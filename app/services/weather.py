"""날씨 외부 API 연동 + 피부 지수/케어 조언 (명세 E.2, F.3).

- WEATHER_API_KEY 없거나 호출 실패 → 목업(fallback) 응답 (is_mock=True)
- 같은 지역(소수 2자리) 30분 캐싱으로 반복 호출 방지

※ 캐시는 프로세스 메모리 기반(개발/단일 워커용). 멀티 워커 배포 시 Redis 등으로 교체.
   무료 current API 엔 UV 가 없어 uv_index 는 '보통' 기본값 → One Call 연동 시 교체.
"""
from __future__ import annotations

import time

import httpx

from app.core.config import settings

OWM_URL = "https://api.openweathermap.org/data/2.5/weather"
_UV_SCORE = {"낮음": 20, "보통": 50, "높음": 75, "매우높음": 95}

# key: (lat2, lon2) -> (expires_at, data)
_cache: dict[tuple[float, float], tuple[float, dict]] = {}


def _build(region: str, temp: float, humidity: float, uv_label: str, is_mock: bool) -> dict:
    moisture = max(0, min(100, round(humidity)))          # 습도 → 수분 지수
    dryness = max(0, min(100, round(100 - humidity)))     # 건조 지수
    uv_score = _UV_SCORE.get(uv_label, 50)

    tips = []
    if humidity < 40:
        tips.append("공기가 건조해요. 수분 세럼·크림으로 보습을 강화하세요.")
    elif humidity > 70:
        tips.append("습도가 높아요. 가벼운 제형으로 산뜻하게 관리하세요.")
    if uv_label in ("높음", "매우높음"):
        tips.append("자외선이 강해요. SPF50+ 선크림을 꼭 챙기세요.")
    if not tips:
        tips.append("무난한 날씨예요. 기본 보습과 자외선 차단을 유지하세요.")

    return {
        "region": region,
        "temperature": temp,
        "humidity": humidity,
        "uv_index": uv_label,
        "skin_moisture": moisture,
        "skin_dryness": dryness,
        "skin_uv": uv_score,
        "advice": " ".join(tips),
        "is_mock": is_mock,
    }


def _mock() -> dict:
    return _build("서울", 22.0, 45.0, "보통", is_mock=True)


def get_weather(lat: float | None = None, lon: float | None = None) -> dict:
    lat = lat if lat is not None else settings.WEATHER_DEFAULT_LAT
    lon = lon if lon is not None else settings.WEATHER_DEFAULT_LON
    key = (round(lat, 2), round(lon, 2))

    now = time.time()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]

    if not settings.WEATHER_API_KEY:
        data = _mock()                     # 키 없음 → 목업
    else:
        try:
            resp = httpx.get(
                OWM_URL,
                params={"lat": lat, "lon": lon, "appid": settings.WEATHER_API_KEY,
                        "units": "metric", "lang": "kr"},
                timeout=5.0,
            )
            resp.raise_for_status()
            j = resp.json()
            region = j.get("name") or "현재 위치"
            temp = float(j["main"]["temp"])
            humidity = float(j["main"]["humidity"])
            data = _build(region, temp, humidity, "보통", is_mock=False)
        except Exception:
            data = _mock()                 # 호출 실패 → 목업

    _cache[key] = (now + settings.WEATHER_CACHE_TTL, data)
    return data
