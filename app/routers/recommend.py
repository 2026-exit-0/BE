"""제품 추천 생성 (명세 I.1) — 스캔 세션 기반.

조회·필터(I.2/I.3 목록)는 박수빈 담당. 여기선 "생성(계산·저장)"만 담당한다.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.scan import ScanSession
from app.schemas.recommend import RecommendationOut
from app.services.recommend import generate_recommendations

router = APIRouter(prefix="/scans", tags=["product"])


@router.post("/{session_id}/recommend", response_model=list[RecommendationOut],
             summary="[I.1] 분석 세션 기반 제품 추천 생성")
def create_recommendations(session_id: str, top_n: int = 10,
                           db: Session = Depends(get_db), user=Depends(get_current_user)):
    session = (db.query(ScanSession)
               .filter(ScanSession.session_id == session_id,
                       ScanSession.user_id == user.user_id)
               .first())
    if not session:
        raise HTTPException(status_code=404, detail="스캔 세션을 찾을 수 없습니다")

    pairs = generate_recommendations(db, session, top_n)
    return [
        RecommendationOut(
            product_id=p.product_id,
            name_kr=p.name_kr,
            brand=p.brand,
            category=p.category,
            price=p.price,
            image_url=p.image_url,
            match_score=float(rec.match_score),
            reason=rec.reason,
        )
        for rec, p in pairs
    ]
