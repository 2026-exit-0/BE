from datetime import datetime

from pydantic import BaseModel, Field


class DeviceTriggerIn(BaseModel):
    device_id: str


class DeviceDoneIn(BaseModel):
    device_id: str
    timestamp: str                    # "%Y%m%d_%H%M%S" (예: "20260928_224509")
    part: str | None = None           # 측정 부위 (예: "FOREHEAD")
    moisture: float
    oil: float
    white_img: str = Field(min_length=1)   # 백색 LED 사진 URL (Supabase 등) — 필수
    uv_img: str = Field(min_length=1)      # UV LED 사진 URL — 필수


class DeviceScanOut(BaseModel):
    session_id: str
    status: str

    class Config:
        from_attributes = True


class DeviceLinkOut(BaseModel):
    device_id: str
    user_id: str | None = None
    connected_at: datetime | None = None

    class Config:
        from_attributes = True
