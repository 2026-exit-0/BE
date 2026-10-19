"""시연용 큐레이션 목업 결과 생성 (진짜 같은 데모).

analyze-mock 및 `demo=true` 요청에서 사용한다. 순수 랜덤이 아니라
설문(피부타입·고민) + 연령대/성별 + 부위 기반으로 그럴듯한 5지표를 만들고,
session_id 시드로 재분석해도 값이 안 튀게(세션마다 다르게) 한다.
폴백 이미지는 이미 Supabase 에 있는 실측 스캔 URL(demo_url_map.json)에서 고른다.

⚠️ 정직성: 이 값은 예시(데모) 데이터다. 응답의 is_mock=True 로 FE가 '예시(데모)' 배지를
표시해야 한다. 실제 측정값/모델 성능으로 제시하지 말 것.
"""
from __future__ import annotations

import json
import os
import random
import unicodedata
from collections import defaultdict
from typing import Dict, List, Optional


def _nfc(s):
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s

# 부위/영역별 그럴듯한 기본 프로파일 (0~100 점수, 높을수록 양호).
_BASE: Dict[str, Dict[str, float]] = {
    "얼굴 전체": {"moisture": 66, "sebum": 60, "pore": 55, "elasticity": 71, "pigmentation": 63},
    "이마":     {"moisture": 62, "sebum": 52, "pore": 58, "elasticity": 73, "pigmentation": 68},
    "볼":       {"moisture": 70, "sebum": 64, "pore": 61, "elasticity": 72, "pigmentation": 66},
    "코":       {"moisture": 58, "sebum": 47, "pore": 49, "elasticity": 70, "pigmentation": 60},
    "턱":       {"moisture": 60, "sebum": 55, "pore": 57, "elasticity": 68, "pigmentation": 64},
}
_DEFAULT = _BASE["얼굴 전체"]
METRICS = ("moisture", "sebum", "pore", "elasticity", "pigmentation")

# --- 설문/연령 기반 보정 (점수는 높을수록 양호 → '고민'은 해당 지표를 낮춘다) ---
SKIN_TYPE_ADJ: Dict[str, Dict[str, float]] = {
    "건성": {"moisture": -18, "sebum": -15},
    "지성": {"sebum": +20, "pore": -6},
    "복합성": {"sebum": +5},
    "민감성": {"moisture": -8},
}
CONCERN_ADJ: Dict[str, Dict[str, float]] = {
    "모공": {"pore": -18},
    "주름": {"elasticity": -18},
    "탄력": {"elasticity": -15},
    "색소침착": {"pigmentation": -18},
    "건조": {"moisture": -18},
    "여드름": {"sebum": +15, "pore": -12},
}
AGE_ADJ: Dict[str, Dict[str, float]] = {
    "10대": {"elasticity": +6, "pigmentation": +6, "sebum": +6, "pore": -4},
    "20대": {"elasticity": +5, "pigmentation": +4},
    "30대": {},
    "40대": {"elasticity": -6, "pigmentation": -6, "moisture": -3},
    "50대": {"elasticity": -12, "pigmentation": -12, "moisture": -6},
    "60대+": {"elasticity": -18, "pigmentation": -16, "moisture": -8},
}
GENDER_ADJ: Dict[str, Dict[str, float]] = {"M": {"sebum": +6, "pore": -3}}


def _apply(scores: Dict[str, float], adj: Dict[str, float]) -> None:
    for k, v in adj.items():
        if k in scores:
            scores[k] += v


def demo_scores(session_id: str, scan_area: str = "얼굴 전체",
                skin_type: Optional[str] = None,
                concerns: Optional[List[str]] = None,
                age_band: Optional[str] = None,
                gender: Optional[str] = None) -> Dict[str, float]:
    """설문·연령·성별·부위 기반 큐레이션 점수. 같은 세션은 항상 같은 값(재분석 일관)."""
    scan_area, skin_type, age_band = _nfc(scan_area), _nfc(skin_type), _nfc(age_band)
    base = dict(_BASE.get(scan_area, _DEFAULT))
    _apply(base, SKIN_TYPE_ADJ.get(skin_type or "", {}))
    for c in (concerns or []):
        _apply(base, CONCERN_ADJ.get(_nfc(c), {}))
    _apply(base, AGE_ADJ.get(age_band or "", {}))
    _apply(base, GENDER_ADJ.get(gender or "", {}))
    rng = random.Random(f"damda-demo::{session_id}")
    return {k: round(min(95.0, max(20.0, base[k] + rng.uniform(-4, 4))), 1) for k in METRICS}


def demo_skin_type(scores: Dict[str, float]) -> str:
    m, s = scores["moisture"], scores["sebum"]
    if m < 55 and s < 55:
        return "건성"
    if s >= 70:
        return "지성"
    return "복합성"


# --- 폴백 이미지 (기존 Supabase URL) ---
# scripts/demo_images/demo_url_map.json : [{age_band, gender, part, light, url}, ...]
_MAP_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "demo_images", "demo_url_map.json"))
_URL_IDX: Dict[tuple, List[str]] = defaultdict(list)
try:
    for _e in json.load(open(_MAP_PATH, encoding="utf-8")):
        _URL_IDX[(_e["age_band"], _e["gender"], _e["part"], _e["light"])].append(_e["url"])
except Exception:
    pass  # 매핑 없으면 폴백 이미지 없이 동작(이미지 None)

# scan_area(한글) → demo_url_map 의 PART 토큰
AREA_PART = {
    "이마": "FOREHEAD", "코": "NOSE", "턱": "CHIN",
    "왼쪽볼": "L_CHEEK", "좌볼": "L_CHEEK", "left": "L_CHEEK",
    "오른쪽볼": "R_CHEEK", "우볼": "R_CHEEK", "right": "R_CHEEK",
    "볼": "L_CHEEK", "얼굴 전체": "FOREHEAD",
}


def _pick(cands: List[str], seed: str) -> Optional[str]:
    return random.Random(seed).choice(cands) if cands else None


def demo_image_urls(session_id: str, scan_area: str = "얼굴 전체",
                    age_band: Optional[str] = None,
                    gender: Optional[str] = None) -> Dict[str, Optional[str]]:
    """설문(연령/성별/부위)에 맞는 폴백 이미지 URL. {'WHITE_LED': url, 'UV_LED': url}.

    정확 매칭 → 같은 성별 임의연령 → 임의 로 완화. 세션 시드로 일관.
    """
    scan_area, age_band = _nfc(scan_area), _nfc(age_band)
    part = AREA_PART.get(scan_area, "FOREHEAD")
    out: Dict[str, Optional[str]] = {}
    for light, itype in (("white", "WHITE_LED"), ("uv", "UV_LED")):
        cands = (
            _URL_IDX.get((age_band, gender, part, light))
            or _URL_IDX.get(("기타", gender, part, light))
            or [u for (ab, ge, pa, li), urls in _URL_IDX.items()
                if ge == gender and pa == part and li == light for u in urls]
            or [u for (ab, ge, pa, li), urls in _URL_IDX.items()
                if pa == part and li == light for u in urls]
        )
        out[itype] = _pick(cands, f"{session_id}:{itype}")
    return out
