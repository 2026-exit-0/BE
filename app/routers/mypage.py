from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas.mypage import MypageOut, MypageUpdate

router = APIRouter(prefix="/mypage", tags=["mypage"])


@router.get("", response_model=MypageOut, summary="[J.1] 내 프로필 조회")
def get_mypage(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return user


@router.patch("", response_model=MypageOut, summary="[J.1.3] 내 프로필 수정")
def update_mypage(
    data: MypageUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user
