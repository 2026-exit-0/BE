"""분석 리포트 조회 (명세 L.1/L.2) — 기간 필터 목록 + 단건 상세 + PDF 다운로드(H.7.1).

app/routers/history.py 와 조회 로직(app/crud/scan.py)을 공유한다.
"""
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.scan import get_user_session, list_user_sessions, session_to_metrics
from app.models.scan import ScanSession
from app.schemas.report import ReportOut

router = APIRouter(prefix="/report", tags=["report"])

PERIOD_DAYS = {"1m": 30, "3m": 90, "6m": 180}  # 개월 단위 근사치

METRIC_LABELS = {
    "moisture": "수분", "sebum": "유분", "pore": "모공",
    "elasticity": "탄력", "pigmentation": "색소침착",
}


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


def _render_report_html(session: ScanSession) -> str:
    metrics = session_to_metrics(session)
    rows = "".join(
        f"<tr><td>{label}</td><td>{metrics[key] if metrics[key] is not None else '-'}</td></tr>"
        for key, label in METRIC_LABELS.items()
    )
    measured_at = session.created_at.strftime("%Y-%m-%d %H:%M") if session.created_at else "-"
    total_score = session.total_score if session.total_score is not None else "-"
    skin_type = session.skin_type_result or "-"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {{ font-family: sans-serif; padding: 40px; color: #222; }}
    h1 {{ font-size: 22px; margin-bottom: 4px; }}
    .meta {{ color: #666; margin-bottom: 20px; }}
    .total {{ font-size: 36px; font-weight: bold; margin: 16px 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: left; }}
    th {{ background: #f5f5f5; }}
</style>
</head>
<body>
    <h1>담다 분석 리포트</h1>
    <div class="meta">측정일 {measured_at} · 피부 타입 {skin_type}</div>
    <div class="total">종합점수 {total_score}</div>
    <table>
        <tr><th>지표</th><th>점수</th></tr>
        {rows}
    </table>
</body>
</html>"""


@router.get("/{session_id}/pdf", summary="[H.7.1] 분석 리포트 PDF 다운로드")
def get_report_pdf(session_id: str, db: Session = Depends(get_db),
                   user=Depends(get_current_user)):
    session = get_user_session(db, user.user_id, session_id)
    if not session or not session.result:
        raise HTTPException(status_code=404, detail="분석 리포트를 찾을 수 없습니다")

    try:
        from weasyprint import HTML   # 무거운 네이티브 의존성 — 실제 호출 시점에만 로드
    except OSError:
        raise HTTPException(
            status_code=500,
            detail="PDF 생성 라이브러리 초기화에 실패했습니다 (WeasyPrint 네이티브 라이브러리 필요 — Windows는 GTK3 런타임 설치 필요)",
        )

    pdf_bytes = HTML(string=_render_report_html(session)).write_pdf()
    headers = {"Content-Disposition": f'attachment; filename="report_{session_id}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
