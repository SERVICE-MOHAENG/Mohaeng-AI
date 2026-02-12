"""콜백 전송 재시도 유틸 테스트."""

from __future__ import annotations

import asyncio

import pytest
import requests

from app.core.config import get_settings
from app.services.callback_delivery import post_callback_with_retry


def _set_required_env(monkeypatch, **overrides: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ACCESS_EXPIRY_MINUTES", "30")
    monkeypatch.setenv("SERVICE_SECRET", "test-service-secret")
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

    def _fake_post(*args, **kwargs):
        call_count["value"] += 1
        if call_count["value"] < 3:
            raise requests.ConnectionError("temporary network issue")

        class _Response:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:
                return None

        return _Response()

    async def _fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr("app.services.callback_delivery.requests.post", _fake_post)
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

    def _fake_post(*args, **kwargs):
        call_count["value"] += 1

        class _Response:
            status_code = 400

            @staticmethod
            def raise_for_status() -> None:
                response = requests.Response()
                response.status_code = 400
                raise requests.HTTPError("bad request", response=response)

        return _Response()

    async def _fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr("app.services.callback_delivery.requests.post", _fake_post)
    monkeypatch.setattr("app.services.callback_delivery.asyncio.sleep", _fake_sleep)

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

    def _fake_post(*args, **kwargs):
        call_count["value"] += 1
        raise requests.exceptions.InvalidURL("invalid callback url")

    async def _fake_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr("app.services.callback_delivery.requests.post", _fake_post)
    monkeypatch.setattr("app.services.callback_delivery.asyncio.sleep", _fake_sleep)

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
