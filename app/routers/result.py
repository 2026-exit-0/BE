from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.crud.scan import pick_image_url
from app.models.scan import ScanSession
from app.schemas.result import ResultOut

router = APIRouter(prefix="/result", tags=["result"])


@router.get("/{session_id}", response_model=ResultOut, summary="[H] 분석 결과 조회")
def get_result(session_id: str, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    # session 소유자 필터 — 남의 세션이면 존재 여부와 무관하게 동일한 404
    session = (db.query(ScanSession)
              .options(joinedload(ScanSession.result), joinedload(ScanSession.images))
              .filter(ScanSession.session_id == session_id, ScanSession.user_id == user.user_id)
              .first())
    if not session or not session.result:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다")

    result = session.result
    images = session.images or []
    return ResultOut(
        id=result.id,
        session_id=result.session_id,
        moisture=result.moisture,
        sebum=result.sebum,
        pore=result.pore,
        elasticity=result.elasticity,
        pigmentation=result.pigmentation,
        white_image_url=pick_image_url(images, "WHITE_LED"),
        uv_image_url=pick_image_url(images, "UV_LED"),
    )
