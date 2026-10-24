from datetime import datetime

from pydantic import BaseModel


class HistoryOut(BaseModel):        # 출력값 (명세 J.3) — 스캔 세션 + 결과 5지표
    session_id: str
    created_at: datetime
    total_score: int | None = None          # 종합 점수 (리포트 히스토리 표·추이용)
    skin_type_result: str | None = None      # 예측 피부 타입
    moisture: float | None = None
    sebum: float | None = None
    pore: float | None = None
    elasticity: float | None = None
    pigmentation: float | None = None
    white_image_url: str | None = None   # ScanImage(WHITE_LED).image_url, 없으면 None
    uv_image_url: str | None = None      # ScanImage(UV_LED).image_url, 없으면 None

    class Config:
        from_attributes = True
