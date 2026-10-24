"""스캔 세션 + 목업 분석 (명세 G.3/G.4, H.1~H.3).

AI/하드웨어 연결 전까지 가짜(mock) 분석 결과를 생성한다.
실제 AI 연동 시 _generate_* 부분만 추론 호출로 교체하면 된다.
"""
import random
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.scan import expire_stale_sessions, get_latest_session
from app.models.advice import AiAdvice
from app.models.scan import ScanImage, ScanResult, ScanSession
from app.models.survey import UserSurvey
from app.schemas.scan import (AdviceOut, AnalyzeOut, ScanCreate, ScanResultOut,
                              ScanSessionOut, ScanStatusOut, ScanTriggerIn)
from app.services.ai import run_inference
from app.services.demo import demo_image_urls, demo_scores, demo_skin_type
from app.services.recommend import (generate_recommendations,
                                    get_session_recommendations)
from app.services.relay import send_scan_command
from app.services.report import build_report
from app.services.scanner import fetch_scanner_image

router = APIRouter(prefix="/scans", tags=["scan"])

METRIC_LABELS = {
    "moisture": "수분", "sebum": "유분", "pore": "모공",
    "elasticity": "탄력", "pigmentation": "색소침착",
}


@router.post("", response_model=ScanSessionOut, status_code=201,
             summary="[G.3/G.4] 스캔 세션 생성")
def create_scan(data: ScanCreate, db: Session = Depends(get_db),
                user=Depends(get_current_user)):
    if not any([data.moisture_on, data.pore_on, data.melanin_on, data.elasticity_on]):
        raise HTTPException(status_code=400, detail="측정 항목을 최소 1개 이상 선택하세요")

    session = ScanSession(
        user_id=user.user_id,
        scan_area=data.scan_area,
        uv_mode=data.uv_mode,
        moisture_on=data.moisture_on,
        pore_on=data.pore_on,
        melanin_on=data.melanin_on,
        elasticity_on=data.elasticity_on,
        temperature=data.temperature,
        humidity=data.humidity,
        uv_index=data.uv_index,
        status="pending",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/trigger", response_model=ScanStatusOut, status_code=201,
             summary="스캔 트리거 (device_id 있으면 HW 릴레이에 촬영 명령까지 전달)")
def trigger_scan(data: ScanTriggerIn = ScanTriggerIn(), db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    if data.device_id:
        if not send_scan_command(data.device_id, data.part):
            raise HTTPException(status_code=502, detail="스캔 기기에 촬영 명령을 전달하지 못했습니다")

    session = ScanSession(user_id=user.user_id, status="processing",
                          device_id=data.device_id, scan_area=data.part or "얼굴 전체")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/status", response_model=ScanStatusOut,
            summary="가장 최근 스캔 세션 상태 조회 (폴링용)")
def get_scan_status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    expire_stale_sessions(db, user.user_id)
    session = get_latest_session(db, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="스캔 세션을 찾을 수 없습니다")
    return session


def _rand_score() -> float:
    return round(random.uniform(40, 90), 1)


def _num(v):
    return float(v) if v is not None else None


def _safe_generate_recommendations(db: Session, session: ScanSession):
    """분석 직후 설문·결과 기반 제품 추천을 계산·저장하고 응답용 목록 반환.

    제품 풀이 비었거나 추천 계산이 실패해도 분석 자체는 성공해야 하므로 예외는 삼킨다.
    """
    try:
        generate_recommendations(db, session, top_n=60)
        return get_session_recommendations(db, session.session_id)
    except Exception:
        db.rollback()
        return []


def _build_and_store_advice(db: Session, session: ScanSession, metrics: dict,
                            skin_type, survey) -> AiAdvice:
    """결과 지표 + 스캔 부위 + 설문 + 환경 → 구조화 리포트 생성·저장 (데모/실제 공용).

    조언·부위 소견을 결과값에서 규칙적으로 파생 → 부위/설문 불일치 제거.
    report(JSON)에 전체 리포트, summary/루틴/생활팁은 기존 FE 호환용으로 함께 저장.
    """
    rep = build_report(
        metrics,
        scan_area=session.scan_area or "얼굴 전체",
        skin_type=skin_type,
        concerns=(survey.concerns if survey else None),
        age_band=(survey.age_band if survey else None),
        gender=(survey.gender if survey else None),
        environment={
            "temperature": _num(session.temperature),
            "humidity": _num(session.humidity),
            "uv_index": session.uv_index,
        },
    )
    advice = db.query(AiAdvice).filter(AiAdvice.session_id == session.session_id).first()
    if not advice:
        advice = AiAdvice(session_id=session.session_id)
        db.add(advice)
    advice.summary = rep.get("summary")
    advice.morning_routine = " → ".join(rep.get("routine_morning", []))
    advice.night_routine = " → ".join(rep.get("routine_night", []))
    advice.lifestyle_tips = " / ".join(rep.get("lifestyle", []))
    advice.report = rep
    advice.next_scan_date = date.today() + timedelta(days=rep.get("next_scan_days", 14))
    return advice


