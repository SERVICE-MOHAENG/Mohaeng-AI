"""LLM router webhook event tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.core.llm_router import Stage


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("HMAC_SECRET", "test-hmac-secret")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/abc")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def _event_names(payloads: list[dict]) -> list[str]:
    return [
        next(field["value"] for field in payload["fields"] if field["name"] == "event_type")
        for payload in payloads
    ]


def test_invoke_emits_success_webhook(monkeypatch) -> None:
    _set_required_env(monkeypatch, ENABLE_STAGE_LLM_ROUTING="false", LLM_MODEL_NAME="fallback-model")
    import app.core.llm_router as llm_router

    payloads: list[dict] = []

    async def _fake_send(embed: dict) -> None:
        payloads.append(embed)

    class _Client:
        def invoke(self, payload):
            return SimpleNamespace(content="ok")

    monkeypatch.setattr("app.services.webhook_notification._send_embed", _fake_send)
    monkeypatch.setattr(llm_router, "_get_chat_openai_client", lambda *args, **kwargs: _Client())
    monkeypatch.setattr(llm_router, "schedule_webhook", lambda coro: asyncio.run(coro))

    response = llm_router.invoke(Stage.CHAT_RESPONSE, "prompt")

    assert response.content == "ok"
    assert _event_names(payloads) == ["llm_call_success"]


def test_ainvoke_emits_retry_and_fallback_success(monkeypatch) -> None:
    _set_required_env(
        monkeypatch,
        ENABLE_STAGE_LLM_ROUTING="true",
        LLM_MODEL_QUALITY="primary-model",
        LLM_MODEL_NAME="fallback-model",
    )
    import app.core.llm_router as llm_router

    payloads: list[dict] = []

    async def _fake_send(embed: dict) -> None:
        payloads.append(embed)

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def ainvoke(self, payload):
            if self.model == "primary-model":
                raise RuntimeError("primary-fail")
            return SimpleNamespace(content="fallback-ok")

    monkeypatch.setattr("app.services.webhook_notification._send_embed", _fake_send)
    monkeypatch.setattr(llm_router, "_get_chat_openai_client", lambda model, *args, **kwargs: _Client(model))

    response = asyncio.run(llm_router.ainvoke(Stage.ROADMAP_SKELETON, "prompt"))

    assert response.content == "fallback-ok"
    assert _event_names(payloads) == ["llm_call_retry", "llm_fallback_success"]


def test_ainvoke_emits_fallback_failure(monkeypatch) -> None:
    _set_required_env(
        monkeypatch,
        ENABLE_STAGE_LLM_ROUTING="true",
        LLM_MODEL_QUALITY="primary-model",
        LLM_MODEL_NAME="fallback-model",
    )
    import app.core.llm_router as llm_router

    payloads: list[dict] = []

    async def _fake_send(embed: dict) -> None:
        payloads.append(embed)

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def ainvoke(self, payload):
            raise RuntimeError(f"{self.model}-fail")

    monkeypatch.setattr("app.services.webhook_notification._send_embed", _fake_send)
    monkeypatch.setattr(llm_router, "_get_chat_openai_client", lambda model, *args, **kwargs: _Client(model))

    with pytest.raises(RuntimeError, match="fallback-model-fail"):
        asyncio.run(llm_router.ainvoke(Stage.ROADMAP_SKELETON, "prompt"))

    assert _event_names(payloads) == ["llm_call_retry", "llm_fallback_failed"]
