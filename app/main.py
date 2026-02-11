"""FastAPI 애플리케이션 진입점."""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api import chat, endpoints, generate
from app.core.logging_config import configure_logging

configure_logging()

app = FastAPI()

app.include_router(endpoints.router)
app.include_router(generate.router)
app.include_router(chat.router)


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


@app.get("/")
def health_check() -> dict:
    """헬스 체크 엔드포인트."""
    return {"status": "ok", "message": "Mohaeng AI Server is running"}
