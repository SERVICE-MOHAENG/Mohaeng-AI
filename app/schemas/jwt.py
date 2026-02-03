"""`JWT` 토큰 페이로드 스키마 정의."""

from pydantic import BaseModel, ConfigDict, Field


class AdminTokenPayload(BaseModel):
    """관리자용 `JWT` 페이로드."""

    model_config = ConfigDict(populate_by_name=True)

    admin_id: str = Field(..., alias="adminId", description="관리자 식별자")
    email: str = Field(..., description="관리자 이메일")
    permissions: int = Field(..., description="권한 비트마스크 값")
    is_super_admin: bool = Field(..., alias="isSuperAdmin", description="슈퍼 관리자 여부")
    iat: int | None = Field(None, description="발급 시각(Unix timestamp, seconds)")
    exp: int | None = Field(None, description="만료 시각(Unix timestamp, seconds)")


class UserTokenPayload(BaseModel):
    """일반 사용자용 `JWT` 페이로드."""

    model_config = ConfigDict(populate_by_name=True)

    sub: str = Field(..., description="토큰 subject (일반적으로 사용자 UUID)")
    user_id: str = Field(..., alias="userId", description="사용자 식별자")
    email: str = Field(..., description="사용자 이메일")
    iat: int | None = Field(None, description="발급 시각(Unix timestamp, seconds)")
    exp: int | None = Field(None, description="만료 시각(Unix timestamp, seconds)")
