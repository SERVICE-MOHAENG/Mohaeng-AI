"""표준화된 로거 모듈.

프로젝트 전체에서 일관된 로깅 형식을 제공합니다.
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """표준화된 로거를 반환합니다.

    Args:
        name: 로거 이름 (일반적으로 __name__ 사용).

    Returns:
        설정된 로거 인스턴스.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
