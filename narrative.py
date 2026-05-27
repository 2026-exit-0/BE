"""측정값 → 자연어 평가 / 종합 narrative 생성.

목적:
  - raw 수치만 보여주면 사용자 인지 부담 큼 ("Ra=2.8이 좋은건가 나쁜건가?")
  - "오늘 피부 상태: 양호, 특히 색소 관리 우수" 같은 stable narrative
  - 졸업 발표 인상 결정 요소

설계 의도:
  - 각 측정/등급 헤드별 threshold 기반 평가 (good/fair/poor)
  - 사용자 입력 (피부타입/민감도/aging) 과 조합해 맥락 narrative
  - 다국어 확장 가능하게 메시지 dict 분리
"""

from __future__ import annotations

from typing import Dict, List, Optional


# ============================================================
# 평가 기준 (placeholder — 실제 도메인 기준으로 조정 필요)
# ============================================================
# 각 측정값/등급의 "양호" 임계치. AI-Hub 028 라벨 분포 기준 추정값.
# 추후 실제 수치 분포 보고 P50/P75/P90 같은 사분위로 보정 권장.

# 회귀 측정값 — 더 낮을수록 좋은 것 (예: 모공 수, 색소반점 수)
THRESHOLDS_LOWER_BETTER = {
    "pore_value": {"good": 200, "fair": 350, "poor": 500},
    "pigmentation_value": {"good": 15, "fair": 30, "poor": 50},
    "wrinkle_value": {"good": 2.5, "fair": 4.0, "poor": 6.0},  # Ra (μm)
}

# 회귀 측정값 — 더 높을수록 좋은 것 (예: 수분, 탄력)
THRESHOLDS_HIGHER_BETTER = {
    "moisture": {"good": 50, "fair": 35, "poor": 20},
    "elasticity_mean": {"good": 0.7, "fair": 0.55, "poor": 0.4},
}

# 분류 등급 — 낮은 grade 가 좋은 상태 (0=양호, max=심함)
GRADE_RATINGS = {
    "wrinkle_grade": {"good_max": 2, "fair_max": 4},  # 0~6
    "pigmentation_grade": {"good_max": 1, "fair_max": 3},  # 0~5
    "pore_grade": {"good_max": 1, "fair_max": 3},  # 0~5
    "dryness_grade": {"good_max": 1, "fair_max": 2},  # 0~4
    "sagging_grade": {"good_max": 2, "fair_max": 4},  # 0~6
}


# ============================================================
# 단위 / label
# ============================================================
UNIT_LABELS = {
    "moisture": "수분",
    "elasticity_mean": "탄력",
    "pore_value": "모공 수",
    "pigmentation_value": "색소반점 수",
    "wrinkle_value": "주름 거칠기 (Ra)",
    "wrinkle_grade": "주름 등급",
    "pigmentation_grade": "색소 등급",
    "pore_grade": "모공 등급",
    "dryness_grade": "건조도 등급",
    "sagging_grade": "처짐 등급",
    "skin_type": "피부 타입",
    "sensitive": "민감성",
}

RATING_TEXT = {
    "good": "양호",
    "fair": "보통",
    "poor": "주의 필요",
}


# ============================================================
# 평가 함수
# ============================================================

def rate_regression(name: str, value: float) -> str:
    """회귀 측정값 → good/fair/poor"""
    if name in THRESHOLDS_LOWER_BETTER:
        t = THRESHOLDS_LOWER_BETTER[name]
        if value <= t["good"]:
            return "good"
        if value <= t["fair"]:
            return "fair"
        return "poor"
    if name in THRESHOLDS_HIGHER_BETTER:
        t = THRESHOLDS_HIGHER_BETTER[name]
        if value >= t["good"]:
            return "good"
        if value >= t["fair"]:
            return "fair"
        return "poor"
    return "fair"  # unknown


