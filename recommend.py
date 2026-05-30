"""제품 추천 알고리즘.

입력:
  - measurement: AI 모델의 회귀/분류 출력
  - user_inputs: 자가진단 (skin_type / sensitivity / aging_score / lifestyle)
  - weather: (옵션) 습도 / UV 지수

처리:
  - Hard filter: 민감성 사용자에 안전한 제품만, skin_type 매칭
  - Soft score: 측정값/사용자 입력/날씨에 따라 카테고리 가산
  - Top K 반환

확장 포인트:
  - score_weights 정교화 (제품별)
  - 가격 필터 (사용자 예산)
  - 카테고리별 1개씩 (다양성)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional


# 제품 DB 로드 (한 번만)
PRODUCT_DB_PATH = Path(__file__).parent / "data" / "products.json"
_PRODUCT_DB: Optional[List[dict]] = None


def get_product_db() -> List[dict]:
    """제품 DB lazy load."""
    global _PRODUCT_DB
    if _PRODUCT_DB is None:
        if not PRODUCT_DB_PATH.exists():
            _PRODUCT_DB = []
        else:
            data = json.loads(PRODUCT_DB_PATH.read_text(encoding="utf-8"))
            _PRODUCT_DB = data.get("products", [])
    return _PRODUCT_DB


# ============================================================
# Hard filter — 탈락 조건
# ============================================================

def _passes_hard_filter(product: dict, user_inputs: dict) -> bool:
    """제품이 사용자에게 적합한가 (탈락 조건)."""
    sensitivity = user_inputs.get("sensitivity", 0) or 0
    skin_type = user_inputs.get("skin_type", "")

    # 민감도 ≥4 → 무향 + 위험성분 없는 제품만
    if sensitivity >= 4:
        if not product.get("fragrance_free", False):
            return False
        if "주의성분포함" in product.get("tags", []):
            return False
        if product.get("risky_ingredients"):
            return False

    # 민감도 ≥3 → 위험성분 제외 (무향은 허용)
    elif sensitivity >= 3:
        if product.get("risky_ingredients"):
            return False

    # 피부타입 매칭 (제품의 for_skin 에 사용자 타입 있어야)
    if skin_type and product.get("for_skin"):
        if skin_type not in product["for_skin"]:
            return False

    return True


# ============================================================
# Soft score — 점수 계산
# ============================================================

def _score(product: dict, measurement: dict, user_inputs: dict, weather: Optional[dict]) -> float:
    """제품에 대한 점수. 높을수록 적합."""
    score = 0.0
    cats = set(product.get("category", []))

    # 측정값 기반 — 약한 헤드일수록 해당 카테고리 가산
    # 회귀 (denormalized): moisture < 40 = 건조, pore_value > 300 = 모공 많음 등
    moisture = measurement.get("moisture", 50)
    pore_value = measurement.get("pore_value", 0)
    pigmentation_value = measurement.get("pigmentation_value", 0)
    wrinkle_value = measurement.get("wrinkle_value", 0)
    elasticity = measurement.get("elasticity_mean", 0.7)

    # 분류 등급 (낮을수록 좋음 — 등급이 높으면 해당 케어 필요)
    dryness_grade = measurement.get("dryness_grade", 0)
    wrinkle_grade = measurement.get("wrinkle_grade", 0)
    pigmentation_grade = measurement.get("pigmentation_grade", 0)
    pore_grade = measurement.get("pore_grade", 0)
    sagging_grade = measurement.get("sagging_grade", 0)

    # 보습 카테고리
    if "보습" in cats:
        if moisture < 30 or dryness_grade >= 3:
            score += 5
        elif moisture < 45:
            score += 3
        else:
            score += 1

    # 미백 카테고리
    if "미백" in cats:
        if pigmentation_value > 30 or pigmentation_grade >= 3:
            score += 5
        elif pigmentation_value > 15 or pigmentation_grade >= 2:
            score += 3
        else:
            score += 1

    # 모공 카테고리
    if "모공" in cats:
        if pore_value > 300 or pore_grade >= 3:
            score += 5
        elif pore_value > 200 or pore_grade >= 2:
            score += 3

    # 진정 카테고리 (민감도 사용자에게 강력 가산)
    if "진정" in cats:
        sens = user_inputs.get("sensitivity", 0) or 0
        if sens >= 4:
            score += 4
        elif sens >= 3:
            score += 2

    # 탄력/항노화 카테고리
    if "탄력" in cats:
        aging = user_inputs.get("aging_score", 0) or 0
        if aging >= 4 or wrinkle_grade >= 4 or sagging_grade >= 4:
            score += 5
        elif aging >= 3 or wrinkle_grade >= 3:
            score += 3

    # 피부타입 정확 매칭 보너스
    skin_type = user_inputs.get("skin_type", "")
    if skin_type and skin_type in product.get("for_skin", []):
        score += 1

    # 무향/저자극 보너스 (민감도 보고)
    sensitivity = user_inputs.get("sensitivity", 0) or 0
    if sensitivity >= 3:
        if product.get("fragrance_free"):
            score += 1
        if "저자극" in product.get("tags", []):
            score += 1

    # 날씨 보정 (옵션)
    if weather:
        humidity = weather.get("humidity", 60)
        uv_index = weather.get("uv_index", 0)
        if humidity < 40 and "보습" in cats:
            score += 1  # 건조한 날엔 보습 우선
        if uv_index >= 7 and product.get("subcategory") == "선크림":
            score += 3

    return score


# ============================================================
# Public API
# ============================================================

def recommend(
    measurement: Dict,
    user_inputs: Dict,
    weather: Optional[Dict] = None,
    top_k: int = 5,
    diversify_by_category: bool = True,
) -> List[Dict]:
    """제품 추천 메인 함수.

    Args:
        measurement: AI 모델 출력 (regression / classification 값)
        user_inputs: 자가진단 결과
        weather: {humidity: 0-100, uv_index: 0-11, ...} (옵션)
        top_k: 반환 개수
        diversify_by_category: True 면 카테고리별 1개씩 (다양성)

    Returns:
        [{name, brand, category, score, ...}] 점수 내림차순
    """
    db = get_product_db()
    if not db:
        return []

    # Hard filter
    candidates = [p for p in db if _passes_hard_filter(p, user_inputs)]

    # Soft score
    scored = [(p, _score(p, measurement, user_inputs, weather)) for p in candidates]
    scored = [(p, s) for p, s in scored if s > 0]
    scored.sort(key=lambda x: -x[1])

    # 다양성: 카테고리별 1개씩
    if diversify_by_category and len(scored) > top_k:
        seen_cats = set()
        diverse = []
        rest = []
        for p, s in scored:
            cat_key = tuple(sorted(p.get("category", [])))
            if cat_key not in seen_cats:
                diverse.append((p, s))
                seen_cats.add(cat_key)
            else:
                rest.append((p, s))
        # 다양화 후 부족하면 나머지로 채움
        result = diverse[:top_k]
        if len(result) < top_k:
            result.extend(rest[:top_k - len(result)])
        scored = result

    # 응답 포맷
    return [
        {
            "id": p["id"],
            "name": p.get("name_kr") or p.get("name_en"),
            "brand": p.get("brand", ""),
            "category": p.get("category", []),
            "subcategory": p.get("subcategory", ""),
            "main_ingredients": [m.get("kr", m.get("inci", "")) for m in p.get("main_ingredients", [])[:3]],
            "fragrance_free": p.get("fragrance_free", False),
            "price_range": p.get("price_range", ""),
            "image_url": p.get("image_url", ""),
            "score": round(s, 2),
            "reason": _generate_reason(p, measurement, user_inputs, weather),
        }
        for p, s in scored[:top_k]
    ]


def _generate_reason(product: dict, measurement: dict, user_inputs: dict, weather: Optional[dict]) -> str:
    """추천 이유를 한 줄로 생성."""
    reasons = []
    cats = set(product.get("category", []))

    if "보습" in cats and measurement.get("moisture", 50) < 35:
        reasons.append("수분 부족")
    if "미백" in cats and measurement.get("pigmentation_value", 0) > 30:
        reasons.append("색소 케어")
    if "모공" in cats and measurement.get("pore_value", 0) > 250:
        reasons.append("모공 두드러짐")
    if "진정" in cats and user_inputs.get("sensitivity", 0) >= 3:
        reasons.append("민감성 안전")
    if "탄력" in cats and (user_inputs.get("aging_score", 0) >= 4):
        reasons.append("노화 케어")

    skin_type = user_inputs.get("skin_type", "")
    if skin_type and skin_type in product.get("for_skin", []):
        reasons.append(f"{skin_type} 적합")

    return " · ".join(reasons[:3]) if reasons else "범용 케어"


if __name__ == "__main__":
    # 간단 self-test
    sample_meas = {
        "moisture": 28, "elasticity_mean": 0.62,
        "pore_value": 320, "pigmentation_value": 35, "wrinkle_value": 3.2,
        "dryness_grade": 3, "pigmentation_grade": 3,
    }
    sample_user = {"skin_type": "건성", "sensitivity": 4, "aging_score": 2}
    sample_weather = {"humidity": 30, "uv_index": 6}

    results = recommend(sample_meas, sample_user, sample_weather, top_k=5)
    print(f"추천 {len(results)}개:")
    for r in results:
        print(f"  [{r['score']:.1f}] {r['brand']} {r['name']}")
        print(f"        카테고리: {', '.join(r['category'])} | 이유: {r['reason']}")
