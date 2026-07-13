from pydantic import BaseModel


class WeatherOut(BaseModel):
    region: str
    temperature: float        # 기온(℃)
    humidity: float           # 습도(%)
    uv_index: str             # 자외선: 낮음/보통/높음/매우높음
    skin_moisture: int        # 피부 수분 지수(0~100)
    skin_dryness: int         # 건조 지수(0~100)
    skin_uv: int              # 자외선 부담 지수(0~100)
    advice: str               # 오늘의 케어 조언
    is_mock: bool = False     # 목업 fallback 여부