def rate_grade(name: str, grade: int) -> str:
    """등급 → good/fair/poor"""
    if name not in GRADE_RATINGS:
        return "fair"
    t = GRADE_RATINGS[name]
    if grade <= t["good_max"]:
        return "good"
    if grade <= t["fair_max"]:
        return "fair"
    return "poor"


# ============================================================
# Narrative 생성
# ============================================================

def generate_narrative(
    region: str,
    regression: Dict[str, float],
    classification: Dict[str, int],
    user_inputs: Optional[dict] = None,
) -> dict:
    """종합 평가 narrative 생성.

    Args:
        region: 측정 부위 (FOREHEAD, L_CHEEK 등)
        regression: 회귀 예측값 dict (denormalized)
        classification: 분류 예측 클래스 dict
        user_inputs: {"skin_type": "건성", "sensitivity": 3, "aging_score": 2, "lifestyle_flags": {...}}

    Returns:
        {
            "summary": "오늘 피부 컨디션: 양호. 특히 색소 관리 우수, 모공 케어 추천",
            "per_metric": [{"name": "수분", "value": "38.5", "rating": "good", "comment": "..."}],
            "tips": ["자외선 차단제 매일 사용 권장", ...],
            "overall_score": 78,  # 0~100
        }
    """
    user_inputs = user_inputs or {}
    per_metric: List[dict] = []
    good_count = 0
    fair_count = 0
    poor_count = 0
    tips: List[str] = []

    # 회귀 측정값 평가
    for name, value in regression.items():
        rating = rate_regression(name, value)
        per_metric.append({
            "name": UNIT_LABELS.get(name, name),
            "raw_name": name,
            "value": f"{value:.2f}",
            "rating": rating,
            "rating_text": RATING_TEXT[rating],
        })
        if rating == "good":
            good_count += 1
        elif rating == "fair":
            fair_count += 1
        else:
            poor_count += 1

    # 분류 등급 평가
    for name, grade in classification.items():
        if name in ("skin_type", "sensitive"):
            # 사용자 입력으로 대체 가능한 약한 헤드 — 예측 자체는 표시하지만 평가는 user_input 우선
            continue
        rating = rate_grade(name, grade)
        per_metric.append({
            "name": UNIT_LABELS.get(name, name),
            "raw_name": name,
            "value": f"{grade}",
            "rating": rating,
            "rating_text": RATING_TEXT[rating],
        })
        if rating == "good":
            good_count += 1
        elif rating == "fair":
            fair_count += 1
        else:
            poor_count += 1

    # 사용자 입력 표시 (echo, 평가 없이)
    if user_inputs.get("skin_type"):
        per_metric.append({
            "name": UNIT_LABELS["skin_type"],
            "raw_name": "skin_type",
            "value": user_inputs["skin_type"],
            "rating": "info",
            "rating_text": "(사용자 입력)",
        })
    if "sensitivity" in user_inputs:
        sens = user_inputs["sensitivity"]
        per_metric.append({
            "name": UNIT_LABELS["sensitive"],
            "raw_name": "sensitive",
            "value": f"{sens}/5",
            "rating": "info",
            "rating_text": "(사용자 입력)",
        })

    # 종합 점수 (0~100)
    total_evaluated = good_count + fair_count + poor_count
    if total_evaluated > 0:
        overall_score = int((good_count * 100 + fair_count * 60 + poor_count * 30) / total_evaluated)
    else:
        overall_score = 50

    # Summary 생성
    if overall_score >= 80:
        condition = "매우 양호"
    elif overall_score >= 60:
        condition = "양호"
    elif overall_score >= 40:
        condition = "보통"
    else:
        condition = "주의 필요"
    summary_parts = [f"오늘 {region} 부위 피부 컨디션: {condition} ({overall_score}점)"]

    # 가장 좋은 / 나쁜 항목 강조
    rated_metrics = [m for m in per_metric if m["rating"] in ("good", "fair", "poor")]
    if rated_metrics:
        best = next((m for m in rated_metrics if m["rating"] == "good"), None)
        worst = next((m for m in rated_metrics if m["rating"] == "poor"), None)
        if best:
            summary_parts.append(f"{best['name']} 우수")
        if worst:
            summary_parts.append(f"{worst['name']} 관리 권장")

    summary = ". ".join(summary_parts)

    # Tips 생성 (lifestyle + 약점 기반)
    lifestyle = user_inputs.get("lifestyle_flags", {})
    if lifestyle.get("sunscreen") == "rare":
        tips.append("자외선 차단제를 매일 사용하면 색소침착/노화 예방에 큰 도움")
    if lifestyle.get("sleep") == "poor":
        tips.append("수면 부족은 피부 회복력을 떨어뜨립니다. 7시간 이상 권장")

    for m in rated_metrics:
        if m["rating"] == "poor":
            tip = _tip_for_metric(m["raw_name"], user_inputs)
            if tip:
                tips.append(tip)

    return {
        "summary": summary,
        "per_metric": per_metric,
        "tips": tips[:5],  # 최대 5개
        "overall_score": overall_score,
        "good_count": good_count,
        "fair_count": fair_count,
        "poor_count": poor_count,
    }


