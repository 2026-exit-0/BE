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
    # HW(ESP32) 연동 — 기기 전용 트리거로 생성된 세션 구분
    source = Column(String(20), nullable=False, default="web")     # web / hardware
    device_id = Column(String(50), nullable=True)                  # 촬영에 쓰인 기기 (web 세션도 기록 가능)

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


class DeviceConnection(Base):
    """기기-사용자 연결 (명세 HW) — device_id 당 '현재' 연결 1건만 유지, 이력 아님.

    연결(link) 시 UPSERT: 기존 연결 있으면 덮어씀. 촬영 시작 시점에 트리거가 이 값을 읽어
    세션 소유자를 확정하므로, 이후 기기 사용자가 바뀌어도 이미 만든 세션은 영향받지 않는다.
    """
    __tablename__ = "device_connections"

    device_id = Column(String(50), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    connected_at = Column(DateTime, server_default=func.now())

    user = relationship("User")
