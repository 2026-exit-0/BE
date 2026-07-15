"""스캔 히스토리 조회 (명세 J.3) — 마이페이지 스캔 기록 전체 목록.

단건 결과 조회는 app/routers/result.py 담당. 여기선 "히스토리 목록"만 담당한다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.scan import ScanSession
from app.schemas.history import HistoryOut

router = APIRouter(prefix="/history", tags=["mypage"])


@router.get("", response_model=list[HistoryOut], summary="[J.3] 내 스캔 기록 전체 조회")
def get_my_history(db: Session = Depends(get_db), user=Depends(get_current_user)):
    sessions = (db.query(ScanSession)
               .options(joinedload(ScanSession.result))
               .filter(ScanSession.user_id == user.user_id)
               .order_by(ScanSession.created_at.desc())
               .all())
    return [
        HistoryOut(
            session_id=s.session_id,
            created_at=s.created_at,
            moisture=s.result.moisture if s.result else None,
            sebum=s.result.sebum if s.result else None,
            pore=s.result.pore if s.result else None,
            elasticity=s.result.elasticity if s.result else None,
            pigmentation=s.result.pigmentation if s.result else None,
        )
        for s in sessions
    ]
