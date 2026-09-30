from fastapi import Depends, Header, HTTPException
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


def verify_device_key(x_device_key: str | None = Header(None, alias="X-Device-Key")) -> None:
    """HW(ESP32) 중계 서버 전용 인증. 로그인을 못 하는 기기라 고정 키로 검증한다.

    DEVICE_API_KEY 가 비어있으면(미설정) 무조건 거부 — 키 설정을 깜빡해도 열려있지 않도록.
    """
    if not settings.DEVICE_API_KEY or x_device_key != settings.DEVICE_API_KEY:
        raise HTTPException(status_code=401, detail="유효하지 않은 기기 키입니다")


def verify_device_or_user(
    x_device_key: str | None = Header(None, alias="X-Device-Key"),
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> None:
    """기기 키(X-Device-Key) 또는 사용자 JWT 둘 중 하나만 유효하면 통과.

    GET /device/link/{device_id} 처럼 HW 중계서버·FE 양쪽 다 조회해야 하는 엔드포인트용.
    """
    if x_device_key and settings.DEVICE_API_KEY and x_device_key == settings.DEVICE_API_KEY:
        return
    if cred and cred.credentials:
        payload = decode_token(cred.credentials)
        if payload and "sub" in payload and db.query(User).filter(User.user_id == payload["sub"]).first():
            return
    raise HTTPException(status_code=401, detail="인증이 필요합니다 (기기 키 또는 로그인)")
