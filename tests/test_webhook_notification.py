"""Discord webhook payload formatting tests."""

from __future__ import annotations

import asyncio
import threading

import pytest

from app.services import webhook_notification as webhook


@pytest.mark.parametrize("event_type", sorted(webhook.ALLOWED_WEBHOOK_EVENTS))
def test_notify_pipeline_event_allows_production_events(monkeypatch, event_type: str) -> None:
    captured: dict = {}

    async def _fake_send(embed: dict) -> None:
        captured.update(embed)

    monkeypatch.setattr(webhook, "_send_embed", _fake_send)

    asyncio.run(
        webhook.notify_pipeline_event(
            event_type=event_type,
            severity="warning",
            stage="demo.stage",
            status="RUNNING",
            title="Demo Event",
            message="stage event",
            job_id="job-1",
            elapsed_ms=123,
            model="gpt-demo",
            fallback_used=False,
            error="boom",
            extra_fields=[{"name": "Custom", "value": "value", "inline": True}],
        )
    )

    fields = {field["name"]: field["value"] for field in captured["fields"]}
    assert captured["title"] == "Demo Event"
    assert fields["event_type"] == event_type
    assert fields["severity"] == "warning"
    assert fields["stage"] == "demo.stage"
    assert fields["status"] == "RUNNING"
    assert fields["job_id"] == "`job-1`"
    assert fields["message"] == "stage event"
    assert fields["elapsed_ms"] == "123ms"
    assert fields["model"] == "gpt-demo"
    assert fields["fallback_used"] == "False"
    assert "boom" in fields["error"]
    assert fields["Custom"] == "value"


def test_notify_pipeline_event_skips_non_production_events(monkeypatch) -> None:
    sent = {"value": False}

    async def _fake_send(embed: dict) -> None:
        sent["value"] = True

    monkeypatch.setattr(webhook, "_send_embed", _fake_send)

    asyncio.run(
        webhook.notify_pipeline_event(
            event_type="llm_call_success",
            severity="success",
            stage="llm",
            status="SUCCESS",
            title="Skipped",
            message="not a production event",
        )
    )

    assert sent["value"] is False


def test_schedule_webhook_uses_daemon_thread_without_running_loop(monkeypatch) -> None:
    started: dict[str, object] = {}

    async def _dummy_coro() -> None:
        return None

    def _raise_no_loop() -> None:
        raise RuntimeError("no running event loop")

    class _FakeThread:
        def __init__(self, *, target, name, daemon) -> None:
            started["target"] = target
            started["name"] = name
            started["daemon"] = daemon

        def start(self) -> None:
            started["started"] = True

    monkeypatch.setattr(webhook.asyncio, "get_running_loop", _raise_no_loop)
    monkeypatch.setattr(threading, "Thread", _FakeThread)

    coro = _dummy_coro()
    webhook.schedule_webhook(coro)
    coro.close()

    assert started["started"] is True
    assert started["name"] == "discord-webhook"
    assert started["daemon"] is True