def _apply_demo_result(db: Session, session: ScanSession) -> AnalyzeOut:
    """시연용 큐레이션 목업 결과를 저장하고 응답 생성 (is_mock=True).

    analyze-mock 및 `demo=true` 요청 공통. 순수 랜덤이 아니라 부위별 그럴듯한 프로파일
    + 세션 시드(재분석해도 값 안 튐). 측정 OFF 항목은 None. 정직성: is_mock=True 로
    FE가 '데모(예시 데이터)' 배지를 반드시 표시.
    """
    survey = db.query(UserSurvey).filter(UserSurvey.user_id == session.user_id).first()
    area = session.scan_area or "얼굴 전체"
    scores = demo_scores(
        session.session_id, area,
        skin_type=(survey.skin_type if survey else None),
        concerns=(survey.concerns if survey else None),
        age_band=(survey.age_band if survey else None),
        gender=(survey.gender if survey else None),
    )
    moisture = scores["moisture"] if session.moisture_on else None
    sebum = scores["sebum"] if session.moisture_on else None       # 수분/유분 동일 토글(G.3.2)
    pore = scores["pore"] if session.pore_on else None
    pigmentation = scores["pigmentation"] if session.melanin_on else None
    elasticity = scores["elasticity"] if session.elasticity_on else None

    measured = [v for v in [moisture, sebum, pore, elasticity, pigmentation] if v is not None]
    total_score = round(sum(measured) / len(measured)) if measured else None

    result = db.query(ScanResult).filter(ScanResult.session_id == session.session_id).first()
    if not result:
        result = ScanResult(session_id=session.session_id)
        db.add(result)
    result.moisture = moisture
    result.sebum = sebum
    result.pore = pore
    result.elasticity = elasticity
    result.pigmentation = pigmentation

    skin_type = (survey.skin_type if survey and survey.skin_type
                 else demo_skin_type({"moisture": moisture or 60, "sebum": sebum or 60}))

    advice = _build_and_store_advice(
        db, session,
        {"moisture": moisture, "sebum": sebum, "pore": pore,
         "elasticity": elasticity, "pigmentation": pigmentation},
        skin_type, survey,
    )

    # 폴백 이미지(기존 Supabase URL) — 설문 연령/성별/부위 매칭. 라이브 촬영 실패 대비.
    imgs = demo_image_urls(session.session_id, area,
                           age_band=(survey.age_band if survey else None),
                           gender=(survey.gender if survey else None))
    db.query(ScanImage).filter(ScanImage.session_id == session.session_id).delete()
    for itype, url in imgs.items():
        if url:
            db.add(ScanImage(session_id=session.session_id, image_type=itype,
                             image_url=url, region=area))

    session.total_score = total_score
    session.skin_type_result = skin_type
    session.status = "done"
    db.commit()
    db.refresh(session)
    db.refresh(result)
    db.refresh(advice)

    recs = _safe_generate_recommendations(db, session)

    return AnalyzeOut(
        session_id=session.session_id,
        status=session.status,
        total_score=session.total_score,
        skin_type_result=session.skin_type_result,
        result=ScanResultOut.model_validate(result),
        advice=AdviceOut.model_validate(advice),
        recommended_products=recs,
        is_mock=True,   # 시연용 예시데이터 → FE 데모 배지 표시
    )


@router.post("/{session_id}/analyze-mock", response_model=AnalyzeOut,
             summary="[G.4] 목업 분석 결과 생성")
