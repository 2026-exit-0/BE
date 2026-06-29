from sqlalchemy import (Column, Date, DateTime, ForeignKey, Integer, String,
                        Text, func)
from sqlalchemy.orm import relationship

from app.core.database import Base


class AiAdvice(Base):
    """AI 케어 조언 (명세 H.3, 케어 가이드 K 연동)"""
    __tablename__ = "ai_advices"

    advice_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("scan_sessions.session_id", ondelete="CASCADE"), unique=True, nullable=False)
    summary = Column(Text, nullable=True)            # AI 진단 요약
    morning_routine = Column(Text, nullable=True)    # 아침 루틴 (K.1.1)
    night_routine = Column(Text, nullable=True)      # 저녁 루틴 (K.1.2)
    lifestyle_tips = Column(Text, nullable=True)     # 생활 습관 조언
    next_scan_date = Column(Date, nullable=True)     # 다음 스캔 권장일
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("ScanSession", back_populates="advice")
