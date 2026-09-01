from datetime import datetime

from pydantic import BaseModel


class ProductOut(BaseModel):        # 출력값 (명세 I)
    product_id: str
    name_kr: str
    name_en: str | None = None
    brand: str | None = None
    category: list[str] | None = None
    subcategory: str | None = None
    for_skin: list[str] | None = None
    tags: list[str] | None = None
    price: int | None = None
    price_range: str | None = None
    image_url: str | None = None
    purchase_url: str | None = None
    alcohol_free: bool
    fragrance_free: bool

    class Config:
        from_attributes = True


class WishlistOut(BaseModel):       # 출력값 (명세 I.4) — 제품 정보 + 찜한 시각
    product_id: str
    name_kr: str
    brand: str | None = None
    price: int | None = None
    image_url: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
