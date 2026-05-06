"""Readiness 체크 유틸 테스트."""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.readiness import collect_readiness_status


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("HMAC_SECRET", "test-hmac-secret")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_collect_readiness_status_ready_when_google_places_key_missing(monkeypatch) -> None:
    _set_required_env(monkeypatch, GOOGLE_PLACES_API_KEY="")

    async def _fake_tcp(*args, **kwargs):
        return {"status": "ok", "ok": True, "required": True, "detail": "mock-ok"}

    monkeypatch.setattr("app.core.readiness._check_tcp_connectivity", _fake_tcp)

    result = asyncio.run(collect_readiness_status())

    assert result["status"] == "ready"
    assert result["checks"]["openai"]["status"] == "ok"
    assert result["checks"]["google_places"]["status"] == "skip"


def test_collect_readiness_status_ready_when_google_places_key_exists(monkeypatch) -> None:
    _set_required_env(monkeypatch, GOOGLE_PLACES_API_KEY="test-google-key")

    async def _fake_tcp(*args, **kwargs):
        return {"status": "ok", "ok": True, "required": True, "detail": "mock-ok"}

    monkeypatch.setattr("app.core.readiness._check_tcp_connectivity", _fake_tcp)

    result = asyncio.run(collect_readiness_status())

    assert result["status"] == "ready"
    assert result["checks"]["openai"]["status"] == "ok"
    assert result["checks"]["google_places"]["status"] == "ok"


def test_collect_readiness_status_not_ready_when_openai_key_missing(monkeypatch) -> None:
    _set_required_env(monkeypatch, OPENAI_API_KEY="")

    async def _fake_tcp(*args, **kwargs):
        return {"status": "ok", "ok": True, "required": True, "detail": "mock-ok"}

    monkeypatch.setattr("app.core.readiness._check_tcp_connectivity", _fake_tcp)

    result = asyncio.run(collect_readiness_status())

    assert result["status"] == "not_ready"
    assert result["checks"]["openai"]["status"] == "fail"


def test_collect_readiness_status_checks_openai_base_url_host(monkeypatch) -> None:
    _set_required_env(
        monkeypatch,
        GOOGLE_PLACES_API_KEY="",
        OPENAI_BASE_URL="https://openai-proxy.dsmhs.kr/v1",
    )
    calls: list[dict] = []

    async def _fake_tcp(**kwargs):
        calls.append(kwargs)
        return {"status": "ok", "ok": True, "required": True, "detail": "mock-ok"}

    monkeypatch.setattr("app.core.readiness._check_tcp_connectivity", _fake_tcp)

    result = asyncio.run(collect_readiness_status())

    assert result["status"] == "ready"
    assert len(calls) == 1
    assert calls[0]["host"] == "openai-proxy.dsmhs.kr"
    assert calls[0]["port"] == 443
    assert calls[0]["label"] == "OpenAI API"
