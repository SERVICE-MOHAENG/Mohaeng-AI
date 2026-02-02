"""애플리케이션 전역 설정을 관리하는 모듈."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수 기반 설정 모델."""

    DATABASE_URL: str
    OPENAI_API_KEY: str
    JWT_ACCESS_SECRET: str
    JWT_ACCESS_EXPIRY_MINUTES: int

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
