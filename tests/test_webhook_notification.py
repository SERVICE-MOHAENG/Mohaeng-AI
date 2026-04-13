"""Discord webhook payload formatting tests."""

from __future__ import annotations

import asyncio

from app.services import webhook_notification as webhook


def test_notify_pipeline_event_builds_standard_fields(monkeypatch) -> None:
    captured: dict = {}

    async def _fake_send(embed: dict) -> None:
        captured.update(embed)

    monkeypatch.setattr(webhook, "_send_embed", _fake_send)

    asyncio.run(
        webhook.notify_pipeline_event(
            event_type="demo_event",
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
    assert fields["event_type"] == "demo_event"
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


def test_notify_job_completed_includes_log_description(monkeypatch) -> None:
    captured: dict = {}

    async def _fake_send(embed: dict) -> None:
        captured.update(embed)

    monkeypatch.setattr(webhook, "_send_embed", _fake_send)

    asyncio.run(
        webhook.notify_job_completed(
            "job-2",
            "generate",
            12.3,
            "SUCCESS",
            [{"stage": "skeleton", "message": "done", "elapsed_ms": 42}],
        )
    )

    fields = {field["name"]: field["value"] for field in captured["fields"]}
    assert captured["title"] == "📋 generate Job Completed"
    assert "**skeleton**" in captured["description"]
    assert "done" in captured["description"]
    assert fields["job_id"] == "`job-2`"
    assert fields["Status"] == "SUCCESS"
    assert fields["Elapsed"] == "12.3s"
