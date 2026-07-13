"""날씨 외부 API 연동 + 피부 지수/케어 조언 (명세 E.2, F.3).

위치 우선순위:
  1) 요청 lat/lon  — 프론트가 navigator.geolocation 으로 넘기는 값 (정석)
  2) 서버 IP 기반 자동 위치 — 개발/시연 편의용. 배포 시엔 '서버 위치'라 부정확
  3) 기본 지역(서울)

- WEATHER_API_KEY 없거나 호출 실패 → 목업(fallback, is_mock=True)
- 같은 지역(소수 2자리) 30분 캐싱
- 정확한 자외선(uvi)은 One Call 3.0 사용 (무료 티어 有, 구독 등록 필요)
"""
from __future__ import annotations

import time

import httpx

from app.core.config import settings

ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall"
IPGEO_URL = "https://ipapi.co/json/"

# key: (lat2, lon2) -> (expires_at, data)
_cache: dict[tuple[float, float], tuple[float, dict]] = {}
_ip_cache: dict = {}  # {"exp": ts, "val": (lat, lon, city) | None}


def _uv_label(uvi: float) -> str:
    """WHO UV 지수 구간 → 한글 라벨."""
    if uvi < 3:
        return "낮음"
    if uvi < 6:
        return "보통"
    if uvi < 8:
        return "높음"
    return "매우높음"


def _ip_location():
    """서버 IP 기반 대략적 위치 (best-effort, 30분 캐시). 실패 시 None."""
    now = time.time()
    if _ip_cache.get("exp", 0) > now:
        return _ip_cache["val"]
    val = None
    try:
        r = httpx.get(IPGEO_URL, timeout=4.0)
        r.raise_for_status()
        j = r.json()
        val = (float(j["latitude"]), float(j["longitude"]), j.get("city") or "현재 위치")
    except Exception:
        val = None
    _ip_cache["exp"] = now + settings.WEATHER_CACHE_TTL
    _ip_cache["val"] = val
    return val


def _resolve_location(lat: float | None, lon: float | None):
    if lat is not None and lon is not None:
        return lat, lon, "현재 위치"
    loc = _ip_location()
    if loc:
        return loc
    return settings.WEATHER_DEFAULT_LAT, settings.WEATHER_DEFAULT_LON, "서울"


def _build(region: str, temp: float, humidity: float, uvi: float, is_mock: bool) -> dict:
    uv_label = _uv_label(uvi)
    moisture = max(0, min(100, round(humidity)))            # 습도 → 수분 지수
    dryness = max(0, min(100, round(100 - humidity)))       # 건조 지수
    skin_uv = max(0, min(100, round(uvi / 11 * 100)))       # uvi(0~11+) → 0~100

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
        "skin_uv": skin_uv,
        "advice": " ".join(tips),
        "is_mock": is_mock,
    }


def _mock(region: str = "서울") -> dict:
    return _build(region, 22.0, 45.0, 4.0, is_mock=True)   # uvi 4 → 보통


def get_weather(lat: float | None = None, lon: float | None = None) -> dict:
    lat, lon, region = _resolve_location(lat, lon)
    key = (round(lat, 2), round(lon, 2))

    now = time.time()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]

    if not settings.WEATHER_API_KEY:
        data = _mock(region)                               # 키 없음 → 목업
    else:
        try:
            resp = httpx.get(
                ONECALL_URL,
                params={"lat": lat, "lon": lon, "appid": settings.WEATHER_API_KEY,
                        "units": "metric", "lang": "kr",
                        "exclude": "minutely,hourly,daily,alerts"},
                timeout=5.0,
            )
            resp.raise_for_status()
            cur = resp.json()["current"]
            data = _build(region, float(cur["temp"]), float(cur["humidity"]),
                          float(cur.get("uvi", 0)), is_mock=False)
        except Exception:
            data = _mock(region)                           # 호출 실패 → 목업

    _cache[key] = (now + settings.WEATHER_CACHE_TTL, data)
    return data
