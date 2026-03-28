"""job 단위 로그 수집기 (contextvars 기반)."""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any

_job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
_start_time_var: ContextVar[float] = ContextVar("job_start_time", default=0.0)
_logs_var: ContextVar[list[dict[str, Any]] | None] = ContextVar("job_logs", default=None)


def init_job_log(job_id: str) -> None:
    """현재 태스크에 대한 job 로그를 초기화한다."""
    _job_id_var.set(job_id)
    _start_time_var.set(time.monotonic())
    _logs_var.set([])


def append_job_log(stage: str, message: str, extra: dict[str, Any] | None = None) -> None:
    """현재 job에 로그 항목을 추가한다. init_job_log 호출 전이면 무시한다."""
    logs = _logs_var.get()
    if logs is None:
        return

    start = _start_time_var.get()
    elapsed_ms = round((time.monotonic() - start) * 1000)

    entry: dict[str, Any] = {"stage": stage, "message": message, "elapsed_ms": elapsed_ms}
    if extra:
        entry.update(extra)

    logs.append(entry)


def collect_job_logs() -> tuple[str | None, list[dict[str, Any]], float]:
    """수집된 로그와 총 소요 시간을 반환하고 컨텍스트를 정리한다."""
    job_id = _job_id_var.get()
    logs = _logs_var.get() or []
    start = _start_time_var.get()
    elapsed_seconds = time.monotonic() - start if start else 0.0

    _job_id_var.set(None)
    _start_time_var.set(0.0)
    _logs_var.set(None)

    return job_id, list(logs), elapsed_seconds
