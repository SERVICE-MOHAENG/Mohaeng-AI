"""Discord webhook notification service."""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_WEBHOOK_TIMEOUT = httpx.Timeout(10.0)

_COLOR_GREEN = 0x2ECC71
_COLOR_RED = 0xE74C3C
_COLOR_ORANGE = 0xE67E22
_COLOR_BLUE = 0x3498DB
_COLOR_GRAY = 0x95A5A6


def _get_webhook_url() -> str | None:
    settings = get_settings()
    url = settings.DISCORD_WEBHOOK_URL
    return url if url else None


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _send_embed(embed: dict[str, Any]) -> None:
    """Send an embed to Discord webhook. Never propagates exceptions."""
    url = _get_webhook_url()
    if not url:
        return

    embed.setdefault("timestamp", _timestamp())

    try:
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            response = await client.post(url, json={"embeds": [embed]})
            response.raise_for_status()
    except Exception as exc:
        logger.warning("Discord webhook send failed: %s", exc)


async def notify_server_start() -> None:
    settings = get_settings()
    await _send_embed(
        {
            "title": "🟢 Server Started",
            "color": _COLOR_GREEN,
            "fields": [
                {"name": "Env", "value": settings.APP_ENV, "inline": True},
                {"name": "Python", "value": platform.python_version(), "inline": True},
                {"name": "Host", "value": platform.node(), "inline": True},
            ],
        }
    )


async def notify_server_shutdown() -> None:
    await _send_embed(
        {
            "title": "🔴 Server Shutdown",
            "color": _COLOR_RED,
            "fields": [
                {"name": "Host", "value": platform.node(), "inline": True},
            ],
        }
    )


async def notify_error_500(method: str, path: str, error: str) -> None:
    await _send_embed(
        {
            "title": "🔥 500 Internal Server Error",
            "color": _COLOR_RED,
            "fields": [
                {"name": "Endpoint", "value": f"`{method} {path}`", "inline": False},
                {"name": "Error", "value": f"```{error[:1000]}```", "inline": False},
            ],
        }
    )


async def notify_timeout(job_id: str, job_type: str, elapsed_seconds: float) -> None:
    await _send_embed(
        {
            "title": "⏱️ Pipeline Timeout",
            "color": _COLOR_ORANGE,
            "fields": [
                {"name": "job_id", "value": f"`{job_id}`", "inline": True},
                {"name": "Type", "value": job_type, "inline": True},
                {"name": "Elapsed", "value": f"{elapsed_seconds:.1f}s", "inline": True},
            ],
        }
    )


async def notify_request_timeout(method: str, path: str, elapsed_seconds: float) -> None:
    await _send_embed(
        {
            "title": "⏱️ Request Timeout",
            "color": _COLOR_ORANGE,
            "fields": [
                {"name": "Endpoint", "value": f"`{method} {path}`", "inline": False},
                {"name": "Elapsed", "value": f"{elapsed_seconds:.1f}s", "inline": True},
            ],
        }
    )


_MAX_DESC_LEN = 3900


def _format_log_line(entry: dict[str, Any]) -> str:
    stage = entry.get("stage", "")
    message = entry.get("message", "")
    elapsed_ms = entry.get("elapsed_ms")
    time_str = f" ({elapsed_ms}ms)" if elapsed_ms is not None else ""
    return f"**{stage}** — {message}{time_str}"


def _format_log_description(logs: list[dict[str, Any]]) -> str:
    if not logs:
        return "no logs"

    lines = [_format_log_line(entry) for entry in logs]
    description = "\n".join(lines)
    if len(description) <= _MAX_DESC_LEN:
        return description

    info_lines: list[str] = []
    detail_count = 0
    for entry in logs:
        if entry.get("level", "info") == "detail":
            detail_count += 1
        else:
            info_lines.append(_format_log_line(entry))

    if detail_count:
        info_lines.append(f"**detail** — {detail_count} entries collapsed")

    description = "\n".join(info_lines)
    if len(description) > _MAX_DESC_LEN:
        description = description[: _MAX_DESC_LEN - 3] + "..."
    return description


async def notify_job_completed(
    job_id: str,
    job_type: str,
    elapsed_seconds: float,
    status: str,
    logs: list[dict[str, Any]],
) -> None:
    description = _format_log_description(logs)
    color = _COLOR_GREEN if status == "SUCCESS" else _COLOR_RED

    await _send_embed(
        {
            "title": f"📋 {job_type} Job Completed",
            "color": color,
            "description": description,
            "fields": [
                {"name": "job_id", "value": f"`{job_id}`", "inline": True},
                {"name": "Status", "value": status, "inline": True},
                {"name": "Elapsed", "value": f"{elapsed_seconds:.1f}s", "inline": True},
            ],
        }
    )


async def notify_callback_failure(
    job_id: str,
    callback_type: str,
    callback_url: str,
    error: str,
) -> None:
    await _send_embed(
        {
            "title": "🚨 Callback Delivery Failed",
            "color": _COLOR_RED,
            "fields": [
                {"name": "job_id", "value": f"`{job_id}`", "inline": True},
                {"name": "Type", "value": callback_type, "inline": True},
                {"name": "URL", "value": f"`{callback_url[:200]}`", "inline": False},
                {"name": "Error", "value": f"```{error[:500]}```", "inline": False},
            ],
        }
    )
