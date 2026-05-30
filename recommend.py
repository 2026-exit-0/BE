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
from urllib.parse import quote


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
            "effect": _generate_effect(p, measurement, user_inputs),
            "purchase_url": _purchase_link(p),
            "warnings": _warning_badges(p),
        }
        for p, s in scored[:top_k]
    ]


# ============================================================
# 사용자 친화적 부가 정보 — 효과 / 구매 링크 / 주의 배지
# ============================================================

# 카테고리별 효과 문구 (사용자 친화적 한국어)
CATEGORY_EFFECTS = {
    "보습": "건조한 피부에 깊은 수분",
    "미백": "칙칙한 톤을 환하게",
    "진정": "민감해진 피부 진정",
    "모공": "넓어진 모공을 매끄럽게",
    "탄력": "탄력 있는 피부 결",
}


def _generate_effect(product: dict, measurement: dict, user_inputs: dict) -> str:
    """이 제품으로 기대할 수 있는 효과 — 카드 상단에 표시될 한 줄."""
    cats = product.get("category", []) or []
    phrases = [CATEGORY_EFFECTS[c] for c in cats if c in CATEGORY_EFFECTS]
    if not phrases:
        return "데일리 케어로 피부 컨디션 유지"
    body = " · ".join(phrases[:2])  # 최대 2개
    return f"이 제품으로 {body} 효과를 기대할 수 있어요"


def _purchase_link(product: dict) -> str:
    """구매처 링크. 제품에 명시된 URL 있으면 우선, 없으면 네이버 쇼핑 검색."""
    if product.get("purchase_url"):
        return product["purchase_url"]
    brand = (product.get("brand") or "").strip()
    name = (product.get("name_kr") or product.get("name_en") or "").strip()
    query = f"{brand} {name}".strip()
    if not query:
        return ""
    return f"https://search.shopping.naver.com/search/all?query={quote(query)}"


# 태그/성분명 → 사용자 친화적 라벨 + 위험도 매핑
_TAG_LABEL = {
    "주의성분포함": ("주의 성분 함유", "medium"),
    "알코올": ("알코올 함유", "low"),
    "알코올 함유": ("알코올 함유", "low"),
    "향료": ("향료 함유", "low"),
    "향료 함유": ("향료 함유", "low"),
    "에센셜오일": ("에센셜 오일 함유", "low"),
    "파라벤": ("파라벤 함유", "high"),
}


def _warning_badges(product: dict) -> List[dict]:
    """주의 사항 — 사용자에게 한국어로 쉽게 보여주기 위한 배지 리스트.
    [{label, level}] (level: high / medium / low)
    """
    badges: List[dict] = []
    seen = set()

    def _add(label: str, level: str):
        if label and label not in seen:
            badges.append({"label": label, "level": level})
            seen.add(label)

    # 1) 위험 성분 (식약처 규제 매칭된 것 등)
    for ing in (product.get("risky_ingredients") or []):
        if isinstance(ing, dict):
            ing_label = ing.get("kr") or ing.get("name") or ing.get("inci") or ""
        else:
            ing_label = str(ing)
        if ing_label:
            _add(f"{ing_label} 주의", "high")

    # 2) 태그 기반
    for tag in (product.get("tags") or []):
        if tag in _TAG_LABEL:
            label, level = _TAG_LABEL[tag]
            _add(label, level)

    return badges


# ============================================================

def _generate_reason(product: dict, measurement: dict, user_inputs: dict, weather: Optional[dict]) -> str:
    """추천 이유를 한 줄로 생성. 측정값/사용자입력의 실제 수치 포함해 설득력 ↑."""
    reasons = []
    cats = set(product.get("category", []))

    # 측정값 기반 — 실제 수치 노출
    moisture = measurement.get("moisture")
    if "보습" in cats and moisture is not None:
        if moisture < 30:
            reasons.append(f"수분 {moisture:.0f} 부족 (보습 시급)")
        elif moisture < 45:
            reasons.append(f"수분 {moisture:.0f} 보통 (보충 권장)")

    pig = measurement.get("pigmentation_value")
    pig_grade = measurement.get("pigmentation_grade")
    if "미백" in cats:
        if pig is not None and pig > 30:
            reasons.append(f"색소반점 {int(pig)}개 (관리 권장)")
        elif pig_grade is not None and pig_grade >= 3:
            reasons.append(f"색소 등급 {pig_grade}/5 (개선 필요)")

    pore = measurement.get("pore_value")
    pore_grade = measurement.get("pore_grade")
    if "모공" in cats:
        if pore is not None and pore > 300:
            reasons.append(f"모공 두드러짐 (수치 {int(pore)})")
        elif pore_grade is not None and pore_grade >= 3:
            reasons.append(f"모공 등급 {pore_grade}/5")

    wrinkle = measurement.get("wrinkle_value")
    wrinkle_grade = measurement.get("wrinkle_grade")
    if "탄력" in cats:
        aging = user_inputs.get("aging_score", 0) or 0
        if aging >= 4:
            reasons.append(f"자가 노화 점수 {aging}/5")
        elif wrinkle_grade is not None and wrinkle_grade >= 4:
            reasons.append(f"주름 등급 {wrinkle_grade}/6")

    # 진정 — 민감성 점수 포함
    sensitivity = user_inputs.get("sensitivity", 0) or 0
    if "진정" in cats and sensitivity >= 3:
        reasons.append(f"민감도 {sensitivity}/5 — 자극 최소화")

    # 피부타입 매칭
    skin_type = user_inputs.get("skin_type", "")
    if skin_type and skin_type in product.get("for_skin", []):
        reasons.append(f"{skin_type} 피부 적합")

    # 제품 특성 — 민감도 ≥3 이면 무향 강조
    if sensitivity >= 3 and product.get("fragrance_free"):
        reasons.append("무향 처방")

    # 핵심 성분 1개 강조 (있으면)
    main_ings = product.get("main_ingredients", [])
    if main_ings:
        first_ing = main_ings[0]
        ing_name = first_ing.get("kr") or first_ing.get("inci", "")
        if ing_name and len(ing_name) < 20:
            reasons.append(f"주성분: {ing_name}")

    # 날씨 보정
    if weather:
        humidity = weather.get("humidity")
        if humidity is not None and humidity < 40 and "보습" in cats:
            reasons.append(f"오늘 습도 {int(humidity)}% (건조)")
        uv = weather.get("uv_index")
        if uv is not None and uv >= 7 and product.get("subcategory") == "선크림":
            reasons.append(f"UV 지수 {uv} (강함)")

    return " · ".join(reasons[:4]) if reasons else "범용 케어"


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
