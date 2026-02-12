"""애플리케이션 준비성(readiness) 체크 유틸."""

from __future__ import annotations

import asyncio
import socket
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import Settings, get_settings
from app.core.timeout_policy import TimeoutPolicy, get_timeout_policy

ReadinessCheck = dict[str, str | bool]


def _ok(detail: str, *, required: bool = True) -> ReadinessCheck:
    return {"status": "ok", "ok": True, "required": required, "detail": detail}


def _fail(detail: str, *, required: bool = True) -> ReadinessCheck:
    return {"status": "fail", "ok": False, "required": required, "detail": detail}


def _skip(detail: str, *, required: bool = False) -> ReadinessCheck:
    return {"status": "skip", "ok": True, "required": required, "detail": detail}


def _resolve_db_host_port(database_url: str) -> tuple[str, int] | None:
    parsed = urlparse(database_url)
    host = parsed.hostname
    if not host:
        return None

    base_scheme = parsed.scheme.split("+")[0].lower()
    default_ports = {
        "postgres": 5432,
        "postgresql": 5432,
        "mysql": 3306,
        "mariadb": 3306,
    }
    port = parsed.port or default_ports.get(base_scheme, 5432)
    return host, int(port)


def _normalize_sqlite_path(database_url: str) -> str | None:
    parsed = urlparse(database_url)
    if parsed.scheme.split("+")[0].lower() not in {"sqlite", "sqlite3"}:
        return None

    if database_url.endswith(":memory:"):
        return ":memory:"

    db_path = unquote(parsed.path or "")
    if not db_path:
        return None

    # Windows absolute path 형태(/C:/...) 보정
    if len(db_path) >= 3 and db_path[0] == "/" and db_path[2] == ":":
        db_path = db_path[1:]
    return db_path


async def _check_tcp_connectivity(host: str, port: int, timeout_seconds: int, label: str) -> ReadinessCheck:
    def _connect() -> None:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return None

    try:
        await asyncio.to_thread(_connect)
        return _ok(f"{label} 연결 가능 ({host}:{port})")
    except Exception as exc:
        return _fail(f"{label} 연결 실패 ({host}:{port}): {exc}")


async def _check_database_readiness(settings: Settings, timeout_policy: TimeoutPolicy) -> ReadinessCheck:
    database_url = (settings.DATABASE_URL or "").strip()
    if not database_url:
        return _fail("DATABASE_URL이 설정되지 않았습니다.")

    sqlite_path = _normalize_sqlite_path(database_url)
    if sqlite_path is not None:

        def _check_sqlite() -> None:
            if sqlite_path != ":memory:":
                parent = Path(sqlite_path).parent
                if parent and not parent.exists():
                    raise FileNotFoundError(f"DB 경로 디렉터리가 존재하지 않습니다: {parent}")
            connection = sqlite3.connect(sqlite_path)
            try:
                connection.execute("SELECT 1")
            finally:
                connection.close()

        try:
            await asyncio.to_thread(_check_sqlite)
            return _ok("SQLite 연결 확인 완료")
        except Exception as exc:
            return _fail(f"SQLite 연결 실패: {exc}")

    host_port = _resolve_db_host_port(database_url)
    if host_port is None:
        return _fail("DATABASE_URL에서 DB 호스트를 파싱할 수 없습니다.")

    host, port = host_port
    return await _check_tcp_connectivity(
        host=host,
        port=port,
        timeout_seconds=timeout_policy.external_api_timeout_seconds,
        label="DB",
    )


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
    """DB/외부 API 의존성 준비 상태를 점검합니다."""
    settings = get_settings()
    timeout_policy = get_timeout_policy(settings)

    db_check, openai_check, google_places_check = await asyncio.gather(
        _check_database_readiness(settings, timeout_policy),
        _check_openai_readiness(settings, timeout_policy),
        _check_google_places_readiness(settings, timeout_policy),
    )

    checks: dict[str, ReadinessCheck] = {
        "db": db_check,
        "openai": openai_check,
        "google_places": google_places_check,
    }
    required_checks_ok = all(bool(check["ok"]) for check in checks.values() if bool(check.get("required", True)))

    return {
        "status": "ready" if required_checks_ok else "not_ready",
        "checks": checks,
    }
