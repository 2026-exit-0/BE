"""회원 인증 1단계 (명세 C) — 이메일 회원가입/로그인 + 비밀번호 변경.

발급 토큰 {access_token, token_type} → FE 그대로 처리.
(소셜 로그인 카카오/구글은 2단계 feat/auth-oauth 에서 추가)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import ChangePasswordIn, LoginIn, SignupIn, TokenOut

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
