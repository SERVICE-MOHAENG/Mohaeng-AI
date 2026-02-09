"""애플리케이션 전역 설정을 관리하는 모듈."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수 기반 설정 모델."""

    DATABASE_URL: str
    OPENAI_API_KEY: str
    JWT_ACCESS_SECRET: str
    JWT_ACCESS_EXPIRY_MINUTES: int
    SERVICE_SECRET: str
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS: int = 60
    CALLBACK_TIMEOUT_SECONDS: int = 10
    GOOGLE_PLACES_API_KEY: str | None = None
    GOOGLE_PLACES_TIMEOUT_SECONDS: int = 10
    GOOGLE_PLACES_LANGUAGE_CODE: str = "ko"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Settings 인스턴스를 반환한다. 최초 호출 시에만 생성되고 이후 캐싱된다."""
    return Settings()
