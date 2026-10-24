"""제품 추천 궁합점수 로직 (명세 I.1, I.3).

설문(피부타입·고민·알레르기·예산) + 스캔 결과 → 제품별 매칭 점수(0~100) 계산.
알레르기 성분 포함 제품은 추천에서 제외한다(I.3.2 안전 필터).
추천사유는 매칭된 고민에 유효한 주성분을 인용해 구체적으로 생성한다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.product import Product, ProductRecommendation
from app.models.scan import ScanSession
from app.models.survey import UserSurvey
from app.schemas.recommend import RecommendationOut

# 설문 고민(D.1.3) → 제품 카테고리 키워드 매핑
CONCERN_CATEGORY = {
    "여드름": {"트러블", "진정", "모공"},
    "모공": {"모공"},
    "주름": {"주름", "탄력", "안티에이징"},
    "색소침착": {"미백", "브라이트닝", "잡티"},
    "탄력": {"탄력", "주름", "안티에이징"},
    "건조": {"보습"},
    "민감": {"진정", "트러블"},
    "진정": {"진정", "트러블"},
}

# 고민별 "효과 있는 주성분" 키워드 — 추천사유 구체화에 사용
CONCERN_INGREDIENTS = {
    "여드름": ["살리실", "티트리", "병풀", "마데카", "센텔라", "징크", "아연", "황련"],
    "모공": ["나이아신아마이드", "살리실", "글라이콜릭", "글루코노락톤", "징크", "아연", "레티놀"],
    "주름": ["레티놀", "레티날", "펩타이드", "아데노신", "콜라겐", "비타민"],
    "탄력": ["펩타이드", "아데노신", "콜라겐", "레티놀", "엘라스틴"],
    "색소침착": ["아스코빅", "비타민", "나이아신아마이드", "알부틴", "트라넥사믹", "글루타티온"],
    "건조": ["하이알루로", "히알루론", "세라마이드", "판테놀", "스쿠알란", "시어버터", "글리세린"],
    "민감": ["병풀", "마데카", "센텔라", "판테놀", "알란토인", "어성초", "시카"],
    "진정": ["병풀", "마데카", "센텔라", "판테놀", "알란토인", "어성초", "시카", "티트리"],
}

# 가중치
W_SKIN_TYPE = 30      # 피부타입 적합
W_CONCERN = 20        # 고민 1건당
W_CONCERN_MAX = 40    # 고민 점수 상한
W_BUDGET_IN = 20      # 예산 범위 내
W_BUDGET_NEAR = 10    # 예산 근접(±20%)
W_LOW_IRRITANT = 10   # 민감성 + 저자극
MAX_PER_CATEGORY = 3  # 상위 추천 내 카테고리 편중 방지


def _ingredient_names(product: Product) -> list[str]:
    names = []
    for ing in (product.ingredients or []):
        if isinstance(ing, dict):
            v = ing.get("kr") or ing.get("inci")
            if v:
                names.append(str(v))
        elif ing:
            names.append(str(ing))
    return names


def _has_allergen(product: Product, allergies: list[str]) -> bool:
    if not allergies:
        return False
    blob = " ".join(_ingredient_names(product)) + " " + (product.full_ingredients or "")
    return any(a and a in blob for a in allergies)


def _cite_ingredients(product: Product, concern: str) -> list[str]:
    """제품 주성분 중 해당 고민에 유효한 성분명(최대 2개)."""
    kws = CONCERN_INGREDIENTS.get(concern, [])
    hits = []
    for name in _ingredient_names(product):
        if any(k in name for k in kws) and name not in hits:
            hits.append(name)
        if len(hits) >= 2:
            break
    return hits


# 고민/카테고리 → 효능 표현 (아/어 연결형, 뒤에 '줍니다'가 붙는다)
FOCUS_BY_CONCERN = {
    "건조": "속당김을 풀어 수분을 채워",
    "모공": "모공과 과잉 피지를 정돈해",
    "색소침착": "칙칙한 톤과 색소 침착을 개선해",
    "주름": "잔주름을 완화하고 탄력을 더해",
    "탄력": "탄력을 끌어올려",
    "여드름": "트러블과 피지를 가라앉혀",
    "민감": "예민하고 붉어진 피부를 진정시켜",
    "진정": "예민하고 붉어진 피부를 진정시켜",
}
FOCUS_BY_CATEGORY = {
    "보습": "수분을 채워", "모공": "모공을 정돈해",
    "미백": "피부 톤을 맑게 해", "브라이트닝": "피부 톤을 맑게 해", "잡티": "잡티를 옅게 해",
    "탄력": "탄력을 더해", "주름": "잔주름을 완화해", "안티에이징": "탄력을 더해",
    "진정": "피부를 진정시켜", "트러블": "트러블을 가라앉혀",
}

# 피부타입별 유익 성분 키워드 (성분 적합도 점수용)
SKIN_INGREDIENTS = {
    "건성": ["하이알루로", "히알루론", "세라마이드", "판테놀", "스쿠알란", "시어버터", "글리세린"],
    "지성": ["나이아신아마이드", "살리실", "글라이콜릭", "징크", "아연", "티트리"],
    "복합성": ["나이아신아마이드", "하이알루로", "판테놀", "세라마이드"],
    "민감성": ["병풀", "마데카", "센텔라", "판테놀", "알란토인", "어성초", "시카"],
}


def _build_reason(product: Product, matched: list[str], skin_type: str | None) -> str:
    """성분·효능 기반 문장형 추천사유 (예산 언급 없음, 제품마다 달라진다)."""
    ings = _ingredient_names(product)[:3]
    ing_txt = "·".join(ings)
    effs = [e for e in (product.efficacy or []) if e][:2]
    if matched:
        focus = FOCUS_BY_CONCERN.get(matched[0], f"{matched[0]} 고민을 케어해")
    else:
        cat = next((c for c in (product.category or []) if c in FOCUS_BY_CATEGORY), None)
        focus = FOCUS_BY_CATEGORY.get(cat, "피부 균형을 잡아")
    skin_txt = f"{skin_type} 피부의 " if skin_type else ""
    if ing_txt and effs:
        return f"{ing_txt} 등 핵심 성분이 {skin_txt}{focus} 주고, {'·'.join(effs)}에도 도움을 줍니다."
    if ing_txt:
        return f"{ing_txt} 등 핵심 성분이 {skin_txt}{focus} 줍니다."
    if effs:
        return f"{'·'.join(effs)} 중심 포뮬러로 {skin_txt}피부를 가꿔 줍니다."
    return f"{skin_txt}{focus} 주는 제품입니다."


def score_product(product: Product, survey: UserSurvey | None,
                  skin_type_fallback: str | None = None):
    """(점수, 이유) 반환. 알레르기 포함 제품은 (None, 사유)로 제외 신호.

    점수는 피부타입·고민·성분 적합도·효능 폭·예산으로 구성돼 제품마다 차등된다.
    추천사유는 예산을 빼고 성분·효능 기반 문장으로 생성한다.
    """
    allergies = (survey.allergies if survey else None) or []
    if _has_allergen(product, allergies):
        return None, "알레르기 성분 포함"

    score = 0
    skin_type = (survey.skin_type if survey else None) or skin_type_fallback
    cats = set(product.category or [])

    # 1) 피부타입 적합
    if skin_type and skin_type in (product.for_skin or []):
        score += W_SKIN_TYPE

    # 2) 고민 매칭
    concerns = (survey.concerns if survey else None) or []
    matched = [c for c in concerns if cats & CONCERN_CATEGORY.get(c, set())]
    if matched:
        score += min(len(matched) * W_CONCERN, W_CONCERN_MAX)

    # 3) 성분 적합도 — 피부타입·고민에 유익한 주성분 수만큼 차등 (50점 고정 방지)
    names = _ingredient_names(product)
    benefit_kws = set(SKIN_INGREDIENTS.get(skin_type or "", []))
    for c in matched:
        benefit_kws |= set(CONCERN_INGREDIENTS.get(c, []))
    if benefit_kws:
        fit = sum(1 for n in names if any(k in n for k in benefit_kws))
        score += min(fit * 4, 20)

    # 4) 효능 폭
    score += min(len(product.efficacy or []) * 2, 6)

    # 5) 예산 (점수에만 반영, 사유 문구에는 넣지 않음)
    if survey and product.price and survey.budget_min is not None and survey.budget_max is not None:
        lo, hi = survey.budget_min, survey.budget_max
        if lo <= product.price <= hi:
            score += W_BUDGET_IN
        elif lo * 0.8 <= product.price <= hi * 1.2:
            score += W_BUDGET_NEAR

    # 6) 민감성 저자극 가점
    if skin_type == "민감성" and product.alcohol_free and product.fragrance_free:
        score += W_LOW_IRRITANT

    score = min(score, 100)
    return score, _build_reason(product, matched, skin_type)


def to_recommendation_out(rec: ProductRecommendation, product: Product) -> RecommendationOut:
    """추천 레코드+제품 → 추천 카드 응답(주성분·효능 포함, 주의성분·링크 제외)."""
    return RecommendationOut(
        product_id=product.product_id,
        name_kr=product.name_kr,
        brand=product.brand,
        category=product.category,
        price=product.price,
        image_url=product.image_url,
        key_ingredients=product.ingredients,
        efficacy=product.efficacy,
        match_score=float(rec.match_score) if rec.match_score is not None else 0.0,
        reason=rec.reason or "피부 타입 기반 추천",
    )


def get_session_recommendations(db: Session, session_id: str) -> list[RecommendationOut]:
    """세션에 저장된 추천을 점수순으로 조회해 응답 형태로 반환 (없으면 빈 리스트)."""
    pairs = (db.query(ProductRecommendation, Product)
             .join(Product, ProductRecommendation.product_id == Product.product_id)
             .filter(ProductRecommendation.session_id == session_id)
             .order_by(ProductRecommendation.match_score.desc())
             .all())
    return [to_recommendation_out(rec, p) for rec, p in pairs]


def _diversify(scored: list, top_n: int) -> list:
    """카테고리별 버킷을 라운드로빈으로 뽑아 5개 카테고리가 고루 들어가게 선정.
    (한 카테고리로 쏠리지 않게 → 필터를 걸어도 카테고리마다 넉넉히 남는다.)"""
    from collections import OrderedDict
    buckets = OrderedDict()
    for item in scored:  # 이미 점수 내림차순
        key = (item[2].category or ["기타"])[0]
        buckets.setdefault(key, []).append(item)
    picked = []
    while len(picked) < top_n and any(buckets.values()):
        for key in list(buckets.keys()):
            b = buckets[key]
            if b:
                picked.append(b.pop(0))
                if len(picked) >= top_n:
                    break
    return picked


def generate_recommendations(db: Session, session: ScanSession, top_n: int = 10):
    """세션 소유자의 설문+스캔결과로 추천을 계산·저장하고 (rec, product) 목록 반환."""
    survey = db.query(UserSurvey).filter(UserSurvey.user_id == session.user_id).first()
    fallback = session.skin_type_result

    scored = []
    for product in db.query(Product).all():
        if not product.image_url:
            continue  # 이미지 없는 제품(구 데이터)은 카드가 비어 보이므로 추천 제외
        s, reason = score_product(product, survey, fallback)
        if s is None:
            continue  # 알레르기 제외
        scored.append((s, reason, product))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = _diversify(scored, top_n)

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
