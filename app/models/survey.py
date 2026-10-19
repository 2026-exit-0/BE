from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserSurvey(Base):
    """피부 설문 (명세 D). 유저당 1개(수정 방식, D.3/J.2)."""
    __tablename__ = "user_surveys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    skin_type = Column(String(10), nullable=False)               # 건성/지성/복합성/민감성 (D.1.2)
    # 인구통계 (선택) — 데모 결과 개인화(연령대별 탄력/색소 베이스라인)에 사용
    age_band = Column(String(10), nullable=True)                 # 10대/20대/30대/40대/50대/60대+
    gender = Column(String(10), nullable=True)                   # 남/여/기타
    concerns = Column(JSON, nullable=True)                       # ["모공","건조"] 최대 3 (D.1.3)
    allergies = Column(JSON, nullable=True)                      # 알레르기 성분 (D.1.4)
    preferred_categories = Column(JSON, nullable=True)           # 선호 카테고리, 선택 (D.1.5)
    budget_min = Column(Integer, nullable=True)                  # 예산 (D.1.6)
    budget_max = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="survey")
