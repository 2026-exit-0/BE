from pydantic import BaseModel


class ResultOut(BaseModel):         # 출력값 (명세 H.1) — ScanResult 필드 그대로
    id: int
    session_id: str
    moisture: float | None = None
    sebum: float | None = None
    pore: float | None = None
    elasticity: float | None = None
    pigmentation: float | None = None
    white_image_url: str | None = None   # ScanImage(WHITE_LED).image_url, 없으면 None
    uv_image_url: str | None = None      # ScanImage(UV_LED).image_url, 없으면 None

    class Config:
        from_attributes = True
