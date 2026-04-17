"""
CA Service API routes.

Handles agent registration, authentication, and certificate revocation.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import (
    CARegisterRequest,
    CARegisterResponse,
    CertificateResponse,
    CapabilityTokenResponse,
    ChallengeRequest,
    ChallengeResponse,
    VerifyRequest,
    VerifyResponse,
    RevokeRequest,
    RevokeResponse,
    CRLResponse,
    AgentInfoResponse,
    ErrorResponse,
    ErrorCode,
)
from app.services.ca_service import CAService, CAServiceError
from app.services.auth_service import AuthService, AuthServiceError
from app.middleware.auth import get_current_session, require_capability

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ca", tags=["CA Service"])
security = HTTPBearer(auto_error=False)


@router.post(
    "/register",
    response_model=CARegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        409: {"model": ErrorResponse, "description": "Agent name already exists"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
    summary="Register a new agent",
    description="Register a new agent and issue certificate with capability tokens.",
)
async def register_agent(
    request: CARegisterRequest,
    session: AsyncSession = Depends(get_session),
):
    """Register a new agent and issue certificate."""
    try:
        ca_service = CAService(session)
        result = await ca_service.register_agent(
            name=request.name,
            public_key_pem=request.public_key,
            owner=request.owner,
            requested_capabilities=request.requested_capabilities,
            description=request.description,
            trust_level=request.trust_level,
            cert_validity_hours=request.cert_validity_hours,
        )

        return CARegisterResponse(
            agent_id=result["agent_id"],
            certificate=CertificateResponse(
                cert_id=result["certificate"]["cert_id"],
                public_key=result["certificate"]["public_key"],
                issuer_key_id=result["certificate"]["issuer_key_id"],
                capabilities=result["certificate"]["capabilities"],
                trust_level=result["certificate"]["trust_level"],
                algorithm=result["certificate"]["algorithm"],
                issued_at=result["certificate"]["issued_at"],
                expires_at=result["certificate"]["expires_at"],
                signature=result["certificate"]["signature"],
            ),
            capability_tokens=[
                CapabilityTokenResponse(
                    token_id=token["token_id"],
                    capability=token["capability"],
                    resource_scope=token["resource_scope"],
                    attenuations=token["attenuations"],
                    expires_at=token["expires_at"],
                )
                for token in result["capability_tokens"]
            ],
        )
    except CAServiceError as e:
        raise _service_error_to_http(e)
    except Exception as e:
        logger.exception("Registration failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(ErrorCode.INTERNAL_ERROR, str(e)).model_dump(),
        )


@router.post(
    "/auth/challenge",
    response_model=ChallengeResponse,
    responses={
        403: {"model": ErrorResponse, "description": "Certificate revoked/expired or agent suspended"},
        404: {"model": ErrorResponse, "description": "Agent or certificate not found"},
    },
    summary="Request authentication challenge",
    description="Get a challenge nonce for challenge-response authentication.",
)
async def get_challenge(
    request: ChallengeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Request a challenge for authentication."""
    try:
        ca_service = CAService(session)
        result = await ca_service.create_challenge(
            agent_id=request.agent_id,
            cert_id=request.cert_id,
        )

        return ChallengeResponse(
            challenge_id=result["challenge_id"],
            nonce=result["nonce"],
            expires_at=result["expires_at"],
        )
    except CAServiceError as e:
        raise _service_error_to_http(e)
    except Exception as e:
        logger.exception("Challenge creation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(ErrorCode.INTERNAL_ERROR, str(e)).model_dump(),
        )


@router.post(
    "/auth/verify",
    response_model=VerifyResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication failed"},
    },
    summary="Verify challenge signature",
    description="Submit signed challenge to get session token.",
)
async def verify_signature(
    request: VerifyRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify challenge signature and issue session token."""
    try:
        ca_service = CAService(session)
        result = await ca_service.verify_challenge(
            challenge_id=request.challenge_id,
            agent_id=request.agent_id,
            signed_nonce=request.signed_nonce,
        )

        return VerifyResponse(
            session_token=result["session_token"],
            expires_at=result["expires_at"],
            agent_id=result["agent_id"],
        )
    except CAServiceError as e:
        raise _service_error_to_http(e)
    except Exception as e:
        logger.exception("Verification failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(ErrorCode.INTERNAL_ERROR, str(e)).model_dump(),
        )


@router.post(
    "/revoke",
    response_model=RevokeResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Certificate not found"},
        409: {"model": ErrorResponse, "description": "Certificate already revoked"},
    },
    summary="Revoke a certificate",
    description="Revoke a certificate and add to CRL. Requires manage_agents capability.",
)
async def revoke_certificate(
    request: RevokeRequest,
    session: AsyncSession = Depends(get_session),
    session_info = Depends(require_capability("manage_agents")),
):
    """Revoke a certificate."""
    try:
        ca_service = CAService(session)
        result = await ca_service.revoke_certificate(
            cert_id=request.cert_id,
            reason=request.reason,
            revoked_by=session_info.agent_id,
        )

        return RevokeResponse(
            cert_id=result["cert_id"],
            status=result["status"],
            revoked_at=result["revoked_at"],
        )
    except CAServiceError as e:
        raise _service_error_to_http(e)
    except Exception as e:
        logger.exception("Revocation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(ErrorCode.INTERNAL_ERROR, str(e)).model_dump(),
        )


@router.get(
    "/crl",
    response_model=CRLResponse,
    summary="Get Certificate Revocation List",
    description="Get the list of all revoked certificates.",
)
async def get_crl(
    session: AsyncSession = Depends(get_session),
):
    """Get Certificate Revocation List."""
    try:
        ca_service = CAService(session)
        result = await ca_service.get_crl()

        return CRLResponse(
            crl_version=result["crl_version"],
            updated_at=result["updated_at"],
            entries=result["entries"],
        )
    except Exception as e:
        logger.exception("CRL retrieval failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(ErrorCode.INTERNAL_ERROR, str(e)).model_dump(),
        )


# =============================================================================
# Helper functions
# =============================================================================

def _service_error_to_http(error: CAServiceError) -> HTTPException:
    """Convert service error to HTTP exception."""
    status_code = _error_code_to_status(error.code)
    return HTTPException(
        status_code=status_code,
        detail=ErrorResponse.create(
            code=error.code,
            message=error.message,
            details=error.details,
        ).model_dump(),
    )


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
