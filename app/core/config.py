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

    # 날씨 외부 API (없으면 목업 fallback)
    WEATHER_API_KEY: str = ""
    WEATHER_DEFAULT_LAT: float = 37.5665   # 서울
    WEATHER_DEFAULT_LON: float = 126.9780
    WEATHER_CACHE_TTL: int = 1800          # 캐시 30분(초)


settings = Settings()
