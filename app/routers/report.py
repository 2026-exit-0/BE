"""분석 리포트 조회 (명세 L.1/L.2) — 기간 필터 목록 + 단건 상세.

app/routers/history.py 와 조회 로직(app/crud/scan.py)을 공유한다.
"""
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.scan import get_user_session, list_user_sessions, session_to_metrics
from app.schemas.report import ReportOut

router = APIRouter(prefix="/report", tags=["report"])

PERIOD_DAYS = {"1m": 30, "3m": 90, "6m": 180}  # 개월 단위 근사치


def _since(period: str) -> datetime | None:
    days = PERIOD_DAYS.get(period)
    return datetime.now() - timedelta(days=days) if days else None


@router.get("", response_model=list[ReportOut], summary="[L.1] 분석 리포트 목록 조회")
def list_reports(period: Literal["1m", "3m", "6m", "all"] = "all",
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    sessions = list_user_sessions(db, user.user_id, since=_since(period))
    return [ReportOut(**session_to_metrics(s)) for s in sessions]


@router.get("/{session_id}", response_model=ReportOut, summary="[L.2] 분석 리포트 상세 조회")
def get_report(session_id: str, db: Session = Depends(get_db),
              user=Depends(get_current_user)):
    # 소유자 아니거나(None) 아직 분석결과 없으면 동일한 404
    session = get_user_session(db, user.user_id, session_id)
    if not session or not session.result:
        raise HTTPException(status_code=404, detail="분석 리포트를 찾을 수 없습니다")
    return ReportOut(**session_to_metrics(session))
