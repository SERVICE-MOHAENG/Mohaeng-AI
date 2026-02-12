"""애플리케이션 진입점 최소 동작 테스트."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from app.core.config import get_settings


def _set_required_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ACCESS_EXPIRY_MINUTES", "30")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    get_settings.cache_clear()


def _load_main_module():
    import app.main as main_module

    return importlib.reload(main_module)


def test_health_check_endpoint(monkeypatch) -> None:
    """루트 헬스체크가 정상 응답을 반환해야 한다."""
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    client = TestClient(main_module.app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Mohaeng AI Server is running"}


def test_chat_openapi_ack_example(monkeypatch) -> None:
    """채팅 API OpenAPI 예시에 ACK 샘플이 포함되어야 한다."""
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    schema = main_module.app.openapi()
    examples = schema["paths"]["/api/v1/chat"]["post"]["responses"]["202"]["content"]["application/json"]["examples"]

    assert examples["accepted"]["value"] == {"status": "ACCEPTED", "job_id": "modify-job-12345"}
