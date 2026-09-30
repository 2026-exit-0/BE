from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수(.env) 로드. 값은 .env 에서 덮어쓴다."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DB (MySQL)
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/damda?charset=utf8mb4"

    # 개발용 더미 유저 (로그인 붙기 전까지 사용)
    DEV_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    # 인증
    JWT_SECRET: str = "change-me"
    JWT_EXPIRE_DAYS: int = 7

    # 소셜 로그인 (provider 앱 등록 후 .env 로 주입)
    KAKAO_CLIENT_ID: str = ""
    KAKAO_CLIENT_SECRET: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # AI 추론 서비스 (비어있으면 실제 분석 불가 → mock 엔드포인트 사용)
    AI_SERVICE_URL: str = ""   # 예: http://ai-server:9000

    # 스캐너(ESP32-CAM) 주소 — /capture(이미지), /status(상태) 제공. 비면 미연결.
    SCANNER_URL: str = ""      # 예: http://192.168.0.30

    # 날씨 외부 API (없으면 목업 fallback)
    WEATHER_API_KEY: str = ""
    WEATHER_DEFAULT_LAT: float = 37.5665   # 서울
    WEATHER_DEFAULT_LON: float = 126.9780
    WEATHER_CACHE_TTL: int = 1800          # 캐시 30분(초)

    # CORS 허용 오리진 (콤마 구분). 배포 FE + 로컬 개발 서버. .env 로 덮어쓰기 가능.
    CORS_ORIGINS: str = "https://damdads.netlify.app,http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # HW(ESP32) 중계 서버 인증 — X-Device-Key 헤더와 비교 (login 못 하는 기기 전용)
    DEVICE_API_KEY: str = ""

    # 웹 스캔 트리거 시 촬영 명령을 전달할 HW 릴레이 서버 (POST /scan-command)
    SCAN_RELAY_URL: str = ""   # 예: http://localhost:8001


settings = Settings()
