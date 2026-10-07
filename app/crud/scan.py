"""스캔 세션 조회 공용 쿼리 — history(J.3)/report(L.1·L.2)/care(K.1)/device(HW) 가 공유한다."""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.advice import AiAdvice
from app.models.scan import DeviceConnection, ScanImage, ScanSession

STALE_PROCESSING_MINUTES = 5   # 이 시간 넘게 processing 이면 방치된 것으로 보고 failed 처리


def list_user_sessions(db: Session, user_id: str, since: datetime | None = None) -> list[ScanSession]:
    """유저 소유 스캔 세션을 result/images 즉시로딩 + 최신순 정렬로 조회. since 있으면 그 이후분만."""
    query = (db.query(ScanSession)
            .options(joinedload(ScanSession.result), joinedload(ScanSession.images))
            .filter(ScanSession.user_id == user_id))
    if since is not None:
        query = query.filter(ScanSession.created_at >= since)
    return query.order_by(ScanSession.created_at.desc()).all()


def get_latest_session(db: Session, user_id: str) -> ScanSession | None:
    """유저의 가장 최근 스캔 세션 조회 (생성일 최신순 1건). 없으면 None."""
    return (db.query(ScanSession)
           .filter(ScanSession.user_id == user_id)
           .order_by(ScanSession.created_at.desc())
           .first())


def get_user_session(db: Session, user_id: str, session_id: str) -> ScanSession | None:
    """유저 소유의 스캔 세션 단건 조회 (result 즉시로딩). 없거나 소유자가 아니면 None."""
    return (db.query(ScanSession)
           .options(joinedload(ScanSession.result))
           .filter(ScanSession.session_id == session_id, ScanSession.user_id == user_id)
           .first())


def get_latest_processing_session(db: Session, user_id: str) -> ScanSession | None:
    """유저의 가장 최근 status='processing' 세션. 없으면 None. (device trigger 싱글톤 / done 콜백용)"""
    return (db.query(ScanSession)
           .filter(ScanSession.user_id == user_id, ScanSession.status == "processing")
           .order_by(ScanSession.created_at.desc())
           .first())


def expire_stale_sessions(db: Session, user_id: str) -> None:
    """일정 시간(STALE_PROCESSING_MINUTES) 넘게 processing 인 세션을 failed 로 정리.

    HW 는 trigger → done 두 요청 사이에 기기/중계서버가 죽으면 done 이 영영 안 올 수 있어서,
    조회 시점(트리거 싱글톤 체크·상태 폴링·done 조회 직전)마다 호출해 방치를 막는다.
    별도 스케줄러 없이 요청 경로에서 확인하는 방식 — 배포 규모상 이걸로 충분하다.
    """
    cutoff = datetime.now() - timedelta(minutes=STALE_PROCESSING_MINUTES)
    stale = (db.query(ScanSession)
            .filter(ScanSession.user_id == user_id, ScanSession.status == "processing",
                    ScanSession.created_at < cutoff)
            .all())
    if not stale:
        return
    for session in stale:
        session.status = "failed"
    db.commit()


def get_device_connection(db: Session, device_id: str) -> DeviceConnection | None:
    """device_id 의 현재 연결 상태(1건) 조회. 없으면 None."""
    return db.query(DeviceConnection).filter(DeviceConnection.device_id == device_id).first()


def get_advice_by_session(db: Session, user_id: str, session_id: str) -> AiAdvice | None:
    """세션 소유자 확인 후 AiAdvice 조회. 소유 아니거나 세션/조언이 없으면 None."""
    return (db.query(AiAdvice)
           .join(ScanSession, AiAdvice.session_id == ScanSession.session_id)
           .filter(AiAdvice.session_id == session_id, ScanSession.user_id == user_id)
           .first())


def pick_image_url(images: list[ScanImage], image_type: str) -> str | None:
    """session.images 중 image_type 매칭 행의 image_url. 없으면 None.

    ScanImage 에 시간 컬럼이 없어 "최신" 이미지를 보장하지 못한다 — 같은 타입이 여러 개
    저장돼 있어도 매번 같은 결과가 나오도록 image_id 오름차순 정렬 후 첫 번째를 쓴다.
    (근본 해결은 저장 시점 upsert/unique 제약 — 이번 범위 밖, 후속 작업으로 분리)
    """
    matched = sorted(
        (img for img in images if img.image_type == image_type),
        key=lambda img: img.image_id,
    )
    return matched[0].image_url if matched else None


def session_to_metrics(session: ScanSession) -> dict:
    """ScanSession(+result/images) → session_id/created_at/5지표+이미지 dict.

    history/report Out 스키마 공용 입력. report.py 의 ReportOut 은 white/uv_image_url
    필드가 없어서 pydantic extra="ignore" 기본 동작으로 이 두 키는 조용히 무시된다.
    """
    result = session.result
    images = session.images or []
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "moisture": result.moisture if result else None,
        "sebum": result.sebum if result else None,
        "pore": result.pore if result else None,
        "elasticity": result.elasticity if result else None,
        "pigmentation": result.pigmentation if result else None,
        "white_image_url": pick_image_url(images, "WHITE_LED"),
        "uv_image_url": pick_image_url(images, "UV_LED"),
    }
