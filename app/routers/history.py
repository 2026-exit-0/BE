"""스캔 히스토리 조회 (명세 J.3) — 마이페이지 스캔 기록 전체 목록.

단건 결과 조회는 app/routers/result.py 담당. 여기선 "히스토리 목록"만 담당한다.
쿼리 로직은 app/crud/scan.py 공용 함수 사용 (app/routers/report.py 와 공유).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.scan import list_user_sessions, session_to_metrics
from app.schemas.history import HistoryOut

router = APIRouter(prefix="/history", tags=["mypage"])


@router.get("", response_model=list[HistoryOut], summary="[J.3] 내 스캔 기록 전체 조회")
def get_my_history(db: Session = Depends(get_db), user=Depends(get_current_user)):
    sessions = list_user_sessions(db, user.user_id)
    return [HistoryOut(**session_to_metrics(s)) for s in sessions]
