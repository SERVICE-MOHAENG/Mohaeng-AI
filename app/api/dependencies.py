"""API 의존성 모음."""

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def require_service_secret(
    x_service_secret: str | None = Header(default=None, alias="x-service-secret"),
) -> None:
    """서비스 간 인증을 위한 시크릿 헤더를 검증한다."""
    settings = get_settings()
    if not settings.SERVICE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="서비스 시크릿 설정이 없습니다.",
        )

    if not x_service_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="서비스 시크릿 헤더가 누락되었습니다.",
        )

    if not hmac.compare_digest(x_service_secret, settings.SERVICE_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 서비스 시크릿입니다.",
        )
