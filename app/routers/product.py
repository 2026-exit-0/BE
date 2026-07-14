"""제품 조회 (명세 I.2/I.3) — 목록/상세.

추천 계산(생성)은 app/routers/recommend.py 담당. 여기선 "조회"만 담당한다.
인증 불필요 — 누구나 조회 가능한 공개 API.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.product import Product, Wishlist
from app.schemas.product import ProductOut, WishlistOut

router = APIRouter(prefix="/products", tags=["product"])
wishlist_router = APIRouter(prefix="/wishlist", tags=["product"])


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


@router.post("/{product_id}/wishlist", response_model=WishlistOut, status_code=201,
            summary="[I.4] 제품 찜하기")
def add_wishlist(product_id: str, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="제품을 찾을 수 없습니다")

    existing = (db.query(Wishlist)
               .filter(Wishlist.user_id == user.user_id, Wishlist.product_id == product_id)
               .first())
    if existing:
        raise HTTPException(status_code=409, detail="이미 찜한 제품입니다")

    wishlist = Wishlist(user_id=user.user_id, product_id=product_id)
    db.add(wishlist)
    try:
        db.commit()
    except IntegrityError:          # 동시 요청 대비 — UniqueConstraint 로 최종 방어
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 찜한 제품입니다")
    db.refresh(wishlist)

    return WishlistOut(
        product_id=product.product_id,
        name_kr=product.name_kr,
        brand=product.brand,
        price=product.price,
        image_url=product.image_url,
        created_at=wishlist.created_at,
    )


@router.delete("/{product_id}/wishlist", status_code=204, summary="[I.4] 제품 찜취소")
def remove_wishlist(product_id: str, db: Session = Depends(get_db),
                    user=Depends(get_current_user)):
    wishlist = (db.query(Wishlist)
               .filter(Wishlist.user_id == user.user_id, Wishlist.product_id == product_id)
               .first())
    if not wishlist:
        raise HTTPException(status_code=404, detail="찜하지 않은 제품입니다")

    db.delete(wishlist)
    db.commit()


@wishlist_router.get("", response_model=list[WishlistOut], summary="[I.4] 내 찜 목록 조회")
def get_my_wishlist(db: Session = Depends(get_db), user=Depends(get_current_user)):
    wishlists = (db.query(Wishlist)
                .filter(Wishlist.user_id == user.user_id)
                .order_by(Wishlist.created_at.desc())
                .all())
    return [
        WishlistOut(
            product_id=w.product.product_id,
            name_kr=w.product.name_kr,
            brand=w.product.brand,
            price=w.product.price,
            image_url=w.product.image_url,
            created_at=w.created_at,
        )
        for w in wishlists
    ]
