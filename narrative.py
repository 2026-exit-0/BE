"""측정값 → 자연어 평가 / 종합 narrative 생성.

목적:
  - raw 수치만 보여주면 사용자 인지 부담 큼 ("Ra=2.8이 좋은건가 나쁜건가?")
  - 사용자 입력 (피부타입/민감도/노화) 을 단순 echo 가 아니라 평가/tip 에 반영
  - 각 metric 에 description + personalized_note 제공 (FE tooltip 용)
"""

from __future__ import annotations

from typing import Dict, List, Optional


# ============================================================
# 평가 기준 (placeholder — 실제 도메인 기준으로 조정 필요)
# ============================================================

THRESHOLDS_LOWER_BETTER = {
    "pore_value": {"good": 200, "fair": 350, "poor": 500},
    "pigmentation_value": {"good": 15, "fair": 30, "poor": 50},
    "wrinkle_value": {"good": 2.5, "fair": 4.0, "poor": 6.0},
}

THRESHOLDS_HIGHER_BETTER = {
    "moisture": {"good": 50, "fair": 35, "poor": 20},
    "elasticity_mean": {"good": 0.7, "fair": 0.55, "poor": 0.4},
}

GRADE_RATINGS = {
    "wrinkle_grade": {"good_max": 2, "fair_max": 4, "max": 6},
    "pigmentation_grade": {"good_max": 1, "fair_max": 3, "max": 5},
    "pore_grade": {"good_max": 1, "fair_max": 3, "max": 5},
    "dryness_grade": {"good_max": 1, "fair_max": 2, "max": 4},
    "sagging_grade": {"good_max": 2, "fair_max": 4, "max": 6},
}


# ============================================================
# 메타 정보 — UI 표시용
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

# metric 별 설명 — FE tooltip 표시용
DESCRIPTIONS = {
    "moisture": "피부 수분 정도. 높을수록 촉촉함 (0~100). FDC2112 센서 기반",
    "elasticity_mean": "피부 탄력성 (Cutometer R0~R9 평균). 0~1, 높을수록 탄력 좋음",
    "pore_value": "모공 개수 추정값. 낮을수록 매끈한 피부",
    "pigmentation_value": "색소반점 / 잡티 개수. 낮을수록 깨끗한 피부",
    "wrinkle_value": "주름 거칠기 평균 Ra (μm). 낮을수록 매끈",
    "wrinkle_grade": "주름 정도 등급 (0~6). 낮을수록 주름 적음",
    "pigmentation_grade": "색소 침착 정도 등급 (0~5). 낮을수록 깨끗",
    "pore_grade": "모공 두드러짐 등급 (0~5). 낮을수록 작은 모공",
    "dryness_grade": "건조도 등급 (0~4). 낮을수록 촉촉",
    "sagging_grade": "처짐 정도 등급 (0~6). 낮을수록 탄력 있음",
    "skin_type": "피부 타입 (건성/지성/복합성/민감성/중성). 사용자 자가 입력",
    "sensitive": "민감성 여부. 1~5 단계로 사용자 자가 입력",
}


# ============================================================
# 평가 함수
# ============================================================

def rate_regression(name: str, value: float) -> str:
    if name in THRESHOLDS_LOWER_BETTER:
        t = THRESHOLDS_LOWER_BETTER[name]
        if value <= t["good"]: return "good"
        if value <= t["fair"]: return "fair"
        return "poor"
    if name in THRESHOLDS_HIGHER_BETTER:
        t = THRESHOLDS_HIGHER_BETTER[name]
        if value >= t["good"]: return "good"
        if value >= t["fair"]: return "fair"
        return "poor"
    return "fair"


def rate_grade(name: str, grade: int) -> str:
    if name not in GRADE_RATINGS:
        return "fair"
    t = GRADE_RATINGS[name]
    if grade <= t["good_max"]: return "good"
    if grade <= t["fair_max"]: return "fair"
    return "poor"


