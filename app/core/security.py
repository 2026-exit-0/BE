"""인증 유틸 — 비밀번호 해싱 + JWT 발급/검증 (명세 C)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


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
