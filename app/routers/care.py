"""케어가이드 조회 (명세 K.1) — 세션별 AI 조언.

생성(분석)은 app/routers/scan.py 의 analyze-mock 담당. 여기선 "조회"만 담당한다.
쿼리 로직은 app/crud/scan.py 공용 함수 사용 (history.py/report.py 와 공유).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.scan import get_advice_by_session
from app.schemas.scan import AdviceOut

router = APIRouter(prefix="/care", tags=["care"])


@router.get("/{session_id}", response_model=AdviceOut, summary="[K.1] 케어가이드 조회")
def get_care_guide(session_id: str, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    advice = get_advice_by_session(db, user.user_id, session_id)
    if not advice:
        raise HTTPException(status_code=404, detail="케어가이드를 찾을 수 없습니다")
    return advice
