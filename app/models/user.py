import uuid

from sqlalchemy import Boolean, Column, DateTime, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """사용자 (명세 C, A.4, J.1)"""
    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True, default=gen_uuid)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)            # 소셜 로그인은 NULL
    nickname = Column(String(20), nullable=False)
    login_type = Column(String(10), nullable=False, default="EMAIL")  # EMAIL/KAKAO/GOOGLE
    social_id = Column(String(100), nullable=True)
    profile_image_url = Column(String(500), nullable=True)        # J.1.3
    email_verified = Column(Boolean, nullable=False, default=False)
    # 알림 설정 (J.5.1)
    notify_analysis = Column(Boolean, nullable=False, default=True)
    notify_recommend = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())

    survey = relationship("UserSurvey", back_populates="user", uselist=False, cascade="all, delete-orphan")
    scan_sessions = relationship("ScanSession", back_populates="user", cascade="all, delete-orphan")
    wishlists = relationship("Wishlist", back_populates="user", cascade="all, delete-orphan")
