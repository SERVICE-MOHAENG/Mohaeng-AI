"""애플리케이션 준비성(readiness) 체크 유틸."""

from __future__ import annotations

import asyncio
import socket

from app.core.config import Settings, get_settings
from app.core.timeout_policy import TimeoutPolicy, get_timeout_policy

ReadinessCheck = dict[str, str | bool]


def _ok(detail: str, *, required: bool = True) -> ReadinessCheck:
    return {"status": "ok", "ok": True, "required": required, "detail": detail}


def _fail(detail: str, *, required: bool = True) -> ReadinessCheck:
    return {"status": "fail", "ok": False, "required": required, "detail": detail}


def _skip(detail: str, *, required: bool = False) -> ReadinessCheck:
    return {"status": "skip", "ok": True, "required": required, "detail": detail}


async def _check_tcp_connectivity(host: str, port: int, timeout_seconds: int, label: str) -> ReadinessCheck:
    def _connect() -> None:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return None

    try:
        await asyncio.to_thread(_connect)
        return _ok(f"{label} 연결 가능 ({host}:{port})")
    except Exception as exc:
        return _fail(f"{label} 연결 실패 ({host}:{port}): {exc}")


async def _check_openai_readiness(settings: Settings, timeout_policy: TimeoutPolicy) -> ReadinessCheck:
    if not settings.OPENAI_API_KEY:
        return _fail("OPENAI_API_KEY가 설정되지 않았습니다.")

    return await _check_tcp_connectivity(
        host="api.openai.com",
        port=443,
        timeout_seconds=timeout_policy.external_api_timeout_seconds,
        label="OpenAI API",
    )


async def _check_google_places_readiness(settings: Settings, timeout_policy: TimeoutPolicy) -> ReadinessCheck:
    if not settings.GOOGLE_PLACES_API_KEY:
        return _skip("GOOGLE_PLACES_API_KEY 미설정으로 Google Places 체크를 건너뜁니다.")

    return await _check_tcp_connectivity(
        host="places.googleapis.com",
        port=443,
        timeout_seconds=timeout_policy.external_api_timeout_seconds,
        label="Google Places API",
    )


async def collect_readiness_status() -> dict[str, object]:
    """외부 API 의존성 준비 상태를 점검합니다."""
    settings = get_settings()
    timeout_policy = get_timeout_policy(settings)

    openai_check, google_places_check = await asyncio.gather(
        _check_openai_readiness(settings, timeout_policy),
        _check_google_places_readiness(settings, timeout_policy),
    )

    checks: dict[str, ReadinessCheck] = {
        "openai": openai_check,
        "google_places": google_places_check,
    }
    required_checks_ok = all(bool(check["ok"]) for check in checks.values() if bool(check.get("required", True)))

    return {
        "status": "ready" if required_checks_ok else "not_ready",
        "checks": checks,
    }
