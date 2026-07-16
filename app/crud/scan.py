"""스캔 세션 조회 공용 쿼리 — history(J.3)/report(L.1·L.2) 가 공유한다."""
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models.scan import ScanSession


def list_user_sessions(db: Session, user_id: str, since: datetime | None = None) -> list[ScanSession]:
    """유저 소유 스캔 세션을 result 즉시로딩 + 최신순 정렬로 조회. since 있으면 그 이후분만."""
    query = (db.query(ScanSession)
            .options(joinedload(ScanSession.result))
            .filter(ScanSession.user_id == user_id))
    if since is not None:
        query = query.filter(ScanSession.created_at >= since)
    return query.order_by(ScanSession.created_at.desc()).all()


def get_user_session(db: Session, user_id: str, session_id: str) -> ScanSession | None:
    """유저 소유의 스캔 세션 단건 조회 (result 즉시로딩). 없거나 소유자가 아니면 None."""
    return (db.query(ScanSession)
           .options(joinedload(ScanSession.result))
           .filter(ScanSession.session_id == session_id, ScanSession.user_id == user_id)
           .first())


def session_to_metrics(session: ScanSession) -> dict:
    """ScanSession(+result) → session_id/created_at/5지표 dict. history/report Out 스키마 공용 입력."""
    result = session.result
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "moisture": result.moisture if result else None,
        "sebum": result.sebum if result else None,
        "pore": result.pore if result else None,
        "elasticity": result.elasticity if result else None,
        "pigmentation": result.pigmentation if result else None,
    }
