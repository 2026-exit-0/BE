"""인증 유틸 — 비밀번호 해싱 + JWT 발급/검증 (명세 C)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def _bcrypt_safe(password: str) -> str:
    """bcrypt는 72바이트까지만 사용 → 초과분을 멀티바이트 경계 안전하게 절단.
    (해싱·검증에 동일 적용해 일관성 유지)"""
    return password.encode("utf-8")[:72].decode("utf-8", "ignore")


def hash_password(password: str) -> str:
    return pwd_context.hash(_bcrypt_safe(password))


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(_bcrypt_safe(password), hashed)


def create_access_token(sub: str) -> str:
    """sub(user_id)로 JWT 발급. 만료 JWT_EXPIRE_DAYS."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRE_DAYS)
    return jwt.encode({"sub": sub, "exp": expire}, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """유효하면 payload, 아니면 None."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None
