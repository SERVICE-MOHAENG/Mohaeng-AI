"""JWT 발급 및 검증을 담당하는 서비스 모듈."""

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from app.core.config import settings


class JwtService:
    """서비스 전역에서 재사용하는 JWT 생성/검증 유틸리티."""

    def __init__(self):
        """환경 설정을 불러와 서명 시크릿과 만료 시간을 초기화한다."""
        self.secret = settings.JWT_ACCESS_SECRET
        self.algorithm = "HS256"
        self.expires_delta = timedelta(minutes=settings.JWT_ACCESS_EXPIRY_MINUTES)

        if not self.secret:
            raise ValueError("JWT access secret is not set.")

    def _create_token(self, payload: dict) -> str:
        """iat/exp를 추가한 뒤 서명된 JWT 문자열을 생성한다."""
        now = datetime.now(timezone.utc)
        expire = now + self.expires_delta

        payload.update({"iat": int(now.timestamp()), "exp": int(expire.timestamp())})

        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def sign_admin_token(self, admin_id: str, email: str, permissions: int, is_super_admin: bool) -> str:
        """관리자 권한 정보가 포함된 액세스 토큰을 생성한다."""
        payload = {
            "adminId": admin_id,
            "email": email,
            "permissions": permissions,
            "isSuperAdmin": is_super_admin,
        }
        return self._create_token(payload)

    def sign_user_token(self, user_id: str, email: str, sub: Optional[str] = None) -> str:
        """사용자 액세스 토큰을 생성한다."""
        payload = {
            "sub": sub or user_id,
            "userId": user_id,
            "email": email,
        }
        return self._create_token(payload)

    def sign_token(self, payload: Dict[str, Any], expires_in: Optional[timedelta] = None) -> str:
        """임의 페이로드로 토큰을 생성하며 만료 시간을 커스텀할 수 있다."""
        now = datetime.now(timezone.utc)
        expire = now + (expires_in if expires_in else self.expires_delta)

        payload.update({"iat": int(now.timestamp()), "exp": int(expire.timestamp())})
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def verify_admin_token(self, token: str) -> dict:
        """관리자 토큰을 검증하고 페이로드를 반환한다.

        Raises:
            ValueError: 서명 오류 또는 필수 필드 누락 시.
        """
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])

            # 필수 필드 검증
            if not all(k in payload for k in ("adminId", "permissions", "isSuperAdmin")):
                raise ValueError("Invalid admin token payload.")

            return payload
        except jwt.PyJWTError:
            raise ValueError("Invalid token") from None

    def verify_user_token(self, token: str) -> dict:
        """사용자 토큰을 검증하고 페이로드를 반환한다.

        Raises:
            ValueError: 서명 오류 또는 필수 필드 누락 시.
        """
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])

            # 필수 필드 검증
            if not payload.get("userId") or not payload.get("sub"):
                raise ValueError("Invalid user token payload.")

            return payload
        except jwt.PyJWTError:
            raise ValueError("Invalid token") from None

    def verify_token(self, token: str, ignore_expiration: bool = False) -> dict:
        """서명/만료 검증 옵션을 지정하여 토큰을 디코드한다."""
        options = {"verify_exp": not ignore_expiration}
        return jwt.decode(token, self.secret, algorithms=[self.algorithm], options=options)

    def get_token_expiration_time(self, token: str) -> int:
        """토큰이 만료되기까지 남은 초를 반환한다. 실패 시 -1."""
        try:
            # 서명 검증 없이 디코딩하여 exp만 확인
            payload = jwt.decode(token, options={"verify_signature": False})
            exp = payload.get("exp")
            if not exp:
                return -1

            now = int(time.time())
            return exp - now
        except Exception:
            return -1

    def is_token_valid(self, token: str) -> bool:
        """토큰의 서명과 만료를 검증해 유효성을 반환한다."""
        try:
            self.verify_token(token)
            return True
        except Exception:
            return False

    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """서명 검증 없이 페이로드를 디코드한다. 실패 시 None."""
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception:
            return None
