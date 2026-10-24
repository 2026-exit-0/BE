from pydantic import BaseModel


class RecommendationOut(BaseModel):
    product_id: str
    name_kr: str
    brand: str | None = None
    category: list[str] | None = None
    price: int | None = None
    image_url: str | None = None
    key_ingredients: list | None = None   # 주성분 [{inci, kr}] — 추천 카드 노출용
    efficacy: list[str] | None = None     # 주요 효능 — 추천 카드 노출용
    match_score: float
    reason: str                            # 성분 기반 추천사유
