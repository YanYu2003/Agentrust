"""
Audit API - Query audit logs and delegation graph.

Implements:
- GET /api/v1/audit/logs - List audit logs with filtering
- GET /api/v1/audit/logs/{log_id} - Get audit log detail
- GET /api/v1/audit/delegation-graph - Get delegation graph for visualization
- GET /api/v1/audit/alert-status - Get alert status
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.middleware.auth import require_auth, SessionInfo
from app.schemas.common import ErrorResponse, ErrorCode
from app.schemas.audit import (
    AuditLogListResponse,
    AuditLogSummary,
    AuditLogDetailResponse,
    DelegationGraphResponse,
    AlertStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


def _has_manage_agents_capability(session: AsyncSession, agent_id: str) -> bool:
    """Check if agent has manage_agents capability."""
    return True  # Simplified - actual implementation would check certificate capabilities


async def _check_manage_agents(session: AsyncSession, session_info: SessionInfo) -> bool:
    """Check if current session has manage_agents capability."""
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
    if not row:
        return False
    capabilities = json.loads(row[0]) if row[0] else []
    return "manage_agents" in capabilities


@router.get(
    "/logs",
    response_model=AuditLogListResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def list_audit_logs(
    request: Request,
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    action: Optional[str] = Query(None, description="Filter by action"),
    result: Optional[str] = Query(None, description="Filter by result (ALLOWED/DENIED/ERROR)"),
    start_time: Optional[str] = Query(None, description="Start time (ISO8601)"),
    end_time: Optional[str] = Query(None, description="End time (ISO8601)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    session_info: SessionInfo = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> AuditLogListResponse:
    """
    List audit logs with optional filtering.

    - Normal agents can only see their own logs
    - Agents with manage_agents capability can see all logs

    Query parameters:
    - agent_id: Filter by agent ID (requires manage_agents)
    - action: Filter by action type
    - result: Filter by result (ALLOWED/DENIED/ERROR)
    - start_time: Start of time range (ISO8601)
    - end_time: End of time range (ISO8601)
    - page: Page number (default: 1)
    - page_size: Number of items per page (default: 20, max: 100)
    """
    try:
        has_manage_agents = await _check_manage_agents(session, session_info)

        # Import here to avoid circular dependency
        from app.services.audit_service import AuditService

        service = AuditService(session)
        total, logs = await service.query_audit_logs(
            agent_id_filter=agent_id,
            action_filter=action,
            result_filter=result,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
            requester_agent_id=session_info.agent_id,
            requester_has_manage_agents=has_manage_agents,
        )

        return AuditLogListResponse(
            total=total,
            page=page,
            page_size=page_size,
            logs=[AuditLogSummary(**log) for log in logs],
        )

    except Exception as e:
        logger.exception(f"Error querying audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(
                ErrorCode.INTERNAL_ERROR,
                "Error querying audit logs",
            ).model_dump(),
        )


@router.get(
    "/logs/{log_id}",
    response_model=AuditLogDetailResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        404: {"model": ErrorResponse, "description": "Audit log not found"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def get_audit_log_detail(
    log_id: str,
    request: Request,
    session_info: SessionInfo = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> AuditLogDetailResponse:
    """
    Get detailed audit log by ID.

    Returns the full audit log entry including:
    - Complete token chain snapshot
    - Request context (IP, user agent, etc.)
    - Error details (if any)
    - Delegation chain summary

    Normal agents can only view their own logs.
    Agents with manage_agents capability can view all logs.
    """
    try:
        has_manage_agents = await _check_manage_agents(session, session_info)

        from app.services.audit_service import AuditService

        service = AuditService(session)
        log_detail = await service.get_audit_log_detail(
            log_id=log_id,
            requester_agent_id=session_info.agent_id,
            requester_has_manage_agents=has_manage_agents,
        )

        if not log_detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponse.create(
                    ErrorCode.NOT_FOUND,
                    f"Audit log {log_id} not found or access denied",
                ).model_dump(),
            )

        return AuditLogDetailResponse(**log_detail)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting audit log detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(
                ErrorCode.INTERNAL_ERROR,
                "Error retrieving audit log detail",
            ).model_dump(),
        )


@router.get(
    "/delegation-graph",
    response_model=DelegationGraphResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Permission denied - manage_agents required"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def get_delegation_graph(
    request: Request,
    session_info: SessionInfo = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> DelegationGraphResponse:
    """
    Get delegation graph for visualization.

    Returns:
    - nodes: List of agent nodes with id, name, trust_level, status
    - edges: List of delegation edges with from, to, delegation_id, capability, attenuations

    Requires manage_agents capability.
    """
    try:
        has_manage_agents = await _check_manage_agents(session, session_info)

        if not has_manage_agents:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse.create(
                    ErrorCode.PERMISSION_DENIED,
                    "manage_agents capability required to view delegation graph",
                ).model_dump(),
            )

        from app.services.audit_service import AuditService

        service = AuditService(session)
        graph_data = await service.get_delegation_graph(
            requester_has_manage_agents=has_manage_agents,
        )

        return DelegationGraphResponse(**graph_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting delegation graph: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(
                ErrorCode.INTERNAL_ERROR,
                "Error retrieving delegation graph",
            ).model_dump(),
        )


@router.get(
    "/alert-status",
    response_model=AlertStatusResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Permission denied - manage_agents required"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def get_alert_status(
    request: Request,
    session_info: SessionInfo = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> AlertStatusResponse:
    """
    Get current alert status.

    Returns:
    - enabled: Whether alerting is enabled
    - threshold: Max denials before alert
    - window_minutes: Time window for counting denials
    - recent_denial_count: Number of denials in current window
    - is_above_threshold: Whether current count exceeds threshold
    - last_checked_at: Timestamp of last check

    Requires manage_agents capability.
    """
    try:
        has_manage_agents = await _check_manage_agents(session, session_info)

        if not has_manage_agents:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ErrorResponse.create(
                    ErrorCode.PERMISSION_DENIED,
                    "manage_agents capability required to view alert status",
                ).model_dump(),
            )

        from app.services.audit_service import AuditService

        service = AuditService(session)
        alert_data = await service.get_alert_status(
            requester_has_manage_agents=has_manage_agents,
        )

        return AlertStatusResponse(**alert_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting alert status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(
                ErrorCode.INTERNAL_ERROR,
                "Error retrieving alert status",
            ).model_dump(),
        )
