"""로거 헬퍼."""

import logging


def get_logger(name: str) -> logging.Logger:
    """모듈 로거를 반환합니다."""
    return logging.getLogger(name)
