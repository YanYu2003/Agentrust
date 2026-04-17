"""
Authentication middleware for session token validation.
"""

import logging
from typing import Optional, Callable

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ErrorResponse, ErrorCode, SessionInfo
from app.services.auth_service import AuthService, AuthServiceError

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def get_current_session(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> Optional[SessionInfo]:
    """
    Get current session if authenticated, otherwise return None.

    Use this for optional authentication.
    """
    if not credentials:
        return None

    try:
        auth_service = AuthService(session)
        session_info = await auth_service.validate_session(credentials.credentials)
        return session_info
    except AuthServiceError as e:
        return None
    except Exception as e:
        logger.exception("Session validation failed")
        return None


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> SessionInfo:
    """
    Require authentication. Raises exception if not authenticated.

    Use this for endpoints that require authentication.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ErrorResponse.create(
                ErrorCode.AUTH_REQUIRED,
                "Authentication required",
            ).model_dump(),
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        auth_service = AuthService(session)
        session_info = await auth_service.validate_session(credentials.credentials)
        return session_info
    except AuthServiceError as e:
        raise HTTPException(
            status_code=_error_code_to_status(e.code),
            detail=ErrorResponse.create(
                code=e.code,
                message=e.message,
                details=e.details,
            ).model_dump(),
            headers={"WWW-Authenticate": "Bearer"} if e.code in [ErrorCode.AUTH_REQUIRED, ErrorCode.AUTH_EXPIRED] else None,
        )
    except Exception as e:
        logger.exception("Authentication failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(ErrorCode.INTERNAL_ERROR, str(e)).model_dump(),
        )


def require_capability(capability: str) -> Callable:
    """
    Dependency that requires a specific capability.

    Args:
        capability: Required capability

    Returns:
        Dependency function
    """
    async def _require_capability(
        session_info: SessionInfo = Depends(require_auth),
        session: AsyncSession = Depends(get_session),
    ) -> SessionInfo:
        """
        Check if the session has the required capability.
        """
        from sqlalchemy import text
        import json

        # Get capabilities from certificate
        result = await session.execute(
            text("SELECT capabilities FROM certificates WHERE cert_id = :cert_id"),
            {"cert_id": session_info.cert_id}
        )
        row = result.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse.create(
                    ErrorCode.PERMISSION_DENIED,
                    "Certificate not found",
                ).model_dump(),
            )

        capabilities = json.loads(row[0]) if row[0] else []

        if capability not in capabilities:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse.create(
                    ErrorCode.PERMISSION_DENIED,
                    f"Capability '{capability}' required",
                    {"required_capability": capability, "available_capabilities": capabilities},
                ).model_dump(),
            )

        return session_info

    return _require_capability


def _error_code_to_status(code: ErrorCode) -> int:
    """Map error code to HTTP status code."""
    mapping = {
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.INVALID_CAPABILITY: 400,
        ErrorCode.INVALID_ATTENUATIONS: 400,
        ErrorCode.INVALID_DELEGATION_DEPTH: 400,
        ErrorCode.DELEGATION_EXPIRY_EXCEEDS_PARENT: 400,
        ErrorCode.AUTH_REQUIRED: 401,
        ErrorCode.AUTH_EXPIRED: 401,
        ErrorCode.AUTH_INVALID_SIGNATURE: 401,
        ErrorCode.PERMISSION_DENIED: 403,
        ErrorCode.CERTIFICATE_REVOKED: 403,
        ErrorCode.CERTIFICATE_EXPIRED: 403,
        ErrorCode.TOKEN_EXPIRED: 403,
        ErrorCode.DELEGATION_CHAIN_INVALID: 403,
        ErrorCode.AGENT_SUSPENDED: 403,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.CONFLICT: 409,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.INTERNAL_ERROR: 500,
    }
    return mapping.get(code, 500)
