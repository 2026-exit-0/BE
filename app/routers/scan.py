"""스캔 세션 + 목업 분석 (명세 G.3/G.4, H.1~H.3).

AI/하드웨어 연결 전까지 가짜(mock) 분석 결과를 생성한다.
실제 AI 연동 시 _generate_* 부분만 추론 호출로 교체하면 된다.
"""
import random
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.advice import AiAdvice
from app.models.scan import ScanResult, ScanSession
from app.schemas.scan import AdviceOut, AnalyzeOut, ScanCreate, ScanResultOut, ScanSessionOut

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


def _rand_score() -> float:
    return round(random.uniform(40, 90), 1)


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

    # ── 측정 ON 항목만 값 생성 (OFF 는 None) ──
    # TODO: AI 연동 시 아래 가짜 생성부를 실제 추론 결과로 교체
    moisture = _rand_score() if session.moisture_on else None
    sebum = _rand_score() if session.moisture_on else None       # 수분/유분 동일 토글(G.3.2)
    pore = _rand_score() if session.pore_on else None
    pigmentation = _rand_score() if session.melanin_on else None
    elasticity = _rand_score() if session.elasticity_on else None

    measured = [v for v in [moisture, sebum, pore, elasticity, pigmentation] if v is not None]
    total_score = round(sum(measured) / len(measured)) if measured else None

    # 결과 저장 (있으면 갱신 = 재분석 대응)
    result = db.query(ScanResult).filter(ScanResult.session_id == session_id).first()
    if not result:
        result = ScanResult(session_id=session_id)
        db.add(result)
    result.moisture = moisture
    result.sebum = sebum
    result.pore = pore
    result.elasticity = elasticity
    result.pigmentation = pigmentation

    # 피부 타입 간이 판정 (목업)
    skin_type = "복합성"
    if moisture is not None and sebum is not None:
        if moisture < 55 and sebum < 55:
            skin_type = "건성"
        elif sebum >= 70:
            skin_type = "지성"

    # 가장 취약한 지표로 조언 문구 구성
    scores = {k: v for k, v in {
        "moisture": moisture, "sebum": sebum, "pore": pore,
        "elasticity": elasticity, "pigmentation": pigmentation,
    }.items() if v is not None}
    weakest_kr = METRIC_LABELS.get(min(scores, key=scores.get), "피부") if scores else "피부"

    advice = db.query(AiAdvice).filter(AiAdvice.session_id == session_id).first()
    if not advice:
        advice = AiAdvice(session_id=session_id)
        db.add(advice)
    advice.summary = f"{weakest_kr} 관리가 가장 필요한 {skin_type} 피부예요. (목업 결과)"
    advice.morning_routine = "약산성 클렌저 → 토너 → 수분 세럼 → SPF50+ 선크림"
    advice.night_routine = "클렌징 오일 → 토너 → 앰플 → 수면 크림"
    advice.lifestyle_tips = "수분 섭취와 충분한 수면을 유지하세요."
    advice.next_scan_date = date.today() + timedelta(days=14)

    session.total_score = total_score
    session.skin_type_result = skin_type
    session.status = "done"
    db.commit()
    db.refresh(session)
    db.refresh(result)
    db.refresh(advice)

    return AnalyzeOut(
        session_id=session.session_id,
        status=session.status,
        total_score=session.total_score,
        skin_type_result=session.skin_type_result,
        result=ScanResultOut.model_validate(result),
        advice=AdviceOut.model_validate(advice),
    )
