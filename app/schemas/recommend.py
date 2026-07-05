from pydantic import BaseModel


class RecommendationOut(BaseModel):
    product_id: str
    name_kr: str
    brand: str | None = None
    category: list[str] | None = None
    price: int | None = None
    image_url: str | None = None
    match_score: float
    reason: str
