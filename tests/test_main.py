"""애플리케이션 진입점 최소 동작 테스트."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from app.core.config import get_settings


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ACCESS_EXPIRY_MINUTES", "30")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
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


def test_docs_disabled_by_default(monkeypatch) -> None:
    """기본 DOCS_MODE(disabled)에서는 문서 엔드포인트가 비활성화되어야 한다."""
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    client = TestClient(main_module.app)

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_secret_mode_requires_service_secret(monkeypatch) -> None:
    """DOCS_MODE=secret인 경우 서비스 시크릿으로만 문서 접근이 가능해야 한다."""
    _set_required_env(monkeypatch, DOCS_MODE="secret")
    main_module = _load_main_module()

    client = TestClient(main_module.app)

    unauthorized = client.get("/docs")
    assert unauthorized.status_code == 401

    authorized = client.get("/docs", headers={"x-service-secret": "test-service-secret"})
    assert authorized.status_code == 200


def test_security_headers_are_attached(monkeypatch) -> None:
    """기본 보안 헤더가 응답에 포함되어야 한다."""
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    client = TestClient(main_module.app)
    response = client.get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "geolocation=(), microphone=(), camera=()"


def test_cors_allowlist_from_env(monkeypatch) -> None:
    """허용된 Origin에 대해서만 CORS 헤더가 반환되어야 한다."""
    _set_required_env(
        monkeypatch,
        CORS_ALLOW_ORIGINS="https://example.com",
        CORS_ALLOW_METHODS="GET,POST,OPTIONS",
        CORS_ALLOW_HEADERS="Authorization,Content-Type",
    )
    main_module = _load_main_module()

    client = TestClient(main_module.app)
    response = client.get("/", headers={"Origin": "https://example.com"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://example.com"
