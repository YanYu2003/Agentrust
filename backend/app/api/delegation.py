"""
Delegation API - Create and manage delegation tokens.

Implements:
- POST /api/v1/delegate - Create a delegation token
- GET /api/v1/agents/{agent_id}/tokens - Query agent's tokens
"""

import json
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.middleware.auth import require_auth, SessionInfo
from app.schemas.common import ErrorResponse, ErrorCode
from app.schemas.delegation import (
    DelegateRequest,
    DelegateResponse,
    DelegationTokenResponse,
    AgentTokensResponse,
)
from app.services.delegation_service import DelegationService, DelegationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/delegate", tags=["delegation"])


@router.post(
    "",
    response_model=DelegateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Token or agent not found"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def create_delegation(
    request: Request,
    delegate_req: DelegateRequest,
    session_info: SessionInfo = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> DelegateResponse:
    """
    Create a delegation token.

    This endpoint allows an agent to delegate part of their capabilities
    to another agent with optional attenuation parameters.

    The delegation:
    - Must be for a capability the delegator owns
    - Must have resource scope that is a subset of parent
    - Must have attenuations that are stricter than parent
    - Cannot exceed parent's expiry time
    - Is limited by delegation depth
    """
    try:
        service = DelegationService(session)

        result = await service.create_delegation(
            from_agent_id=session_info.agent_id,
            to_agent_id=delegate_req.to_agent_id,
            parent_token_id=delegate_req.parent_token_id,
            parent_token_type=delegate_req.parent_token_type,
            capability=delegate_req.capability,
            resource_scope=delegate_req.resource_scope,
            attenuations=delegate_req.attenuations,
            max_depth=delegate_req.max_depth,
            validity_minutes=delegate_req.validity_minutes,
        )

        return DelegateResponse(
            delegation_token=DelegationTokenResponse(**result["delegation_token"])
        )

    except DelegationError as e:
        logger.warning(f"Delegation creation failed: {e.message}")
        raise HTTPException(
            status_code=_error_code_to_status(e.code),
            detail=ErrorResponse.create(
                code=e.code,
                message=e.message,
                details=e.details,
            ).model_dump(),
        )
    except Exception as e:
        logger.exception(f"Unexpected error during delegation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error during delegation creation",
            ).model_dump(),
        )


# Agent tokens query endpoint (separate router for /agents path)
agents_router = APIRouter(prefix="/agents", tags=["agents"])


@agents_router.get(
    "/{agent_id}/tokens",
    response_model=AgentTokensResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Agent not found"},
    },
)
async def get_agent_tokens(
    agent_id: str,
    request: Request,
    session_info: SessionInfo = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> AgentTokensResponse:
    """
    Get all tokens for an agent.

    Returns:
    - capability_tokens: Capability tokens held by the agent
    - delegation_tokens_received: Delegation tokens received from other agents
    - delegation_tokens_issued: Delegation tokens issued by this agent

    Authorization:
    - Agents can only query their own tokens
    - Agents with 'manage_agents' capability can query any agent's tokens
    """
    try:
        # Check if requesting agent has manage_agents capability
        result = await session.execute(
            text("""
                SELECT c.capabilities
                FROM certificates c
                WHERE c.agent_id = :agent_id AND c.status = 'valid'
                ORDER BY c.issued_at DESC LIMIT 1
            """),
            {"agent_id": session_info.agent_id}
        )
        row = result.fetchone()
        capabilities = json.loads(row[0]) if row and row[0] else []
        has_manage_agents = "manage_agents" in capabilities

        service = DelegationService(session)
        tokens = await service.get_agent_tokens(
            agent_id=agent_id,
            requesting_agent_id=session_info.agent_id,
            has_manage_agents=has_manage_agents,
        )

        return AgentTokensResponse(**tokens)

    except DelegationError as e:
        raise HTTPException(
            status_code=_error_code_to_status(e.code),
            detail=ErrorResponse.create(
                code=e.code,
                message=e.message,
                details=e.details,
            ).model_dump(),
        )
    except Exception as e:
        logger.exception(f"Unexpected error during token query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error during token query",
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
