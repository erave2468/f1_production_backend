import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "supersecretadmintoken")
admin_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


# 보안
def require_admin(api_key: str = Security(admin_token_header)):
    """
    관리자 전용 엔드포인트용 의존성.
    헤더 X-Admin-Token 이 서버 설정과 다르면 403 에러 발생.
    """
    if api_key != ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )
