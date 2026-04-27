"""Discord webhook notification service."""

from __future__ import annotations

import asyncio
import json
import platform
import threading
import traceback
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

ALLOWED_WEBHOOK_EVENTS = frozenset(
    {
        "server_start",
        "server_shutdown",
        "http_500",
        "request_timeout",
        "pipeline_timeout",
        "callback_delivery_failed",
        "chat_started",
        "generate_started",
        "recommend_request_received",
        "chat_intent_rejected",
        "chat_intent_failed",
        "chat_completed",
        "generate_completed",
        "recommend_completed",
        "llm_call_failed",
        "llm_fallback_failed",
        "roadmap_finalize_failed",
    }
)


def schedule_webhook(coro: Awaitable[Any]) -> None:
    """현재 이벤트 루프에 웹훅 전송 작업을 예약한다.

    실행 중인 이벤트 루프가 있으면 백그라운드 태스크로 예약하고,
    없으면 별도 데몬 스레드에서 asyncio.run()으로 실행한다.
    진짜 fire-and-forget이 필요하면 호출 측에서 실행 중인 이벤트 루프를 보장하거나
    별도 백그라운드 실행 전략을 사용해야 한다.
    """

    async def _run_safely() -> None:
        try:
            await coro
        except Exception as exc:
            logger.warning("Discord webhook task failed: %s", exc)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:

        def _runner() -> None:
            try:
                asyncio.run(_run_safely())
            except Exception as exc:
                logger.warning("Discord webhook task failed outside event loop: %s", exc)

        threading.Thread(target=_runner, name="discord-webhook", daemon=True).start()
        return
    loop.create_task(_run_safely())


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


def _append_json_field(
    fields: list[dict[str, Any]],
    name: str,
    value: Any,
    inline: bool = False,
    *,
    limit: int = 1000,
) -> None:
    if value is None:
        return
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        text = str(value)
    if not text:
        return
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    fields.append({"name": name, "value": f"```json\n{text}\n```", "inline": inline})


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
    """표준 파이프라인 이벤트를 Discord 웹훅 payload로 전송한다."""
    if event_type not in ALLOWED_WEBHOOK_EVENTS:
        logger.debug("Skipping non-production webhook event: %s", event_type)
        return

    fields: list[dict[str, Any]] = []
    _append_field(fields, "이벤트", event_type)
    _append_field(fields, "중요도", severity)
    _append_field(fields, "단계", stage)
    _append_field(fields, "상태", status)
    _append_field(fields, "job_id", f"`{job_id}`" if job_id else None)
    _append_field(fields, "메시지", message, inline=False)
    _append_field(fields, "소요 시간", f"{elapsed_ms}ms" if elapsed_ms is not None else None)
    _append_field(fields, "모델", model)
    _append_field(fields, "fallback 사용", fallback_used)
    _append_field(fields, "오류", f"```{error[:1000]}```" if error else None, inline=False)
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
        title="서버 시작",
        message="FastAPI 애플리케이션이 시작되었습니다.",
        extra_fields=[
            {"name": "환경", "value": settings.APP_ENV, "inline": True},
            {"name": "Python", "value": platform.python_version(), "inline": True},
            {"name": "호스트", "value": platform.node(), "inline": True},
        ],
    )


async def notify_server_shutdown() -> None:
    await notify_pipeline_event(
        event_type="server_shutdown",
        severity="error",
        stage="server",
        status="STOPPED",
        title="서버 종료",
        message="FastAPI 애플리케이션이 종료되었습니다.",
        extra_fields=[{"name": "호스트", "value": platform.node(), "inline": True}],
    )


async def notify_error_500(method: str, path: str, error: str) -> None:
    await notify_pipeline_event(
        event_type="http_500",
        severity="error",
        stage="http",
        status="FAILED",
        title="HTTP 500 오류",
        message="처리되지 않은 예외가 전역 예외 처리기에 도달했습니다.",
        extra_fields=[
            {"name": "엔드포인트", "value": f"`{method} {path}`", "inline": False},
            {"name": "오류", "value": f"```{error[:1000]}```", "inline": False},
        ],
    )


async def notify_timeout(job_id: str, job_type: str, elapsed_seconds: float) -> None:
    await notify_pipeline_event(
        event_type="pipeline_timeout",
        severity="warning",
        stage=job_type,
        status="TIMEOUT",
        title="파이프라인 제한 시간 초과",
        message=f"{job_type} 작업이 제한 시간을 초과했습니다.",
        job_id=job_id,
        extra_fields=[
            {"name": "작업 유형", "value": job_type, "inline": True},
            {"name": "경과 시간", "value": f"{elapsed_seconds:.1f}s", "inline": True},
        ],
    )


async def notify_request_timeout(method: str, path: str, elapsed_seconds: float) -> None:
    await notify_pipeline_event(
        event_type="request_timeout",
        severity="warning",
        stage="http",
        status="TIMEOUT",
        title="HTTP 요청 제한 시간 초과",
        message="HTTP 요청이 설정된 타임아웃을 초과했습니다.",
        extra_fields=[
            {"name": "엔드포인트", "value": f"`{method} {path}`", "inline": False},
            {"name": "경과 시간", "value": f"{elapsed_seconds:.1f}s", "inline": True},
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
        title="콜백 전송 실패",
        message="콜백 전송이 재시도 후에도 실패했습니다.",
        job_id=job_id,
        error=error,
        extra_fields=[
            {"name": "콜백 유형", "value": callback_type, "inline": True},
            {"name": "URL", "value": f"`{callback_url[:200]}`", "inline": False},
        ],
    )


def format_exception_details(exc: BaseException) -> dict[str, str]:
    """예외를 웹훅에 넣기 좋은 한국어 상세 정보로 변환한다."""
    return {
        "오류 유형": type(exc).__name__,
        "오류 메시지": str(exc),
        "스택 트레이스": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }
