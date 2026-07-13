"""제품 조회 (명세 I.2/I.3) — 목록/상세.

추천 계산(생성)은 app/routers/recommend.py 담당. 여기선 "조회"만 담당한다.
인증 불필요 — 누구나 조회 가능한 공개 API.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.product import Product
from app.schemas.product import ProductOut

router = APIRouter(prefix="/products", tags=["product"])


@router.get("", response_model=list[ProductOut], summary="[I] 제품 목록 조회")
def list_products(
    category: str | None = None,
    skin_type: str | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if price_min is not None:
        query = query.filter(Product.price >= price_min)
    if price_max is not None:
        query = query.filter(Product.price <= price_max)

    products = query.all()
    if category:                       # category 는 JSON 리스트 컬럼 → 파이썬에서 포함 여부 필터
        products = [p for p in products if category in (p.category or [])]
    if skin_type:                      # for_skin 도 동일
        products = [p for p in products if skin_type in (p.for_skin or [])]
    return products


@router.get("/{product_id}", response_model=ProductOut, summary="[I] 제품 상세 조회")
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="제품을 찾을 수 없습니다")
    return product
