"""FastAPI 애플리케이션 진입점."""

from fastapi import FastAPI

from app.api import endpoints, generate
from app.core.logging_config import configure_logging

configure_logging()

app = FastAPI()

app.include_router(endpoints.router)
app.include_router(generate.router)


@app.get("/")
def health_check() -> dict:
    """헬스 체크 엔드포인트."""
    return {"status": "ok", "message": "Mohaeng AI Server is running"}
