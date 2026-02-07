"""FastAPI 애플리케이션 진입점."""

from fastapi import FastAPI

from app.api import endpoints, generate

app = FastAPI()

app.include_router(endpoints.router)
app.include_router(generate.router)


@app.get("/")
def health_check() -> dict:
    """서버 상태를 확인합니다."""
    return {"status": "ok", "message": "Mohaeng AI Server is running"}
