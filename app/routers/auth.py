"""회원 인증 (명세 C) — 이메일 + 소셜(카카오/구글).

셋 다 우리 JWT({access_token, token_type})를 발급 → FE는 동일하게 처리.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import ChangePasswordIn, LoginIn, OAuthIn, SignupIn, TokenOut
from app.services.oauth import exchange_google, exchange_kakao

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=201, summary="[C.3] 이메일 회원가입")
def signup(data: SignupIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다")
    user = User(
        email=data.email,
        nickname=data.nickname,
        password_hash=hash_password(data.password),
        login_type="EMAIL",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user.user_id))


@router.post("/login", response_model=TokenOut, summary="[C.1.1] 이메일 로그인")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 일치하지 않습니다")
    return TokenOut(access_token=create_access_token(user.user_id))


@router.post("/change-password", summary="[J.5.2] 비밀번호 변경")
def change_password(data: ChangePasswordIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not user.password_hash or not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 일치하지 않습니다")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"success": True}


def _upsert_social(db: Session, provider: str, profile: dict) -> User:
    """소셜 프로필로 유저 조회/생성. 같은 이메일이 있으면 연결."""
    social_id = profile.get("social_id")
    user = (db.query(User)
            .filter(User.login_type == provider, User.social_id == social_id)
            .first())
    if user:
        return user

    email = profile.get("email")
    if email:
        existing = db.query(User).filter(User.email == email).first()
        if existing:                       # 기존 계정에 소셜 연결
            if not existing.social_id:
                existing.social_id = social_id
            db.commit()
            return existing

    user = User(
        email=email or f"{provider.lower()}_{social_id}@social.local",
        nickname=profile.get("nickname") or "사용자",
        login_type=provider,
        social_id=social_id,
        email_verified=True,               # 소셜은 provider가 검증
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/kakao", response_model=TokenOut, summary="[C.1.2] 카카오 로그인")
def kakao_login(data: OAuthIn, db: Session = Depends(get_db)):
    profile = exchange_kakao(data.code, data.redirect_uri)
    user = _upsert_social(db, "KAKAO", profile)
    return TokenOut(access_token=create_access_token(user.user_id))


@router.post("/google", response_model=TokenOut, summary="[C.1.2] 구글 로그인")
def google_login(data: OAuthIn, db: Session = Depends(get_db)):
    profile = exchange_google(data.code, data.redirect_uri)
    user = _upsert_social(db, "GOOGLE", profile)
    return TokenOut(access_token=create_access_token(user.user_id))
