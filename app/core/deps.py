from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User


def get_current_user(db: Session = Depends(get_db)) -> User:
    """현재 로그인 사용자.

    [개발 단계] JWT 미구현 → 시드된 더미 유저를 반환한다.
    [추후] 인증 붙일 때 이 함수 '내부만' JWT 파싱으로 교체하면 된다.
           라우터는 Depends(get_current_user) 그대로라 수정 불필요.
    """
    user = db.query(User).filter(User.user_id == settings.DEV_USER_ID).first()
    if not user:
        raise HTTPException(
            status_code=500,
            detail="개발용 더미 유저가 없습니다. `python -m scripts.seed_dev_user` 를 먼저 실행하세요.",
        )
    return user
