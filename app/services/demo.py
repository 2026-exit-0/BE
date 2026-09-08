"""시연용 큐레이션 목업 결과 생성 (진짜 같은 데모).

analyze-mock 및 `demo=true` 요청에서 사용한다. 순수 랜덤(_rand_score) 대신 부위별로
그럴듯한 프로파일 + session_id 시드 기반 미세 지터를 써서, 시연영상에서 자연스럽고
세션마다 일관되게(재분석해도 값이 안 튀게) 보이도록 한다.

⚠️ 정직성: 이 값은 예시(데모) 데이터다. 응답의 is_mock=True 로 FE가 '예시(데모)' 배지를
표시해야 한다. 실제 측정값/모델 성능으로 제시하지 말 것.
"""
from __future__ import annotations

import random
from typing import Dict

# 부위/영역별 그럴듯한 기본 프로파일 (0~100 점수, 높을수록 양호).
# '건강하지만 개선 여지 있는' 시나리오 — 취약점이 하나 도드라지게 설계.
_BASE: Dict[str, Dict[str, float]] = {
    "얼굴 전체": {"moisture": 66, "sebum": 60, "pore": 55, "elasticity": 71, "pigmentation": 63},
    "이마":     {"moisture": 62, "sebum": 52, "pore": 58, "elasticity": 73, "pigmentation": 68},
    "볼":       {"moisture": 70, "sebum": 64, "pore": 61, "elasticity": 72, "pigmentation": 66},
    "코":       {"moisture": 58, "sebum": 47, "pore": 49, "elasticity": 70, "pigmentation": 60},
    "턱":       {"moisture": 60, "sebum": 55, "pore": 57, "elasticity": 68, "pigmentation": 64},
}
_DEFAULT = _BASE["얼굴 전체"]
METRICS = ("moisture", "sebum", "pore", "elasticity", "pigmentation")


def demo_scores(session_id: str, scan_area: str = "얼굴 전체") -> Dict[str, float]:
    """세션 시드 기반 큐레이션 점수. 같은 세션은 항상 같은 값(재분석 일관), 세션마다 다름."""
    base = _BASE.get(scan_area, _DEFAULT)
    rng = random.Random(f"damda-demo::{session_id}")
    return {k: round(min(95.0, max(35.0, base[k] + rng.uniform(-5, 5))), 1) for k in METRICS}


def demo_skin_type(scores: Dict[str, float]) -> str:
    m, s = scores["moisture"], scores["sebum"]
    if m < 55 and s < 55:
        return "건성"
    if s >= 70:
        return "지성"
    return "복합성"
