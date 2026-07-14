"""날씨 조회 (명세 E.2, F.3). 비로그인도 접근 가능(홈 위젯)."""
from fastapi import APIRouter

from app.schemas.weather import WeatherOut
from app.services.weather import get_weather

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("", response_model=WeatherOut,
            summary="[E.2/F.3] 오늘의 날씨 + 피부 지수/케어 조언")
def read_weather(lat: float | None = None, lon: float | None = None):
    """위치(lat/lon) 미지정 시 기본 지역(서울). 키 없거나 실패 시 목업 반환."""
    return get_weather(lat, lon)
