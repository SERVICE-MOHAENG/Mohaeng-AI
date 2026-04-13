"""Discord webhook notification service."""

from __future__ import annotations

import asyncio
import platform
from datetime import datetime, timezone
from typing import Any, Awaitable

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


def schedule_webhook(coro: Awaitable[Any]) -> None:
    """현재 이벤트 루프에 웹훅 전송 작업을 예약한다."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return
    loop.create_task(coro)


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


def _severity_color(severity: str) -> int:
    normalized = severity.strip().lower()
    if normalized == "error":
        return _COLOR_RED
    if normalized == "warning":
        return _COLOR_ORANGE
    if normalized == "success":
        return _COLOR_GREEN
    return _COLOR_BLUE


def _append_field(fields: list[dict[str, Any]], name: str, value: Any, inline: bool = True) -> None:
    if value is None:
        return
    text = str(value)
    if not text:
        return
    fields.append({"name": name, "value": text, "inline": inline})


def _format_event_title(event_type: str, title: str | None) -> str:
    if title:
        return title
    return event_type.replace("_", " ").title()


async def notify_pipeline_event(
    *,
    event_type: str,
    severity: str,
    stage: str,
    status: str,
    message: str,
    title: str | None = None,
    description: str | None = None,
    job_id: str | None = None,
    elapsed_ms: int | None = None,
    model: str | None = None,
    fallback_used: bool | None = None,
    error: str | None = None,
    extra_fields: list[dict[str, Any]] | None = None,
) -> None:
    """공통 단계 이벤트를 Discord 웹훅으로 전송한다."""
    fields: list[dict[str, Any]] = []
    _append_field(fields, "event_type", event_type)
    _append_field(fields, "severity", severity)
    _append_field(fields, "stage", stage)
    _append_field(fields, "status", status)
    _append_field(fields, "job_id", f"`{job_id}`" if job_id else None)
    _append_field(fields, "message", message, inline=False)
    _append_field(fields, "elapsed_ms", f"{elapsed_ms}ms" if elapsed_ms is not None else None)
    _append_field(fields, "model", model)
    _append_field(fields, "fallback_used", fallback_used)
    _append_field(fields, "error", f"```{error[:1000]}```" if error else None, inline=False)
    if extra_fields:
        fields.extend(extra_fields)

    payload: dict[str, Any] = {
        "title": _format_event_title(event_type, title),
        "color": _severity_color(severity),
        "fields": fields,
    }
    if description is not None:
        payload["description"] = description

    await _send_embed(payload)


async def notify_server_start() -> None:
    settings = get_settings()
    await notify_pipeline_event(
        event_type="server_start",
        severity="success",
        stage="server",
        status="READY",
        title="🟢 Server Started",
        message="FastAPI 애플리케이션이 시작되었습니다.",
        extra_fields=[
            {"name": "Env", "value": settings.APP_ENV, "inline": True},
            {"name": "Python", "value": platform.python_version(), "inline": True},
            {"name": "Host", "value": platform.node(), "inline": True},
        ],
    )


async def notify_server_shutdown() -> None:
    await notify_pipeline_event(
        event_type="server_shutdown",
        severity="error",
        stage="server",
        status="STOPPED",
        title="🔴 Server Shutdown",
        message="FastAPI 애플리케이션이 종료되었습니다.",
        extra_fields=[{"name": "Host", "value": platform.node(), "inline": True}],
    )


async def notify_error_500(method: str, path: str, error: str) -> None:
    await notify_pipeline_event(
        event_type="http_500",
        severity="error",
        stage="http",
        status="FAILED",
        title="🔥 500 Internal Server Error",
        message="처리되지 않은 예외가 전역 예외 처리기에 도달했습니다.",
        extra_fields=[
            {"name": "Endpoint", "value": f"`{method} {path}`", "inline": False},
            {"name": "Error", "value": f"```{error[:1000]}```", "inline": False},
        ],
    )


async def notify_timeout(job_id: str, job_type: str, elapsed_seconds: float) -> None:
    await notify_pipeline_event(
        event_type="pipeline_timeout",
        severity="warning",
        stage=job_type,
        status="TIMEOUT",
        title="⏱️ Pipeline Timeout",
        message=f"{job_type} 작업이 제한 시간을 초과했습니다.",
        job_id=job_id,
        extra_fields=[
            {"name": "Type", "value": job_type, "inline": True},
            {"name": "Elapsed", "value": f"{elapsed_seconds:.1f}s", "inline": True},
        ],
    )


async def notify_request_timeout(method: str, path: str, elapsed_seconds: float) -> None:
    await notify_pipeline_event(
        event_type="request_timeout",
        severity="warning",
        stage="http",
        status="TIMEOUT",
        title="⏱️ Request Timeout",
        message="HTTP 요청이 설정된 타임아웃을 초과했습니다.",
        extra_fields=[
            {"name": "Endpoint", "value": f"`{method} {path}`", "inline": False},
            {"name": "Elapsed", "value": f"{elapsed_seconds:.1f}s", "inline": True},
        ],
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
    severity = "success" if status == "SUCCESS" else "error"

    await notify_pipeline_event(
        event_type=f"{job_type}_job_completed",
        severity=severity,
        stage=job_type,
        status=status,
        title=f"📋 {job_type} Job Completed",
        message="수집된 작업 로그를 요약해서 전송합니다.",
        description=description,
        job_id=job_id,
        elapsed_ms=round(elapsed_seconds * 1000),
        extra_fields=[
            {"name": "Status", "value": status, "inline": True},
            {"name": "Elapsed", "value": f"{elapsed_seconds:.1f}s", "inline": True},
        ],
    )


async def notify_callback_failure(
    job_id: str,
    callback_type: str,
    callback_url: str,
    error: str,
) -> None:
    await notify_pipeline_event(
        event_type="callback_delivery_failed",
        severity="error",
        stage=callback_type,
        status="FAILED",
        title="🚨 Callback Delivery Failed",
        message="콜백 전송이 재시도 후에도 실패했습니다.",
        job_id=job_id,
        error=error,
        extra_fields=[
            {"name": "Type", "value": callback_type, "inline": True},
            {"name": "URL", "value": f"`{callback_url[:200]}`", "inline": False},
        ],
    )
