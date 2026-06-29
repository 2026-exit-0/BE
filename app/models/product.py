import uuid

from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        Numeric, String, UniqueConstraint, func)
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Product(Base):
    """제품 (명세 I, 데모 products.json 기반)"""
    __tablename__ = "products"

    product_id = Column(String(36), primary_key=True, default=gen_uuid)
    name_kr = Column(String(200), nullable=False)
    name_en = Column(String(200), nullable=True)
    brand = Column(String(100), nullable=True)
    category = Column(JSON, nullable=True)            # ["보습","진정"]
    subcategory = Column(String(50), nullable=True)   # 에센스/토너 등
    ingredients = Column(JSON, nullable=True)         # [{"inci":..,"kr":..}] (알레르기 경고 I.3.2)
    for_skin = Column(JSON, nullable=True)            # ["건성","복합성"]
    tags = Column(JSON, nullable=True)                # ["저자극","BHA"]
    price = Column(Integer, nullable=True)            # 숫자 정규화 (예산 필터 D.1.6)
    price_range = Column(String(20), nullable=True)   # 원본 "1-3만원" 보존
    image_url = Column(String(500), nullable=True)
    purchase_url = Column(String(500), nullable=True) # I.5
    alcohol_free = Column(Boolean, default=False)
    fragrance_free = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    recommendations = relationship("ProductRecommendation", back_populates="product")
    wishlists = relationship("Wishlist", back_populates="product")


class ProductRecommendation(Base):
    """제품 추천 결과 (명세 I.1, I.3) — 분석 세션별 추천"""
    __tablename__ = "product_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("scan_sessions.session_id", ondelete="CASCADE"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False)
    match_score = Column(Numeric(5, 2), nullable=True)  # 궁합 점수
    reason = Column(String(255), nullable=True)         # 추천 이유 (I.3.3)

    session = relationship("ScanSession", back_populates="recommendations")
    product = relationship("Product", back_populates="recommendations")


class Wishlist(Base):
    """찜 (명세 I.4, J.4)"""
    __tablename__ = "wishlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_wishlist_user_product"),)

    user = relationship("User", back_populates="wishlists")
    product = relationship("Product", back_populates="wishlists")