def analyze_mock(session_id: str, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    session = (db.query(ScanSession)
               .filter(ScanSession.session_id == session_id,
                       ScanSession.user_id == user.user_id)
               .first())
    if not session:
        raise HTTPException(status_code=404, detail="스캔 세션을 찾을 수 없습니다")

    session.status = "processing"
    db.commit()
    return _apply_demo_result(db, session)


def _owned_session(db: Session, session_id: str, user_id: str) -> ScanSession | None:
    return (db.query(ScanSession)
            .filter(ScanSession.session_id == session_id, ScanSession.user_id == user_id)
            .first())


def _apply_ai_result(db: Session, session: ScanSession, ai: dict) -> AnalyzeOut:
    """AI 추론 결과(dict)를 ScanResult/AiAdvice 로 저장하고 응답 생성.

    push(이미지 업로드)·pull(스캐너) 공통 로직.
    현재 모델(v6-macro)은 모공/색소침착만 실측 → 나머지 지표는 목업으로 보완.
    """
    reg = ai.get("regression", {})

    def _clamp(v):
        return None if v is None else max(0.0, min(100.0, round(float(v), 1)))

    # AI 실측: pore/pigmentation. 안 나오는 지표는 목업으로 채움.
    pore = _clamp(reg.get("pore_value"))
    pore = pore if pore is not None else _rand_score()
    pigmentation = _clamp(reg.get("pigmentation_value"))
    pigmentation = pigmentation if pigmentation is not None else _rand_score()
    moisture = _rand_score()
    sebum = _rand_score()
    elasticity = _rand_score()

    skin_type = "복합성"
    if moisture < 55 and sebum < 55:
        skin_type = "건성"
    elif sebum >= 70:
        skin_type = "지성"

    result = db.query(ScanResult).filter(ScanResult.session_id == session.session_id).first()
    if not result:
        result = ScanResult(session_id=session.session_id)
        db.add(result)
    result.moisture = moisture
    result.sebum = sebum
    result.pore = pore
    result.elasticity = elasticity
    result.pigmentation = pigmentation

    total_score = round((moisture + sebum + pore + elasticity + pigmentation) / 5)

    survey = db.query(UserSurvey).filter(UserSurvey.user_id == session.user_id).first()
    if survey and survey.skin_type:
        skin_type = survey.skin_type
    advice = _build_and_store_advice(
        db, session,
        {"moisture": moisture, "sebum": sebum, "pore": pore,
         "elasticity": elasticity, "pigmentation": pigmentation},
        skin_type, survey,
    )

    session.total_score = total_score
    session.skin_type_result = skin_type
    session.status = "done"
    db.commit()
    db.refresh(session)
    db.refresh(result)
    db.refresh(advice)

    recs = _safe_generate_recommendations(db, session)

    return AnalyzeOut(
        session_id=session.session_id,
        status=session.status,
        total_score=session.total_score,
        skin_type_result=session.skin_type_result,
        result=ScanResultOut.model_validate(result),
        advice=AdviceOut.model_validate(advice),
        recommended_products=recs,
        is_mock=False,   # 실제 AI 분석
    )


@router.post("/{session_id}/analyze", response_model=AnalyzeOut,
             summary="[G.4] 실제 AI 분석 (이미지 업로드 · push)")
async def analyze(session_id: str,
                  image: UploadFile | None = File(None),
                  region: str = Form("PART_0"),
                  demo: bool = Form(False),
                  db: Session = Depends(get_db), user=Depends(get_current_user)):
    """업로드 이미지를 AI 추론 서버로 보내 실제 분석.

    demo=true → 시연용 큐레이션 목업(이미지 불필요, is_mock=True). demo=false → 실제(AI 실패 시 503).
    """
    session = _owned_session(db, session_id, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="스캔 세션을 찾을 수 없습니다")

    session.status = "processing"
    db.commit()

    if demo:
        return _apply_demo_result(db, session)
    if image is None:
        raise HTTPException(status_code=422, detail="이미지가 필요합니다 (demo=false)")

    ai = run_inference(await image.read(), image.filename or "scan.jpg", region)
    if ai is None:
        session.status = "failed"
        db.commit()
        raise HTTPException(status_code=503, detail="AI 분석 서버에 연결할 수 없습니다")
    return _apply_ai_result(db, session, ai)


@router.post("/{session_id}/analyze-scan", response_model=AnalyzeOut,
             summary="[G.4] 실제 AI 분석 (스캐너 pull) — FE 스캔 버튼용")
def analyze_scan(session_id: str, region: str = "PART_0", demo: bool = False,
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    """스캐너(ESP32)에서 이미지를 가져와(pull) AI 분석. FE 스캔 버튼용.

    demo=true → 시연용 큐레이션 목업 반환(스캐너·AI 불필요, is_mock=True). FE 목업/실제 토글용.
    demo=false(기본) → 실제: 스캐너 미연결 → 503(스캐너) / AI 미설정·실패 → 503(AI).
    """
    session = _owned_session(db, session_id, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="스캔 세션을 찾을 수 없습니다")

    session.status = "processing"
    db.commit()

    if demo:
        return _apply_demo_result(db, session)

    image_bytes = fetch_scanner_image()
    if image_bytes is None:
        session.status = "failed"
        db.commit()
        raise HTTPException(status_code=503, detail="스캐너에 연결할 수 없습니다")

    ai = run_inference(image_bytes, "scan.jpg", region)
    if ai is None:
        session.status = "failed"
        db.commit()
        raise HTTPException(status_code=503, detail="AI 분석 서버에 연결할 수 없습니다")
    return _apply_ai_result(db, session, ai)
