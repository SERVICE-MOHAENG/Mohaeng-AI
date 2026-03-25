"""콜백 전송 재시도 유틸리티."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.timeout_policy import to_httpx_timeout

logger = get_logger(__name__)


def _is_retryable_request_error(exc: Exception) -> bool:
    """재시도 가능한 요청 예외인지 판별합니다."""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code if exc.response is not None else None
        return status_code is None or status_code == 429 or status_code >= 500

    return False


async def post_callback_with_retry(
    *,
    callback_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int,
    context: dict[str, Any] | None = None,
) -> bool:
    """콜백 요청을 전송하고 실패 시 지수 백오프로 재시도합니다."""
    settings = get_settings()
    max_retries = max(0, int(settings.CALLBACK_MAX_RETRIES))
    max_attempts = 1 + max_retries
    base_delay = max(0.0, float(settings.CALLBACK_BACKOFF_BASE_SECONDS))
    max_delay = max(base_delay, float(settings.CALLBACK_BACKOFF_MAX_SECONDS))
    timeout = to_httpx_timeout(timeout_seconds)
    callback_context = context or {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(
                    callback_url,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                if attempt > 1:
                    logger.info(
                        "Callback succeeded after retry: attempt=%d/%d url=%s context=%s",
                        attempt,
                        max_attempts,
                        callback_url,
                        callback_context,
                    )
                return True
            except Exception as exc:
                is_retryable = _is_retryable_request_error(exc)
                is_last_attempt = attempt >= max_attempts
                status_code = None
                if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                    status_code = exc.response.status_code

                if is_last_attempt or not is_retryable:
                    logger.error(
                        (
                            "Callback delivery failed permanently: "
                            "attempts=%d url=%s status_code=%s retryable=%s error=%s context=%s"
                        ),
                        attempt,
                        callback_url,
                        status_code,
                        is_retryable,
                        exc,
                        callback_context,
                    )
                    return False

                delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                logger.warning(
                    (
                        "Callback delivery failed, retrying: "
                        "attempt=%d/%d delay=%.2fs url=%s status_code=%s error=%s context=%s"
                    ),
                    attempt,
                    max_attempts,
                    delay,
                    callback_url,
                    status_code,
                    exc,
                    callback_context,
                )
                await asyncio.sleep(delay)

    return False
