"""분석 리포트 조회 (명세 L.1/L.2) — 기간 필터 목록 + 단건 상세 + PDF 다운로드(H.7.1).

app/routers/history.py 와 조회 로직(app/crud/scan.py)을 공유한다.
"""
from datetime import datetime, timedelta
from html import escape
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


# 지표별 판정 기준 — 분석 결과 화면(scanStore.parseApiResult)과 동일
# (라벨, 설명, 기준값, 방향 "min"=이상이면 좋음 / "max"=이하면 좋음, 좋을 때 문구, 나쁠 때 문구)
METRIC_INFO = {
    "moisture": ("수분", "피부 수분 보유량", 60, "min", "정상", "주의"),
    "sebum": ("유분", "피지 분비 정도", 55, "max", "보통", "주의"),
    "pore": ("모공", "모공·피부결 상태", 60, "min", "양호", "관리 권장"),
    "elasticity": ("탄력", "피부 탄력 지수", 60, "min", "정상", "주의"),
    "pigmentation": ("색소침착", "색소·피부 톤", 55, "max", "정상", "주의"),
}
GREEN, AMBER, GRAY = ("#2E7D32", "#E8F5E9"), ("#B26A00", "#FFF4E0"), ("#9E9E9E", "#F5F5F5")


def _fmt(v) -> str:
    return "-" if v is None else f"{round(float(v), 1):g}%"


def _is_good(v, limit, direction) -> bool:
    return v >= limit if direction == "min" else v <= limit


def _status(v, limit, direction, good, bad):
    """(문구, 글자색, 배경색)"""
    if v is None:
        return "측정 안 됨", *GRAY
    return (good, *GREEN) if _is_good(v, limit, direction) else (bad, *AMBER)


def _radar_svg(values: list) -> str:
    """5각형 레이더 차트. values: 0~100 또는 None."""
    import math
    cx, cy, R = 105, 95, 70
    n = len(values)

    def pt(i, r):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * math.cos(a), cy + r * math.sin(a)

    grid = ""
    for lvl in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, R * lvl) for i in range(n)))
        grid += f'<polygon points="{pts}" fill="none" stroke="#E0E0E0" stroke-width="1"/>'
    axes = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#E0E0E0" stroke-width="1"/>'
        for x, y in (pt(i, R) for i in range(n))
    )
    data_pts = " ".join(
        f"{x:.1f},{y:.1f}" for x, y in (pt(i, R * max(0, min(100, v or 0)) / 100) for i, v in enumerate(values))
    )
    labels = ""
    for i, (key, (label, *_)) in enumerate(METRIC_INFO.items()):
        x, y = pt(i, R + 16)
        labels += f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="10" fill="#424242">{label}</text>'
    return f"""<svg width="210" height="190" viewBox="0 0 210 190">{grid}{axes}
      <polygon points="{data_pts}" fill="#4CAF50" fill-opacity="0.25" stroke="#2E7D32" stroke-width="2"/>{labels}</svg>"""


def _render_report_html(session: ScanSession) -> str:
    metrics = session_to_metrics(session)
    measured_at = session.created_at.strftime("%Y.%m.%d %H:%M") if session.created_at else "-"
    score = session.total_score
    score_text = str(score) if score is not None else "-"
    skin_type = escape(session.skin_type_result or "피부 타입 정보 없음")

    # 종합 점수 링 (둘레 2πr = 263.9)
    dash = 263.9 * max(0, min(100, score or 0)) / 100
    ring = f"""<svg width="112" height="112" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="9"/>
      <circle cx="50" cy="50" r="42" fill="none" stroke="#B9F6CA" stroke-width="9" stroke-linecap="round"
              stroke-dasharray="{dash:.1f} 263.9" transform="rotate(-90 50 50)"/>
      <text x="50" y="52" text-anchor="middle" font-size="27" font-weight="800" fill="#FFFFFF" font-family="Noto Sans CJK KR, NanumGothic, sans-serif">{score_text}</text>
      <text x="50" y="67" text-anchor="middle" font-size="9" fill="#C8E6C9">/ 100점</text></svg>"""

    values, cards, bars, measured = [], [], [], []
    for key, (label, desc, limit, direction, good, bad) in METRIC_INFO.items():
        v = metrics.get(key)
        v = None if v is None else float(v)
        values.append(v)
        st, fg, bg = _status(v, limit, direction, good, bad)
        if v is not None:
            measured.append((label, v, _is_good(v, limit, direction)))
        lo, hi = (limit, 100) if direction == "min" else (0, limit)
        rule = f"{limit}% 이상이 {good}" if direction == "min" else f"{limit}% 이하가 {good}"
        cards.append(f"""<td><div class="card" style="background:{bg}">
            <div class="cv" style="color:{fg}">{_fmt(v)}</div>
            <div class="cl">{label}</div>
            <div class="cs" style="color:{fg}">{st}</div></div></td>""")
        fill = "" if v is None else (
            f'<div class="fill" style="width:{max(0, min(100, v)):.0f}%;background:{fg}"></div>')
        bars.append(f"""<tr>
            <td class="bl"><b>{label}</b><br><span>{desc}</span></td>
            <td><div class="track"><div class="zone" style="left:{lo}%;width:{hi - lo}%"></div>{fill}</div>
                <div class="range">{rule}</div></td>
            <td class="bv" style="color:{fg}">{_fmt(v)}</td></tr>""")

    ok = [m for m in measured if m[2]]
    care = [m for m in measured if not m[2]]
    if not measured:
        summary = "측정된 지표가 없어요."
    elif care:
        summary = f"양호한 지표 {len(ok)}개 · 관리가 필요한 지표: <b>{', '.join(m[0] for m in care)}</b>"
    else:
        summary = "측정된 지표가 모두 양호해요."

    white_url, uv_url = metrics.get("white_image_url"), metrics.get("uv_image_url")
    photos = ""
    if white_url or uv_url:
        def cell(url, title, color):
            img = f'<img src="{escape(url)}">' if url else '<div class="noimg">사진 없음</div>'
            return f'<td class="photo"><div class="ptitle" style="background:{color}">{title}</div>{img}</td>'
        photos = f"""<h2>촬영 사진</h2><table class="photos"><tr>
            {cell(white_url, "일반광 · White 5500K", "#455A64")}
            {cell(uv_url, "UV 형광 · 395nm", "#5B3FD1")}</tr></table>"""

    # AI 종합 케어 코멘트 (있을 때만)
    advice = getattr(session, "advice", None)

    def _text(t):
        return escape(t).replace("\n", "<br>") if t else ""

    care_html = ""
    if advice and (advice.summary or advice.morning_routine or advice.night_routine or advice.lifestyle_tips):
        boxes = "".join(
            f'<td><div class="tip"><div class="tt">{title}</div>{_text(body)}</div></td>'
            for title, body in (("☀ 아침 루틴", advice.morning_routine),
                                ("☾ 저녁 루틴", advice.night_routine),
                                ("✿ 생활 습관", advice.lifestyle_tips))
            if body
        )
        next_scan = (f'<div class="next">다음 측정 권장일 · {advice.next_scan_date.strftime("%Y.%m.%d")}</div>'
                     if advice.next_scan_date else "")
        care_html = f"""<div class="care">
            <h2>AI 종합 케어 코멘트</h2>
            {f'<div class="comment">{_text(advice.summary)}</div>' if advice.summary else ''}
            {f'<table class="tips"><tr>{boxes}</tr></table>' if boxes else ''}
            {next_scan}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<style>
    @page {{ size: A4; margin: 14mm 0 10mm; }}
    @page :first {{ margin-top: 0; }}
    body {{ font-family: "Noto Sans CJK KR", "Noto Sans KR", "NanumGothic", sans-serif; color: #212121; font-size: 10.5pt; margin: 0; }}
    .hero {{ background: linear-gradient(135deg, #388E3C, #1B5E20); color: #fff; padding: 22px 34px 20px; }}
    .hero table {{ width: 100%; border-collapse: collapse; }}
    .brand {{ font-size: 8.5pt; font-weight: bold; letter-spacing: 2px; color: #C8E6C9; }}
    .hero h1 {{ font-size: 22pt; margin: 4px 0 10px; }}
    .chip {{ display: inline-block; background: rgba(255,255,255,0.2); font-weight: bold; font-size: 9.5pt;
             padding: 4px 12px; border-radius: 20px; }}
    .meta {{ color: #E8F5E9; font-size: 9.5pt; margin-top: 10px; }}
    .wrap {{ padding: 16px 34px 0; }}
    .summary {{ background: #F6F7F4; border-left: 4px solid #4CAF50; padding: 10px 14px; border-radius: 6px;
                font-size: 10pt; color: #424242; }}
    table.cards {{ width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 7px 0; margin: 14px -7px 0; }}
    .card {{ border-radius: 12px; padding: 9px 6px; text-align: center; }}
    .cv {{ font-size: 16pt; font-weight: 800; }}
    .cl {{ font-size: 9pt; color: #424242; margin-top: 2px; }}
    .cs {{ font-size: 8.5pt; font-weight: bold; margin-top: 3px; }}
    h2 {{ font-size: 12pt; margin: 13px 0 7px; padding-left: 8px; border-left: 4px solid #4CAF50; }}
    table.two {{ width: 100%; border-collapse: collapse; }}
    table.two > tbody > tr > td {{ vertical-align: top; }}
    table.bars {{ width: 100%; border-collapse: collapse; }}
    table.bars td {{ padding: 4px 4px; border-bottom: 1px solid #EEEEEE; vertical-align: middle; }}
    td.bl {{ width: 92px; font-size: 10pt; }} td.bl span {{ font-size: 7.5pt; color: #9E9E9E; }}
    td.bv {{ width: 44px; text-align: right; font-weight: bold; }}
    .track {{ position: relative; height: 9px; background: #EEEEEE; border-radius: 5px; }}
    .zone {{ position: absolute; top: 0; height: 9px; background: #C8E6C9; }}
    .fill {{ position: absolute; top: 2px; left: 0; height: 5px; border-radius: 3px; }}
    .range {{ font-size: 7.5pt; color: #9E9E9E; margin-top: 3px; }}
    .legend {{ font-size: 7.5pt; color: #757575; margin-top: 6px; }}
    .legend i {{ display: inline-block; width: 14px; height: 7px; background: #C8E6C9; margin-right: 4px; }}
    table.photos {{ width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 10px 0; margin: 0 -10px; }}
    td.photo {{ width: 50%; vertical-align: top; }}
    .ptitle {{ color: #fff; font-size: 9pt; font-weight: bold; padding: 5px 10px; border-radius: 8px 8px 0 0; }}
    td.photo img {{ width: 100%; height: 100px; object-fit: cover; border-radius: 0 0 8px 8px; }}
    .noimg {{ height: 100px; background: #F5F5F5; color: #9E9E9E; text-align: center; line-height: 100px;
              font-size: 9pt; border-radius: 0 0 8px 8px; }}
    .care {{ break-inside: avoid; }}
    .comment {{ background: #F1F8F1; border-radius: 10px; padding: 12px 14px; line-height: 1.6; color: #33402F; }}
    table.tips {{ width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 8px 0; margin: 10px -8px 0; }}
    table.tips td {{ vertical-align: top; }}
    .tip {{ border: 1px solid #E0E0E0; border-radius: 10px; padding: 10px 12px; font-size: 9pt; line-height: 1.55; color: #424242; }}
    .tt {{ font-weight: bold; color: #2E7D32; margin-bottom: 4px; font-size: 9.5pt; }}
    .next {{ margin-top: 10px; font-size: 9pt; color: #2E7D32; font-weight: bold; }}
    .foot {{ margin: 14px 34px 0; color: #9E9E9E; font-size: 8pt; border-top: 1px solid #EEEEEE; padding-top: 8px; }}
</style></head>
<body>
    <div class="hero"><table><tr>
        <td>
            <div class="brand">DAMDA SKIN LAB</div>
            <h1>피부 분석 리포트</h1>
            <span class="chip">{skin_type}</span>
            <div class="meta">측정일 {measured_at}</div>
        </td>
        <td style="width:120px; text-align:right">{ring}</td>
    </tr></table></div>

    <div class="wrap">
        <div class="summary">{summary}</div>
        <table class="cards"><tr>{''.join(cards)}</tr></table>

        <h2>지표별 결과</h2>
        <table class="two"><tr>
            <td style="width:230px">{_radar_svg(values)}</td>
            <td><table class="bars">{''.join(bars)}</table>
                <div class="legend"><i></i>연한 초록 칸이 양호한 구간이에요</div></td>
        </tr></table>

        {photos}
        {care_html}
    </div>

    <div class="foot">담다(DAMDA) · 이 리포트는 피부 관리 참고용이며 의학적 진단을 대신하지 않습니다.</div>
</body></html>"""


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