def _tip_for_metric(metric_name: str, user_inputs: dict) -> Optional[str]:
    """헤드별 개선 팁 (간단 placeholder)."""
    skin_type = user_inputs.get("skin_type", "")
    tips_map = {
        "moisture": "수분 부족 — 히알루론산 / 세라마이드 함유 제품 권장",
        "elasticity_mean": "탄력 저하 — 펩타이드 / 레티놀 함유 제품 권장 (민감성은 저농도부터)",
        "pore_value": "모공 케어 — BHA (살리실산) 또는 클레이 마스크 권장",
        "pigmentation_value": "색소 관리 — 비타민 C 세럼 + 자외선 차단 필수",
        "wrinkle_value": "주름 — 레티놀 / 펩타이드 야간 케어 권장",
        "wrinkle_grade": "주름 — 레티놀 / 펩타이드 야간 케어 권장",
        "pigmentation_grade": "색소 관리 — 비타민 C 세럼 + 자외선 차단 필수",
        "pore_grade": "모공 케어 — BHA 또는 클레이 마스크 권장",
        "dryness_grade": "건조 — 보습 강화 (오일/크림) 권장",
        "sagging_grade": "처짐 — 마사지 + 탄력 케어 권장",
    }
    tip = tips_map.get(metric_name)
    if tip and "민감성" in skin_type and metric_name in ("elasticity_mean", "wrinkle_value", "wrinkle_grade"):
        tip = tip.replace("권장", "권장 (민감성 → 저농도부터)")
    return tip


if __name__ == "__main__":
    # Self-test
    sample_reg = {
        "moisture": 38.5,
        "elasticity_mean": 0.62,
        "pore_value": 180,
        "pigmentation_value": 22,
        "wrinkle_value": 2.8,
    }
    sample_cls = {
        "wrinkle_grade": 2,
        "pigmentation_grade": 1,
        "pore_grade": 2,
        "dryness_grade": 1,
        "sagging_grade": 3,
    }
    sample_user = {
        "skin_type": "복합성",
        "sensitivity": 2,
        "aging_score": 2,
        "lifestyle_flags": {"sleep": "fair", "sunscreen": "occasional"},
    }
    result = generate_narrative("L_CHEEK", sample_reg, sample_cls, sample_user)
    print("Summary:", result["summary"])
    print(f"Overall: {result['overall_score']}점 (good {result['good_count']} / fair {result['fair_count']} / poor {result['poor_count']})")
    print("Per-metric:")
    for m in result["per_metric"]:
        print(f"  {m['name']:20s} {m['value']:10s} [{m['rating_text']}]")
    print("Tips:")
    for t in result["tips"]:
        print(f"  - {t}")
