"""스캐너(ESP32-CAM) 연동 — 이미지 pull + 연결 상태 (명세 F.2/G.1, G.4).

SCANNER_URL 의 `/capture` 에서 JPEG 를 가져오고, `/status` 로 연결을 확인한다.
스캐너와 백엔드가 같은 네트워크에 있어야 접근 가능. (HW 연동규격 = 풀 방식)
"""
from __future__ import annotations

import httpx

from app.core.config import settings


def fetch_scanner_image() -> bytes | None:
    """스캐너에서 현재 프레임(JPEG bytes)을 가져온다. 미설정/실패 시 None."""
    if not settings.SCANNER_URL:
        return None
    try:
        resp = httpx.get(f"{settings.SCANNER_URL}/capture", timeout=10.0)
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None


def check_scanner_status() -> bool:
    """스캐너 연결 여부(True/False)."""
    if not settings.SCANNER_URL:
        return False
    try:
        resp = httpx.get(f"{settings.SCANNER_URL}/status", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False
