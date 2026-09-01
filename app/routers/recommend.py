"""제품 추천 생성 (명세 I.1) — 스캔 세션 기반.

조회·필터(I.2/I.3 목록)는 박수빈 담당. 여기선 "생성(계산·저장)"만 담당한다.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.product import Product, ProductRecommendation
from app.models.scan import ScanSession
from app.schemas.recommend import RecommendationOut
from app.services.recommend import generate_recommendations

router = APIRouter(prefix="/scans", tags=["product"])


def _to_out(rec: ProductRecommendation, product: Product) -> RecommendationOut:
    return RecommendationOut(
        product_id=product.product_id,
        name_kr=product.name_kr,
        brand=product.brand,
        category=product.category,
        price=product.price,
        image_url=product.image_url,
        match_score=float(rec.match_score),
        reason=rec.reason,
    )


def _get_owned_session(db: Session, session_id: str, user_id: str) -> ScanSession | None:
    return (db.query(ScanSession)
           .filter(ScanSession.session_id == session_id, ScanSession.user_id == user_id)
           .first())


@router.post("/{session_id}/recommend", response_model=list[RecommendationOut],
             summary="[I.1] 분석 세션 기반 제품 추천 생성")
def create_recommendations(session_id: str, top_n: int = 10,
                           db: Session = Depends(get_db), user=Depends(get_current_user)):
    session = _get_owned_session(db, session_id, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="스캔 세션을 찾을 수 없습니다")

    pairs = generate_recommendations(db, session, top_n)
    return [_to_out(rec, p) for rec, p in pairs]


@router.get("/{session_id}/recommend", response_model=list[RecommendationOut],
            summary="[I.2] 저장된 추천 결과 조회")
def get_recommendations(session_id: str, db: Session = Depends(get_db),
                        user=Depends(get_current_user)):
    session = _get_owned_session(db, session_id, user.user_id)
    if not session:
        raise HTTPException(status_code=404, detail="스캔 세션을 찾을 수 없습니다")

    # 재계산 없이 저장된 결과만 조회 — product 조인해서 표시용 정보 함께 반환
    pairs = (db.query(ProductRecommendation, Product)
            .join(Product, ProductRecommendation.product_id == Product.product_id)
            .filter(ProductRecommendation.session_id == session_id)
            .order_by(ProductRecommendation.match_score.desc())
            .all())
    if not pairs:
        raise HTTPException(status_code=404, detail="추천 결과가 없습니다")

    return [_to_out(rec, p) for rec, p in pairs]
