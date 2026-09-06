from datetime import date

from pydantic import BaseModel


class ScanCreate(BaseModel):
    """스캔 세션 생성 요청 (측정 설정, 명세 G.3)"""
    scan_area: str = "얼굴 전체"
    uv_mode: bool = False
    # 측정 항목 토글 (G.3.2~5). moisture_on 이 수분/유분 공통 토글.
    moisture_on: bool = True
    pore_on: bool = True
    melanin_on: bool = True
    elasticity_on: bool = True
    # 환경 데이터 (선택)
    temperature: float | None = None
    humidity: float | None = None
    uv_index: str | None = None


class ScanSessionOut(BaseModel):
    session_id: str
    status: str
    scan_area: str | None = None
    total_score: int | None = None
    skin_type_result: str | None = None

    class Config:
        from_attributes = True


class ScanResultOut(BaseModel):
    """5지표 점수. 측정 제외(OFF) 항목은 None → 프론트에서 '-' 처리 (H.2)"""
    moisture: float | None = None
    sebum: float | None = None
    pore: float | None = None
    elasticity: float | None = None
    pigmentation: float | None = None

    class Config:
        from_attributes = True


class AdviceOut(BaseModel):
    summary: str | None = None
    morning_routine: str | None = None
    night_routine: str | None = None
    lifestyle_tips: str | None = None
    next_scan_date: date | None = None

    class Config:
        from_attributes = True


class AnalyzeOut(BaseModel):
    """분석 결과 응답 (분석 직후 상태 + 결과 + 조언).

    is_mock=True 면 예시(데모) 데이터 → FE는 '데모(예시 데이터)' 배지를 표시해야 한다.
    """
    session_id: str
    status: str
    total_score: int | None = None
    skin_type_result: str | None = None
    result: ScanResultOut
    advice: AdviceOut
    is_mock: bool = False   # True=시연용 예시데이터(배지 표시), False=실제 AI 분석