# ============================================================
# 개인화 — 사용자 입력이 평가/tip 에 영향
# ============================================================

def _personalize_metric(name: str, rating: str, user_inputs: dict) -> Optional[str]:
    """개별 metric 에 대한 사용자 맞춤 한 줄 평. FE tooltip 의 두 번째 줄로 표시.

    사용자 입력 (skin_type, sensitivity, aging_score) 를 보고 해당 metric 결과를
    개인 맥락에서 해석.
    """
    skin_type = user_inputs.get("skin_type", "")
    sensitivity = user_inputs.get("sensitivity", 0) or 0
    aging = user_inputs.get("aging_score", 0) or 0

    # 민감성 우선 — 모든 metric 에 영향
    if sensitivity >= 4:
        if name in ("pore_value", "pore_grade") and rating == "poor":
            return "민감성 케어 — BHA 대신 효소 필링 권장"
        if name in ("wrinkle_value", "wrinkle_grade") and rating != "good":
            return "민감성 — 저농도 레티놀 (0.025%) 부터 시작 권장"
        if name in ("pigmentation_value", "pigmentation_grade") and rating != "good":
            return "민감성 — 비타민C 대신 나이아신아마이드 권장"

    # 피부타입별 맥락
    if skin_type == "건성":
        if name == "moisture" and rating == "poor":
            return "건성 피부엔 흔한 결과. 히알루론산 + 세라마이드 보습 권장"
        if name == "dryness_grade" and rating != "good":
            return "건성 피부 특성. 오일 또는 크림 추가 권장"
    elif skin_type == "지성":
        if name in ("pore_value", "pore_grade") and rating != "good":
            return "지성 피부 특성. 클레이 마스크 주 1-2회 권장"
        if name == "moisture" and rating == "good":
            return "지성도 수분 부족 가능 — 수분만 보충 (오일 X)"
    elif skin_type == "복합성":
        if name in ("pore_value", "pore_grade"):
            return "T존 집중 케어 (BHA), U존은 보습 우선"
    elif skin_type == "민감성":
        if rating != "good":
            return "민감성 — 새 제품 도입 시 패치 테스트 필수"

    # 노화 점수 높음
    if aging >= 4:
        if name in ("wrinkle_value", "wrinkle_grade"):
            return "노화 진행 — 펩타이드 + 레티놀 야간 케어 우선"
        if name == "sagging_grade":
            return "노화 진행 — 마사지 + 탄력 케어 권장"

    return None


def _tip_for_metric(metric_name: str, rating: str, user_inputs: dict) -> Optional[str]:
    """약점 metric 에 대한 케어 tip (사용자 입력 반영)."""
    skin_type = user_inputs.get("skin_type", "")
    sensitivity = user_inputs.get("sensitivity", 0) or 0

    base_tips = {
        "moisture": "히알루론산 / 세라마이드 함유 보습제 권장",
        "elasticity_mean": "펩타이드 / 콜라겐 함유 제품 권장",
        "pore_value": "BHA (살리실산) 또는 클레이 마스크",
        "pigmentation_value": "비타민 C 세럼 + 자외선 차단 필수",
        "wrinkle_value": "레티놀 / 펩타이드 야간 케어",
        "wrinkle_grade": "레티놀 / 펩타이드 야간 케어",
        "pigmentation_grade": "비타민 C 세럼 + 자외선 차단 필수",
        "pore_grade": "BHA 또는 클레이 마스크",
        "dryness_grade": "보습 강화 (오일 / 크림)",
        "sagging_grade": "마사지 + 탄력 케어 (펩타이드)",
    }
    tip = base_tips.get(metric_name)
    if not tip:
        return None

    # 민감성 보정
    if sensitivity >= 4:
        if "레티놀" in tip:
            tip = tip.replace("레티놀", "저농도 레티놀 (0.025%)")
        if "BHA" in tip:
            tip = tip.replace("BHA", "효소 필링 (BHA 자극 시)")
        if "비타민 C 세럼" in tip:
            tip = tip.replace("비타민 C 세럼", "나이아신아마이드 (비타민C 대안)")

    # 건성 보정
    if skin_type == "건성" and "클레이" in tip:
        tip = tip.replace("클레이 마스크", "유분 흡수 토너 (클레이 자극 시)")

    return tip


