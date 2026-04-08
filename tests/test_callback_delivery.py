"""콜백 전송 재시도 유틸 테스트."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.core.config import get_settings
from app.services.callback_delivery import post_callback_with_retry


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
    monkeypatch.setenv("HMAC_SECRET", "test-hmac-secret")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def test_post_callback_with_retry_succeeds_after_retries(monkeypatch) -> None:
    _set_required_env(
        monkeypatch,
        CALLBACK_MAX_RETRIES="2",
        CALLBACK_BACKOFF_BASE_SECONDS="0.5",
        CALLBACK_BACKOFF_MAX_SECONDS="5",
    )

    call_count = {"value": 0}
    sleep_delays: list[float] = []

    async def _fake_post(self, *args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] < 3:
            raise httpx.ConnectError(
                "temporary network issue",
                request=httpx.Request("POST", "https://example.com/callback"),
            )

        request = httpx.Request("POST", "https://example.com/callback")
        return httpx.Response(200, request=request)

    async def _fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    monkeypatch.setattr("app.services.callback_delivery.asyncio.sleep", _fake_sleep)

    result = asyncio.run(
        post_callback_with_retry(
            callback_url="https://example.com/callback",
            payload={"status": "SUCCESS"},
            headers={"x-service-secret": "secret"},
            timeout_seconds=10,
            context={"job_id": "job-1"},
        )
    )

    assert result is True
    assert call_count["value"] == 3
    assert sleep_delays == pytest.approx([0.5, 1.0])


def test_post_callback_with_retry_does_not_retry_non_retryable_4xx(monkeypatch) -> None:
    _set_required_env(
        monkeypatch,
        CALLBACK_MAX_RETRIES="3",
        CALLBACK_BACKOFF_BASE_SECONDS="0.5",
        CALLBACK_BACKOFF_MAX_SECONDS="5",
    )

    call_count = {"value": 0}
    sleep_delays: list[float] = []

    async def _fake_post(self, *args, **kwargs):
        call_count["value"] += 1
        request = httpx.Request("POST", "https://example.com/callback")
        return httpx.Response(400, request=request)

    async def _fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    async def _noop_notify(*args, **kwargs) -> None:
        pass

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    monkeypatch.setattr("app.services.callback_delivery.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("app.services.callback_delivery.notify_callback_failure", _noop_notify)

    result = asyncio.run(
        post_callback_with_retry(
            callback_url="https://example.com/callback",
            payload={"status": "FAILED"},
            headers={"x-service-secret": "secret"},
            timeout_seconds=10,
            context={"job_id": "job-2"},
        )
    )

    assert result is False
    assert call_count["value"] == 1
    assert sleep_delays == []


def test_post_callback_with_retry_does_not_retry_invalid_url(monkeypatch) -> None:
    _set_required_env(
        monkeypatch,
        CALLBACK_MAX_RETRIES="3",
        CALLBACK_BACKOFF_BASE_SECONDS="0.5",
        CALLBACK_BACKOFF_MAX_SECONDS="5",
    )

    call_count = {"value": 0}
    sleep_delays: list[float] = []

    async def _fake_post(self, *args, **kwargs):
        call_count["value"] += 1
        raise httpx.InvalidURL("invalid callback url")

    async def _fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    async def _noop_notify(*args, **kwargs) -> None:
        pass

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    monkeypatch.setattr("app.services.callback_delivery.asyncio.sleep", _fake_sleep)
    monkeypatch.setattr("app.services.callback_delivery.notify_callback_failure", _noop_notify)

    result = asyncio.run(
        post_callback_with_retry(
            callback_url="::invalid-url::",
            payload={"status": "FAILED"},
            headers={"x-service-secret": "secret"},
            timeout_seconds=10,
            context={"job_id": "job-3"},
        )
    )

    assert result is False
    assert call_count["value"] == 1
    assert sleep_delays == []
