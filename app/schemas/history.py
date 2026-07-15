from datetime import datetime

from pydantic import BaseModel


class HistoryOut(BaseModel):        # 출력값 (명세 J.3) — 스캔 세션 + 결과 5지표
    session_id: str
    created_at: datetime
    moisture: float | None = None
    sebum: float | None = None
    pore: float | None = None
    elasticity: float | None = None
    pigmentation: float | None = None

    class Config:
        from_attributes = True
