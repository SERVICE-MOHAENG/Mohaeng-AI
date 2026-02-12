"""애플리케이션 진입점 최소 동작 테스트."""

from __future__ import annotations

import asyncio
import importlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.schemas.recommend import RecommendRequest


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ACCESS_EXPIRY_MINUTES", "30")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("DOCS_MODE", "disabled")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def _load_main_module():
    import app.main as main_module

    return importlib.reload(main_module)


def test_health_check_endpoint(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    client = TestClient(main_module.app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Mohaeng AI Server is running"}


def test_chat_openapi_ack_example(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    schema = main_module.app.openapi()
    examples = schema["paths"]["/api/v1/chat"]["post"]["responses"]["202"]["content"]["application/json"]["examples"]

    assert examples["accepted"]["value"] == {"status": "ACCEPTED", "job_id": "modify-job-12345"}


def test_recommend_openapi_ack_example(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    schema = main_module.app.openapi()
    examples = schema["paths"]["/api/v1/recommend"]["post"]["responses"]["202"]["content"]["application/json"][
        "examples"
    ]

    assert examples["accepted"]["value"] == {"status": "ACCEPTED", "job_id": "recommend-job-12345"}


def test_recommend_schema_accepts_legacy_enum_values() -> None:
    request = RecommendRequest(
        job_id="job-1",
        callback_url="https://example.com/internal",
        weather="OCEAN_BEACH",
        travel_range="SHORT_HAUL",
        travel_style="MODERN_TRENDY",
        budget_level="BALANCED",
        food_personality=["LOCAL_HIDDEN_GEM"],
        main_interests=["SHOPPING_TOUR", "DYNAMIC_ACTIVITY"],
    )

    assert request.weather == "OCEAN_BEACH"
    assert request.travel_range == "SHORT_HAUL"
    assert request.travel_style == "MODERN_TRENDY"
    assert request.budget_level == "BALANCED"
    assert request.food_personality == ["LOCAL_HIDDEN_GEM"]
    assert request.main_interests == ["SHOPPING_TOUR", "DYNAMIC_ACTIVITY"]

    with pytest.raises(ValueError):
        RecommendRequest(
            job_id="job-2",
            callback_url="https://example.com/internal",
            travel_range="ASIA",
        )


def test_docs_disabled_by_default(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    client = TestClient(main_module.app)

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_secret_mode_requires_service_secret(monkeypatch) -> None:
    _set_required_env(monkeypatch, DOCS_MODE="secret")
    main_module = _load_main_module()

    client = TestClient(main_module.app)

    unauthorized = client.get("/docs")
    assert unauthorized.status_code == 401

    authorized = client.get("/docs", headers={"x-service-secret": "test-service-secret"})
    assert authorized.status_code == 200


def test_security_headers_are_attached(monkeypatch) -> None:
    _set_required_env(monkeypatch)
    main_module = _load_main_module()

    client = TestClient(main_module.app)
    response = client.get("/")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "geolocation=(), microphone=(), camera=()"


def test_cors_allowlist_from_env(monkeypatch) -> None:
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


def test_request_timeout_middleware(monkeypatch) -> None:
    _set_required_env(monkeypatch, REQUEST_TIMEOUT_SECONDS="1")
    main_module = _load_main_module()

    @main_module.app.get("/_slow-test")
    async def _slow_test() -> dict:
        await asyncio.sleep(1.2)
        return {"ok": True}

    client = TestClient(main_module.app)
    response = client.get("/_slow-test")

    assert response.status_code == 504
    assert response.json() == {"detail": "요청 처리 시간이 초과되었습니다."}
