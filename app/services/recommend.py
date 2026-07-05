"""제품 추천 궁합점수 로직 (명세 I.1, I.3).

설문(피부타입·고민·알레르기·예산) + 스캔 결과 → 제품별 매칭 점수(0~100) 계산.
알레르기 성분 포함 제품은 추천에서 제외한다(I.3.2 안전 필터).

※ 뼈대 버전 — 가중치는 상단 상수로 빼두었으니 튜닝하면 된다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product import Product, ProductRecommendation
from app.models.scan import ScanSession
from app.models.survey import UserSurvey

# 설문 고민(D.1.3) → 제품 카테고리 키워드 매핑
CONCERN_CATEGORY = {
    "여드름": {"트러블", "진정", "모공"},
    "모공": {"모공"},
    "주름": {"주름", "탄력", "안티에이징"},
    "색소침착": {"미백", "브라이트닝", "잡티"},
    "탄력": {"탄력", "주름", "안티에이징"},
    "건조": {"보습"},
}

# 가중치
W_SKIN_TYPE = 30      # 피부타입 적합
W_CONCERN = 20        # 고민 1건당
W_CONCERN_MAX = 40    # 고민 점수 상한
W_BUDGET_IN = 20      # 예산 범위 내
W_BUDGET_NEAR = 10    # 예산 근접(±20%)
W_LOW_IRRITANT = 10   # 민감성 + 저자극


def _has_allergen(product: Product, allergies: list[str]) -> bool:
    if not allergies or not product.ingredients:
        return False
    names = []
    for ing in product.ingredients:
        if isinstance(ing, dict):
            names += [str(ing.get("kr", "")), str(ing.get("inci", ""))]
        else:
            names.append(str(ing))
    blob = " ".join(names)
    return any(a and a in blob for a in allergies)


def score_product(product: Product, survey: UserSurvey | None,
                  skin_type_fallback: str | None = None):
    """(점수, 이유) 반환. 알레르기 포함 제품은 (None, 사유)로 제외 신호."""
    allergies = (survey.allergies if survey else None) or []
    if _has_allergen(product, allergies):
        return None, "알레르기 성분 포함"

    reasons: list[str] = []
    score = 0
    skin_type = (survey.skin_type if survey else None) or skin_type_fallback
    cats = set(product.category or [])

    # 1) 피부타입 적합
    if skin_type and skin_type in (product.for_skin or []):
        score += W_SKIN_TYPE
        reasons.append(f"{skin_type} 피부 적합")

    # 2) 고민 매칭
    concerns = (survey.concerns if survey else None) or []
    matched = [c for c in concerns if cats & CONCERN_CATEGORY.get(c, set())]
    if matched:
        score += min(len(matched) * W_CONCERN, W_CONCERN_MAX)
        reasons.append(f"{'·'.join(matched)} 케어")

    # 3) 예산
    if survey and product.price and survey.budget_min is not None and survey.budget_max is not None:
        lo, hi = survey.budget_min, survey.budget_max
        if lo <= product.price <= hi:
            score += W_BUDGET_IN
            reasons.append("예산 내")
        elif lo * 0.8 <= product.price <= hi * 1.2:
            score += W_BUDGET_NEAR
            reasons.append("예산 근접")

    # 4) 민감성 → 저자극 가점
    if skin_type == "민감성" and product.alcohol_free and product.fragrance_free:
        score += W_LOW_IRRITANT
        reasons.append("저자극")

    score = min(score, 100)
    reason = ", ".join(reasons) or "피부 타입 기반 추천"
    return score, reason


def generate_recommendations(db: Session, session: ScanSession, top_n: int = 10):
    """세션 소유자의 설문+스캔결과로 추천을 계산·저장하고 (rec, product) 목록 반환."""
    survey = db.query(UserSurvey).filter(UserSurvey.user_id == session.user_id).first()
    fallback = session.skin_type_result

    scored = []
    for product in db.query(Product).all():
        s, reason = score_product(product, survey, fallback)
        if s is None:
            continue  # 알레르기 제외
        scored.append((s, reason, product))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    # 기존 추천 삭제 후 재생성 (재분석 대응)
    (db.query(ProductRecommendation)
       .filter(ProductRecommendation.session_id == session.session_id)
       .delete())

    pairs = []
    for s, reason, product in top:
        rec = ProductRecommendation(
            session_id=session.session_id,
            product_id=product.product_id,
            match_score=s,
            reason=reason,
        )
        db.add(rec)
        pairs.append((rec, product))
    db.commit()
    return pairs
