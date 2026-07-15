"""분석 결과 조회 (명세 H.1) — 스캔 결과 단건 조회.

생성(분석)은 app/routers/scan.py 담당. 여기선 "조회"만 담당한다.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.scan import ScanResult, ScanSession
from app.schemas.result import ResultOut

router = APIRouter(prefix="/result", tags=["result"])


@router.get("/{session_id}", response_model=ResultOut, summary="[H.1] 분석 결과 조회")
def get_result(session_id: str, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    # session 소유자 조인 필터 — 남의 세션이면 존재 여부와 무관하게 동일한 404
    result = (db.query(ScanResult)
             .join(ScanSession, ScanResult.session_id == ScanSession.session_id)
             .filter(ScanResult.session_id == session_id,
                     ScanSession.user_id == user.user_id)
             .first())
    if not result:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다")
    return result
