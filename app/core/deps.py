from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

# auto_error=False → 토큰 없어도 에러 안 내고 None (하이브리드용)
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """현재 로그인 사용자.

    [전환기 하이브리드]
    - Authorization: Bearer <JWT> 있으면 → 토큰 파싱해 실제 유저
    - 토큰 없으면 → 개발용 더미 유저 (FE 로그인 붙기 전 다른 기능 호환)
    FE 로그인 연동이 끝나면 아래 '더미 fallback' 블록만 지우면 완전 전환된다.
    """
    if cred and cred.credentials:
        payload = decode_token(cred.credentials)
        if not payload or "sub" not in payload:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
        user = db.query(User).filter(User.user_id == payload["sub"]).first()
        if not user:
            raise HTTPException(status_code=401, detail="존재하지 않는 사용자입니다")
        return user

    # ── 더미 fallback (전환 완료 시 이 블록 삭제) ──
    user = db.query(User).filter(User.user_id == settings.DEV_USER_ID).first()
    if not user:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    return user
