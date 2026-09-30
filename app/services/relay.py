"""웹 스캔 트리거 시 HW 릴레이 서버(포트 8001)에 촬영 명령 전달.

SCAN_RELAY_URL 의 /scan-command 를 호출해 실제 기기 촬영을 시작시킨다.
member 는 릴레이 쪽에서 기본값으로 처리하므로 보내지 않는다.
"""
from __future__ import annotations

import httpx

from app.core.config import settings


def send_scan_command(device_id: str, part: str | None) -> bool:
    """릴레이 서버에 촬영 명령 전달. 성공(status=ok) 시 True, 그 외/실패 시 False."""
    if not settings.SCAN_RELAY_URL:
        return False
    try:
        resp = httpx.post(
            f"{settings.SCAN_RELAY_URL}/scan-command",
            json={"device_id": device_id, "part": part},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("status") == "ok"
    except Exception:
        return False
