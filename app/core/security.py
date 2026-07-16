"""인증 유틸 — 비밀번호 해싱 + JWT 발급/검증 (명세 C).

해싱은 bcrypt 를 직접 사용한다. (passlib 은 유지보수 중단 + 최신 bcrypt 와
호환성 문제가 있어 사용하지 않음.) bcrypt 는 72바이트까지만 처리하므로
초과 입력은 바이트 단위로 절단한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]              # bcrypt 72바이트 제한
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    pw = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except ValueError:
        return False


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
