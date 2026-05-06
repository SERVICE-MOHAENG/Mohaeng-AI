"""OpenAI base URL configuration tests."""

from __future__ import annotations

import importlib

from app.core.config import Settings, get_settings


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("HMAC_SECRET", "test-hmac-secret")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_openai_base_url_default_is_proxy(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    settings = Settings(
        OPENAI_API_KEY="test-key",
        SERVICE_SECRET="test-service-secret",
        HMAC_SECRET="test-hmac-secret",
    )

    assert settings.OPENAI_BASE_URL == "https://openai-proxy.dsmhs.kr/v1"


def test_openai_base_url_can_be_overridden_by_env(monkeypatch) -> None:
    _set_required_env(monkeypatch, OPENAI_BASE_URL="https://proxy.example.com/v1/")

    settings = get_settings()

    assert settings.OPENAI_BASE_URL == "https://proxy.example.com/v1"


def test_llm_router_passes_openai_base_url_to_chat_openai(monkeypatch) -> None:
    import app.core.llm_router as llm_router

    captured: dict[str, object] = {}

    class _ChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    llm_router.clear_llm_client_cache()
    monkeypatch.setattr(llm_router, "ChatOpenAI", _ChatOpenAI)

    llm_router._get_chat_openai_client(
        "test-model",
        0.0,
        30,
        "test-key",
        "https://openai-proxy.dsmhs.kr/v1",
    )

    assert captured["base_url"] == "https://openai-proxy.dsmhs.kr/v1"


def test_graph_llms_pass_openai_base_url_to_chat_openai(monkeypatch) -> None:
    _set_required_env(monkeypatch, OPENAI_BASE_URL="https://openai-proxy.dsmhs.kr/v1")
    captured: list[dict[str, object]] = []

    class _ChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.append(kwargs)

    for module_name in ("app.graph.chat.llm", "app.graph.roadmap.llm"):
        module = importlib.import_module(module_name)
        module.get_llm.cache_clear()
        monkeypatch.setattr(module, "ChatOpenAI", _ChatOpenAI)
        module.get_llm()

    assert [kwargs["base_url"] for kwargs in captured] == [
        "https://openai-proxy.dsmhs.kr/v1",
        "https://openai-proxy.dsmhs.kr/v1",
    ]
