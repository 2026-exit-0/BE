from pydantic import BaseModel


class ResultOut(BaseModel):         # 출력값 (명세 H.1) — ScanResult 필드 그대로
    id: int
    session_id: str
    moisture: float | None = None
    sebum: float | None = None
    pore: float | None = None
    elasticity: float | None = None
    pigmentation: float | None = None

    class Config:
        from_attributes = True
