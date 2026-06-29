from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수(.env) 로드. 값은 .env 에서 덮어쓴다."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DB (MySQL)
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/damda?charset=utf8mb4"

    # 개발용 더미 유저 (로그인 붙기 전까지 사용)
    DEV_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    # 인증(추후 사용)
    JWT_SECRET: str = "change-me"
    JWT_EXPIRE_DAYS: int = 7


settings = Settings()
