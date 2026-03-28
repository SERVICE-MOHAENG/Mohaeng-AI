"""Discord 웹훅 알림 전송 서비스."""

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
    """Discord 웹훅으로 embed를 전송한다. 실패해도 예외를 전파하지 않는다."""
    url = _get_webhook_url()
    if not url:
        return

    embed.setdefault("timestamp", _timestamp())

    try:
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            response = await client.post(url, json={"embeds": [embed]})
            response.raise_for_status()
    except Exception as exc:
        logger.warning("Discord webhook 전송 실패: %s", exc)


async def notify_server_start() -> None:
    settings = get_settings()
    await _send_embed(
        {
            "title": "🟢 서버 시작",
            "color": _COLOR_GREEN,
            "fields": [
                {"name": "환경", "value": settings.APP_ENV, "inline": True},
                {"name": "Python", "value": platform.python_version(), "inline": True},
                {"name": "호스트", "value": platform.node(), "inline": True},
            ],
        }
    )


async def notify_server_shutdown() -> None:
    await _send_embed(
        {
            "title": "🔴 서버 종료",
            "color": _COLOR_RED,
            "fields": [
                {"name": "호스트", "value": platform.node(), "inline": True},
            ],
        }
    )


async def notify_error_500(method: str, path: str, error: str) -> None:
    await _send_embed(
        {
            "title": "🔥 500 Internal Server Error",
            "color": _COLOR_RED,
            "fields": [
                {"name": "엔드포인트", "value": f"`{method} {path}`", "inline": False},
                {"name": "에러", "value": f"```{error[:1000]}```", "inline": False},
            ],
        }
    )


async def notify_timeout(job_id: str, job_type: str, elapsed_seconds: float) -> None:
    await _send_embed(
        {
            "title": "⏱️ Timeout 발생",
            "color": _COLOR_ORANGE,
            "fields": [
                {"name": "job_id", "value": f"`{job_id}`", "inline": True},
                {"name": "타입", "value": job_type, "inline": True},
                {"name": "소요 시간", "value": f"{elapsed_seconds:.1f}s", "inline": True},
            ],
        }
    )


async def notify_request_timeout(method: str, path: str, elapsed_seconds: float) -> None:
    await _send_embed(
        {
            "title": "⏱️ Request Timeout",
            "color": _COLOR_ORANGE,
            "fields": [
                {"name": "엔드포인트", "value": f"`{method} {path}`", "inline": False},
                {"name": "소요 시간", "value": f"{elapsed_seconds:.1f}s", "inline": True},
            ],
        }
    )


async def notify_job_completed(
    job_id: str,
    job_type: str,
    elapsed_seconds: float,
    status: str,
    logs: list[dict[str, Any]],
) -> None:
    description_lines: list[str] = []
    for entry in logs:
        stage = entry.get("stage", "")
        message = entry.get("message", "")
        elapsed_ms = entry.get("elapsed_ms")
        time_str = f" ({elapsed_ms}ms)" if elapsed_ms is not None else ""
        description_lines.append(f"**{stage}** — {message}{time_str}")

    description = "\n".join(description_lines) if description_lines else "로그 없음"
    if len(description) > 4000:
        description = description[:3997] + "..."

    color = _COLOR_GREEN if status == "SUCCESS" else _COLOR_RED

    await _send_embed(
        {
            "title": f"📋 {job_type} 작업 완료",
            "color": color,
            "description": description,
            "fields": [
                {"name": "job_id", "value": f"`{job_id}`", "inline": True},
                {"name": "상태", "value": status, "inline": True},
                {"name": "소요 시간", "value": f"{elapsed_seconds:.1f}s", "inline": True},
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
            "title": "🚨 콜백 전달 실패",
            "color": _COLOR_RED,
            "fields": [
                {"name": "job_id", "value": f"`{job_id}`", "inline": True},
                {"name": "타입", "value": callback_type, "inline": True},
                {"name": "URL", "value": f"`{callback_url[:200]}`", "inline": False},
                {"name": "에러", "value": f"```{error[:500]}```", "inline": False},
            ],
        }
    )
