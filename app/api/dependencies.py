"""API 의존성 모음."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.jwt import UserTokenPayload
from app.services.jwt_service import JwtService

bearer_scheme = HTTPBearer(auto_error=False)


def get_jwt_service() -> JwtService:
    """`JWT` 서비스 인스턴스를 제공합니다."""
    return JwtService()


def require_user_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    jwt_service: JwtService = Depends(get_jwt_service),
) -> UserTokenPayload:
    """유효한 사용자용 `Bearer` 토큰을 요구합니다."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 정보가 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return jwt_service.verify_user_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
