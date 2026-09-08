"""AI 추론 서비스 연동 (명세 G.4).

별도로 떠 있는 AI 추론 서버(DamdaInferenceModel 래핑)를 HTTP로 호출한다.
AI_SERVICE_URL 이 비어있거나 호출 실패 시 None → 라우터가 처리(503 or mock).
"""
from __future__ import annotations

import json

import httpx

from app.core.config import settings


def run_inference(image_bytes: bytes, filename: str, region: str = "PART_0",
                  sensor: dict | None = None) -> dict | None:
    """이미지+부위를 AI 서버로 보내 추론 결과 dict 반환. 실패 시 None.

    반환 형태(AI 서버 = DamdaInferenceModel.predict):
      { "regression": {pore_value, pigmentation_value, wrinkle_value},
        "classification": {...grades...}, "meta": {...} }
    """
    if not settings.AI_SERVICE_URL:
        return None
    try:
        files = {"image": (filename, image_bytes)}
        data = {"region": region}
        if sensor:
            data["sensor"] = json.dumps(sensor)
        resp = httpx.post(f"{settings.AI_SERVICE_URL}/infer",
                          files=files, data=data, timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None
