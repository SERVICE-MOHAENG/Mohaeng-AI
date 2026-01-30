from fastapi import FastAPI

from app.routers import search

app = FastAPI()

app.include_router(search.router)


@app.get("/")
def health_check() -> dict:
    """서버의 현재 동작 상태를 확인합니다.

    Returns:
        dict: 서버가 정상적으로 실행 중임을 나타내는 상태 메시지.
    """
    return {"status": "ok", "message": "Mohaeng AI Server is running 🚀"}
