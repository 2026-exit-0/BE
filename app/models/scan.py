import uuid

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer,
                        Numeric, String, func)
from sqlalchemy.orm import relationship

from app.core.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class ScanSession(Base):
    """스캔 세션 (명세 G, H)"""
    __tablename__ = "scan_sessions"

    session_id = Column(String(36), primary_key=True, default=gen_uuid)
    user_id = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    scanned_at = Column(DateTime, server_default=func.now())
    scan_area = Column(String(50), nullable=True, default="얼굴 전체")   # G.3.1
    uv_mode = Column(Boolean, default=False)
    # 측정 항목 토글 (G.3.2~5)
    moisture_on = Column(Boolean, default=True)
    pore_on = Column(Boolean, default=True)
    melanin_on = Column(Boolean, default=True)
    elasticity_on = Column(Boolean, default=True)
    # 환경 데이터 (분석결과 환경연동)
    temperature = Column(Numeric(4, 1), nullable=True)
    humidity = Column(Numeric(4, 1), nullable=True)
    uv_index = Column(String(10), nullable=True)
    # 비동기 분석 처리 상태 (G.4.2 타임아웃 대응)
    status = Column(String(20), nullable=False, default="pending")  # pending/processing/done/failed
    total_score = Column(Integer, nullable=True)                    # 종합점수 (H.1)
    skin_type_result = Column(String(20), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="scan_sessions")
    result = relationship("ScanResult", back_populates="session", uselist=False, cascade="all, delete-orphan")
    advice = relationship("AiAdvice", back_populates="session", uselist=False, cascade="all, delete-orphan")
    images = relationship("ScanImage", back_populates="session", cascade="all, delete-orphan")
    recommendations = relationship("ProductRecommendation", back_populates="session", cascade="all, delete-orphan")


class ScanResult(Base):
    """분석 결과 5지표 점수 (명세 H.1, H.2, H.4)"""
    __tablename__ = "scan_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("scan_sessions.session_id", ondelete="CASCADE"), unique=True, nullable=False)
    moisture = Column(Numeric(5, 2), nullable=True)       # 수분
    sebum = Column(Numeric(5, 2), nullable=True)          # 유분
    pore = Column(Numeric(5, 2), nullable=True)           # 모공
    elasticity = Column(Numeric(5, 2), nullable=True)     # 탄력
    pigmentation = Column(Numeric(5, 2), nullable=True)   # 색소침착

    session = relationship("ScanSession", back_populates="result")


class ScanImage(Base):
    """스캔 이미지 (명세 G.2, 백색/UV LED)"""
    __tablename__ = "scan_images"

    image_id = Column(String(36), primary_key=True, default=gen_uuid)
    session_id = Column(String(36), ForeignKey("scan_sessions.session_id", ondelete="CASCADE"), nullable=False)
    image_type = Column(String(20), nullable=True)        # WHITE_LED / UV_LED
    image_url = Column(String(500), nullable=False)
    region = Column(String(30), nullable=True)

    session = relationship("ScanSession", back_populates="images")
