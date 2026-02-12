"""전역 타임아웃 정책 정의."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings

_MIN_TIMEOUT_SECONDS = 1
_MAX_CONNECT_TIMEOUT_SECONDS = 5.0
_CONNECT_TIMEOUT_RATIO = 0.3


def _normalize_timeout(value: int | float | None, default: int, *, upper_bound: int | None = None) -> int:
    """타임아웃 값을 정수 초 단위로 정규화합니다."""
    try:
        seconds = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        seconds = int(default)

    seconds = max(_MIN_TIMEOUT_SECONDS, seconds)
    if upper_bound is not None:
        seconds = min(seconds, upper_bound)
    return seconds


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    """애플리케이션 전체 타임아웃 정책."""

    request_timeout_seconds: int
    llm_timeout_seconds: int
    recommend_timeout_seconds: int
    external_api_timeout_seconds: int
    callback_timeout_seconds: int
    google_places_timeout_seconds: int


def build_timeout_policy(settings: Settings) -> TimeoutPolicy:
    """설정값으로부터 일관된 타임아웃 정책을 생성합니다."""
    request_timeout = _normalize_timeout(settings.REQUEST_TIMEOUT_SECONDS, default=60)
    llm_timeout = _normalize_timeout(settings.LLM_TIMEOUT_SECONDS, default=60, upper_bound=request_timeout)
    recommend_timeout = _normalize_timeout(
        settings.RECOMMEND_TIMEOUT_SECONDS,
        default=45,
        upper_bound=request_timeout,
    )
    external_timeout = _normalize_timeout(
        settings.EXTERNAL_API_TIMEOUT_SECONDS,
        default=15,
        upper_bound=request_timeout,
    )
    callback_timeout = _normalize_timeout(
        settings.CALLBACK_TIMEOUT_SECONDS,
        default=10,
        upper_bound=external_timeout,
    )
    google_places_timeout = _normalize_timeout(
        settings.GOOGLE_PLACES_TIMEOUT_SECONDS,
        default=10,
        upper_bound=external_timeout,
    )

    return TimeoutPolicy(
        request_timeout_seconds=request_timeout,
        llm_timeout_seconds=llm_timeout,
        recommend_timeout_seconds=recommend_timeout,
        external_api_timeout_seconds=external_timeout,
        callback_timeout_seconds=callback_timeout,
        google_places_timeout_seconds=google_places_timeout,
    )


def get_timeout_policy(settings: Settings | None = None) -> TimeoutPolicy:
    """현재 설정을 기반으로 타임아웃 정책을 반환합니다."""
    resolved_settings = settings or get_settings()
    return build_timeout_policy(resolved_settings)


def to_requests_timeout(total_timeout_seconds: int) -> tuple[float, float]:
    """requests용 (connect, read) 타임아웃 튜플을 생성합니다."""
    total = float(max(_MIN_TIMEOUT_SECONDS, int(total_timeout_seconds)))
    connect_timeout = min(_MAX_CONNECT_TIMEOUT_SECONDS, max(1.0, total * _CONNECT_TIMEOUT_RATIO))
    read_timeout = max(1.0, total - connect_timeout) if total > connect_timeout else max(0.5, total * 0.5)
    return (connect_timeout, read_timeout)
