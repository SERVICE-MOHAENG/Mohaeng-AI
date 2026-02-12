"""애플리케이션 전역 설정을 관리하는 모듈."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수 기반 설정 모델."""

    DATABASE_URL: str | None = None
    OPENAI_API_KEY: str
    JWT_ACCESS_SECRET: str
    JWT_ACCESS_EXPIRY_MINUTES: int
    SERVICE_SECRET: str
    LLM_MODEL_NAME: str = "gpt-4o-mini"
    REQUEST_TIMEOUT_SECONDS: int = 30
    LLM_TIMEOUT_SECONDS: int = 60
    RECOMMEND_TIMEOUT_SECONDS: int = 45
    RECOMMEND_LLM_TEMPERATURE: float = 0.6
    EXTERNAL_API_TIMEOUT_SECONDS: int = 15
    CALLBACK_TIMEOUT_SECONDS: int = 10
    CALLBACK_MAX_RETRIES: int = 2
    CALLBACK_BACKOFF_BASE_SECONDS: float = 0.5
    CALLBACK_BACKOFF_MAX_SECONDS: float = 5.0
    GOOGLE_PLACES_API_KEY: str | None = None
    GOOGLE_PLACES_TIMEOUT_SECONDS: int = 10
    GOOGLE_PLACES_LANGUAGE_CODE: str = "ko"
    APP_ENV: str = "development"
    DOCS_MODE: str = "disabled"
    EXPOSE_INTERNAL_ERRORS: bool = False
    CORS_ALLOW_ORIGINS: str = ""
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Authorization,Content-Type,x-service-secret"
    CORS_ALLOW_CREDENTIALS: bool = False
    SECURITY_HEADERS_ENABLED: bool = True
    ENABLE_HSTS: bool = False
    HSTS_MAX_AGE_SECONDS: int = 31536000
    PROXY_HEADERS_ENABLED: bool = True
    PROXY_TRUSTED_HOSTS: str = "127.0.0.1"
    TRUSTED_HOSTS: str = ""

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