def _skin_type_note(skin_type: str) -> Optional[str]:
    notes = {
        "건성": "수분/유분 모두 부족. 보습 강화 + 자극 최소화",
        "지성": "유분 과다, 수분은 부족할 수 있음. 수분 토너 + 유분 조절",
        "복합성": "T존 (유분) vs U존 (건조) 차등 케어",
        "민감성": "새 제품 패치 테스트 필수. 향료 / 알코올 적은 제품",
        "중성": "현재 밸런스 유지가 핵심",
    }
    return notes.get(skin_type)


def _sensitivity_note(sens: int) -> Optional[str]:
    if sens <= 1: return "민감도 낮음 — 강한 활성 성분 사용 가능"
    if sens <= 2: return "민감도 보통 — 일반 케어 OK, 새 제품 도입 신중"
    if sens <= 3: return "민감도 약간 높음 — 저자극 라인 권장"
    if sens <= 4: return "민감도 높음 — 향료 / 알코올 / 강한 산성 피하기"
    return "매우 민감 — 피부과 전문 라인 권장"


# ============================================================
# Narrative 생성
# ============================================================

def generate_narrative(
    region: str,
    regression: Dict[str, float],
    classification: Dict[str, int],
    user_inputs: Optional[dict] = None,
) -> dict:
    user_inputs = user_inputs or {}
    per_metric: List[dict] = []
    good_count = 0
    fair_count = 0
    poor_count = 0
    tips: List[str] = []

    # 회귀 측정값
    for name, value in regression.items():
        rating = rate_regression(name, value)
        per_metric.append({
            "name": UNIT_LABELS.get(name, name),
            "raw_name": name,
            "value": f"{value:.2f}",
            "rating": rating,
            "rating_text": RATING_TEXT[rating],
            "description": DESCRIPTIONS.get(name, ""),
            "personalized_note": _personalize_metric(name, rating, user_inputs),
        })
        if rating == "good": good_count += 1
        elif rating == "fair": fair_count += 1
        else: poor_count += 1

    # 분류 등급 (skin_type / sensitive 는 user_inputs 로 대체)
    for name, grade in classification.items():
        if name in ("skin_type", "sensitive"):
            continue
        rating = rate_grade(name, grade)
        per_metric.append({
            "name": UNIT_LABELS.get(name, name),
            "raw_name": name,
            "value": f"{grade}",
            "rating": rating,
            "rating_text": RATING_TEXT[rating],
            "description": DESCRIPTIONS.get(name, ""),
            "personalized_note": _personalize_metric(name, rating, user_inputs),
        })
        if rating == "good": good_count += 1
        elif rating == "fair": fair_count += 1
        else: poor_count += 1

    # 사용자 입력 표시 (info)
    if user_inputs.get("skin_type"):
        per_metric.append({
            "name": UNIT_LABELS["skin_type"],
            "raw_name": "skin_type",
            "value": user_inputs["skin_type"],
            "rating": "info",
            "rating_text": "(사용자 입력)",
            "description": DESCRIPTIONS["skin_type"],
            "personalized_note": _skin_type_note(user_inputs["skin_type"]),
        })
    if "sensitivity" in user_inputs:
        sens = user_inputs["sensitivity"]
        per_metric.append({
            "name": UNIT_LABELS["sensitive"],
            "raw_name": "sensitive",
            "value": f"{sens}/5",
            "rating": "info",
            "rating_text": "(사용자 입력)",
            "description": DESCRIPTIONS["sensitive"],
            "personalized_note": _sensitivity_note(sens),
        })

    # 종합 점수 (객관 측정값만 — 사용자 입력은 narrative 개인화에만 영향)
    total_evaluated = good_count + fair_count + poor_count
    if total_evaluated > 0:
        overall_score = int((good_count * 100 + fair_count * 60 + poor_count * 30) / total_evaluated)
    else:
        overall_score = 50

    # Summary (개인화 반영)
    if overall_score >= 80: condition = "매우 양호"
    elif overall_score >= 60: condition = "양호"
    elif overall_score >= 40: condition = "보통"
    else: condition = "주의 필요"

    summary_parts = [f"오늘 {region} 부위 피부 컨디션: {condition} ({overall_score}점)"]

    rated_metrics = [m for m in per_metric if m["rating"] in ("good", "fair", "poor")]
    if rated_metrics:
        best = next((m for m in rated_metrics if m["rating"] == "good"), None)
        worst = next((m for m in rated_metrics if m["rating"] == "poor"), None)
        if best:
            summary_parts.append(f"{best['name']} 우수")
        if worst:
            summary_parts.append(f"{worst['name']} 관리 권장")

    skin_type = user_inputs.get("skin_type", "")
    sens = user_inputs.get("sensitivity", 0) or 0
    if skin_type and sens >= 4:
        summary_parts.append(f"{skin_type} / 민감성 케어 우선")
    elif skin_type:
        summary_parts.append(f"{skin_type} 케어 루틴 권장")

    summary = ". ".join(summary_parts)

    # Tips
    lifestyle = user_inputs.get("lifestyle_flags", {})
    if lifestyle.get("sunscreen") == "rare":
        tips.append("자외선 차단제 매일 사용 — 색소침착 / 노화 예방 1순위")
    elif lifestyle.get("sunscreen") == "occasional" and any(
        m["raw_name"] in ("pigmentation_value", "pigmentation_grade") and m["rating"] != "good"
        for m in per_metric
    ):
        tips.append("색소 관리 시 매일 자외선 차단제 효과적")

    if lifestyle.get("sleep") == "poor":
        tips.append("수면 부족 — 피부 회복력 저하. 7시간 이상 권장")

    for m in rated_metrics:
        if m["rating"] == "poor":
            tip = _tip_for_metric(m["raw_name"], m["rating"], user_inputs)
            if tip:
                tips.append(f"{m['name']}: {tip}")

    return {
        "summary": summary,
        "per_metric": per_metric,
        "tips": tips[:6],
        "overall_score": overall_score,
        "good_count": good_count,
        "fair_count": fair_count,
        "poor_count": poor_count,
        "user_context": {
            "skin_type": user_inputs.get("skin_type"),
            "sensitivity": user_inputs.get("sensitivity"),
            "aging_score": user_inputs.get("aging_score"),
            "applied": bool(user_inputs.get("skin_type") or user_inputs.get("sensitivity")),
        },
    }


if __name__ == "__main__":
    sample_reg = {"moisture": 38.5, "elasticity_mean": 0.62, "pore_value": 180,
                  "pigmentation_value": 22, "wrinkle_value": 2.8}
    sample_cls = {"wrinkle_grade": 2, "pigmentation_grade": 1, "pore_grade": 2,
                  "dryness_grade": 1, "sagging_grade": 3}
    sample_user = {"skin_type": "민감성", "sensitivity": 4, "aging_score": 2,
                   "lifestyle_flags": {"sleep": "fair", "sunscreen": "occasional"}}
    result = generate_narrative("L_CHEEK", sample_reg, sample_cls, sample_user)
    print("Summary:", result["summary"])
    print(f"Overall: {result['overall_score']}점")
    for m in result["per_metric"]:
        note = f" — {m['personalized_note']}" if m.get("personalized_note") else ""
        print(f"  {m['name']:20s} {m['value']:10s} [{m['rating_text']}]{note}")
    for t in result["tips"]:
        print(f"  tip: {t}")
