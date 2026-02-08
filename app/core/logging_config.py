"""Uvicorn 기본 포맷에 맞춘 로깅 설정."""

from __future__ import annotations

import copy
import logging.config
import os
from typing import Any

from uvicorn.config import LOGGING_CONFIG as UVICORN_LOGGING_CONFIG


def _resolve_log_level(level: str | None = None) -> str:
    """인자 또는 환경변수에서 로그 레벨을 결정합니다."""
    if level:
        return level.upper()
    return os.getenv("LOG_LEVEL", "INFO").upper()


def build_logging_config(level: str | None = None) -> dict[str, Any]:
    """Uvicorn 기본 포맷터와 동일한 로깅 설정을 생성합니다."""
    log_level = _resolve_log_level(level)
    config = copy.deepcopy(UVICORN_LOGGING_CONFIG)

    config["root"] = {"handlers": ["default"], "level": log_level}

    config["loggers"]["uvicorn"]["level"] = log_level
    config["loggers"]["uvicorn.error"]["level"] = log_level
    config["loggers"]["uvicorn.access"]["level"] = log_level

    return config


def configure_logging(level: str | None = None) -> None:
    """dictConfig로 로깅을 구성합니다."""
    logging.config.dictConfig(build_logging_config(level))
