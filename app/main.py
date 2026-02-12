"""FastAPI 애플리케이션 진입점."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api import chat, endpoints, generate
from app.api.dependencies import require_service_secret
from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.logging_config import configure_logging

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_docs_mode(mode: str) -> str:
    normalized = (mode or "").strip().lower()
    if normalized in {"disabled", "secret", "public"}:
        return normalized
    logger.warning("유효하지 않은 DOCS_MODE 값입니다. disabled로 대체합니다: %s", mode)
    return "disabled"


def _configure_proxy_headers(app_: FastAPI) -> None:
    if not settings.PROXY_HEADERS_ENABLED:
        return

    trusted_hosts = _split_csv(settings.PROXY_TRUSTED_HOSTS) or ["127.0.0.1"]
    app_.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_hosts)


def _configure_trusted_hosts(app_: FastAPI) -> None:
    trusted_hosts = _split_csv(settings.TRUSTED_HOSTS)
    if not trusted_hosts:
        return

    app_.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)


def _configure_cors(app_: FastAPI) -> None:
    origins = _split_csv(settings.CORS_ALLOW_ORIGINS)
    if not origins:
        return

    allow_methods = _split_csv(settings.CORS_ALLOW_METHODS) or ["GET"]
    allow_headers = _split_csv(settings.CORS_ALLOW_HEADERS) or ["Authorization", "Content-Type"]
    allow_credentials = settings.CORS_ALLOW_CREDENTIALS

    if "*" in origins and allow_credentials:
        logger.warning(
            "CORS_ALLOW_ORIGINS에 '*'와 CORS_ALLOW_CREDENTIALS=true가 함께 설정되어 "
            "allow_credentials를 false로 강제합니다."
        )
        allow_credentials = False

    app_.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
    )


docs_mode = _resolve_docs_mode(settings.DOCS_MODE)

app = FastAPI(
    docs_url="/docs" if docs_mode == "public" else None,
    redoc_url="/redoc" if docs_mode == "public" else None,
    openapi_url="/openapi.json" if docs_mode == "public" else None,
)

_configure_proxy_headers(app)
_configure_trusted_hosts(app)
_configure_cors(app)

app.include_router(endpoints.router)
app.include_router(generate.router)
app.include_router(chat.router)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """기본 보안 헤더를 응답에 추가합니다."""
    response = await call_next(request)
    if not settings.SECURITY_HEADERS_ENABLED:
        return response

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Cache-Control", "no-store")
    if settings.ENABLE_HSTS and request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", f"max-age={settings.HSTS_MAX_AGE_SECONDS}")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """예상하지 못한 예외를 표준 형식으로 처리합니다."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    message = str(exc) if settings.EXPOSE_INTERNAL_ERRORS else "내부 서버 오류가 발생했습니다."
    return JSONResponse(status_code=500, content={"detail": message})


def _inject_chat_null_examples(openapi_schema: dict) -> None:
    """`/api/v1/chat` 응답 예시에 `modified_itinerary: null` 키를 강제 주입합니다."""
    content = (
        openapi_schema.get("paths", {})
        .get("/api/v1/chat", {})
        .get("post", {})
        .get("responses", {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
    )
    examples = content.get("examples", {})
    for example_key in ("rejected_guardrail", "general_chat", "ask_clarification"):
        value = examples.get(example_key, {}).get("value")
        if isinstance(value, dict):
            value.setdefault("modified_itinerary", None)


def custom_openapi() -> dict:
    """OpenAPI 스키마 생성 후 문서 예시를 보정합니다."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    _inject_chat_null_examples(openapi_schema)
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


if docs_mode == "secret":

    @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(require_service_secret)])
    def openapi_json() -> JSONResponse:
        """서비스 시크릿 인증 후 OpenAPI 스키마를 반환합니다."""
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False, dependencies=[Depends(require_service_secret)])
    def swagger_ui() -> Response:
        """서비스 시크릿 인증 후 Swagger UI를 반환합니다."""
        return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")

    @app.get("/redoc", include_in_schema=False, dependencies=[Depends(require_service_secret)])
    def redoc_ui() -> Response:
        """서비스 시크릿 인증 후 ReDoc UI를 반환합니다."""
        return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")


@app.get("/")
def health_check() -> dict:
    """헬스 체크 엔드포인트."""
    return {"status": "ok", "message": "Mohaeng AI Server is running"}
