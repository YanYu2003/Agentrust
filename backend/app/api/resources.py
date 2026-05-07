"""
Resource Gateway API - Execute protected operations.

Implements POST /api/v1/resources/execute endpoint.
"""

import json
import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.middleware.auth import require_auth, SessionInfo
from app.schemas.common import ErrorResponse, ErrorCode
from app.schemas.resources import (
    ExecuteRequest,
    ExecuteResponse,
    ExecuteResult,
    VerificationInfo,
    AuditLogCreate,
)
from app.services.token_verifier import TokenVerifier, TokenVerificationError
from app.services.executor import ResourceExecutor, ExecutionError
from app.utils import generate_id, now_iso

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["resources"])


@router.post(
    "/execute",
    response_model=ExecuteResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Token not found"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def execute_resource(
    request: Request,
    execute_req: ExecuteRequest,
    session_info: SessionInfo = Depends(require_auth),
    session: AsyncSession = Depends(get_session),
) -> ExecuteResponse:
    """
    Execute a protected resource operation.

    This endpoint:
    1. Verifies the token chain
    2. Checks permissions against requested action/resource
    3. Executes the operation with attenuation parameters
    4. Records an audit log

    Requires a valid session_token in Authorization header.
    """
    audit_log = None
    verification_info = None

    try:
        # Initialize services
        verifier = TokenVerifier(session)
        executor = ResourceExecutor()

        # Convert token chain to dict format for verifier
        token_chain = [
            {"token_id": item.token_id, "token_type": item.token_type.value}
            for item in execute_req.token_chain
        ]

        # Verify token chain
        verification_result = await verifier.verify_token_chain(
            token_chain=token_chain,
            requested_action=execute_req.action,
            requested_resource=execute_req.resource,
            session_agent_id=session_info.agent_id,
        )

        verification_info = VerificationInfo(
            token_chain_valid=True,
            chain_length=verification_result.chain_length,
            effective_attenuations=verification_result.effective_attenuations,
            delegation_path=verification_result.delegation_path,
        )

        # Execute the operation
        result_data, applied_attenuations = await executor.execute(
            action=execute_req.action,
            resource=execute_req.resource,
            params=execute_req.params,
            attenuations=verification_result.effective_attenuations,
        )

        # Build result
        execute_result = ExecuteResult(**result_data)

        # Record audit log (success)
        await _record_audit_log(
            session=session,
            agent_id=session_info.agent_id,
            action=execute_req.action,
            resource=execute_req.resource,
            result="ALLOWED",
            token_chain=token_chain,
            request_context=_get_request_context(request),
            delegation_chain_summary=verification_result.delegation_path,
            task_id=execute_req.task_id,
            parent_agent_id=execute_req.parent_agent_id,
            task_context=_merge_audit_task_context(
                execute_req,
                result_snapshot=execute_result.model_dump(exclude_none=True),
            ),
        )

        await session.commit()

        return ExecuteResponse(
            result=execute_result,
            verification=verification_info,
            attenuations_applied=applied_attenuations,
        )

    except TokenVerificationError as e:
        logger.warning(f"Token verification failed: {e.message}")

        # Record audit log (denied)
        await _record_audit_log(
            session=session,
            agent_id=session_info.agent_id,
            action=execute_req.action,
            resource=execute_req.resource,
            result="DENIED",
            token_chain=[item.model_dump() for item in execute_req.token_chain],
            request_context=_get_request_context(request),
            delegation_chain_summary=None,
            error_detail=e.message,
            task_id=execute_req.task_id,
            parent_agent_id=execute_req.parent_agent_id,
            task_context=_merge_audit_task_context(execute_req, error=e.message),
        )
        await session.commit()

        raise HTTPException(
            status_code=_error_code_to_status(e.code),
            detail=ErrorResponse.create(
                code=e.code,
                message=e.message,
                details=e.details,
            ).model_dump(),
        )

    except ExecutionError as e:
        logger.warning(f"Execution failed: {e.message}")

        # Record audit log (error)
        await _record_audit_log(
            session=session,
            agent_id=session_info.agent_id,
            action=execute_req.action,
            resource=execute_req.resource,
            result="ERROR",
            token_chain=[item.model_dump() for item in execute_req.token_chain],
            request_context=_get_request_context(request),
            delegation_chain_summary=None,
            error_detail=e.message,
            task_id=execute_req.task_id,
            parent_agent_id=execute_req.parent_agent_id,
            task_context=_merge_audit_task_context(execute_req, error=e.message),
        )
        await session.commit()

        raise HTTPException(
            status_code=_error_code_to_status(e.code),
            detail=ErrorResponse.create(
                code=e.code,
                message=e.message,
                details=e.details,
            ).model_dump(),
        )

    except Exception as e:
        logger.exception(f"Unexpected error during resource execution: {e}")

        # Record audit log (error)
        try:
            await _record_audit_log(
                session=session,
                agent_id=session_info.agent_id,
                action=execute_req.action,
                resource=execute_req.resource,
                result="ERROR",
                token_chain=[item.model_dump() for item in execute_req.token_chain],
                request_context=_get_request_context(request),
                delegation_chain_summary=None,
                error_detail=str(e),
                task_id=execute_req.task_id,
                parent_agent_id=execute_req.parent_agent_id,
                task_context=_merge_audit_task_context(execute_req, error=str(e)),
            )
            await session.commit()
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponse.create(
                ErrorCode.INTERNAL_ERROR,
                "Internal server error during resource execution",
            ).model_dump(),
        )


def _merge_audit_task_context(
    execute_req: ExecuteRequest,
    *,
    result_snapshot: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Build task_context JSON for audit (params + optional snapshot / error)."""
    ctx: Dict[str, Any] = {}
    if execute_req.task_context:
        ctx.update(execute_req.task_context)
    ctx["params"] = execute_req.params
    if result_snapshot is not None:
        ctx["result_snapshot"] = result_snapshot
    if error:
        ctx["error"] = error
    return ctx


async def _record_audit_log(
    session: AsyncSession,
    agent_id: str,
    action: str,
    resource: str,
    result: str,
    token_chain: List[Dict[str, Any]],
    request_context: Dict[str, Any],
    delegation_chain_summary: Optional[str],
    error_detail: Optional[str] = None,
    task_id: Optional[str] = None,
    parent_agent_id: Optional[str] = None,
    task_context: Optional[Dict[str, Any]] = None,
) -> None:
    """Record an audit log entry."""
    log_id = generate_id("log")
    now = now_iso()
    task_context = task_context or {}

    await session.execute(
        text("""
            INSERT INTO audit_logs
            (log_id, agent_id, parent_agent_id, task_id, action, resource, result, 
             token_chain, request_context, task_context, delegation_chain_summary, 
             error_detail, created_at)
            VALUES (:log_id, :agent_id, :parent_agent_id, :task_id, :action, :resource, 
                    :result, :token_chain, :request_context, :task_context, 
                    :delegation_chain_summary, :error_detail, :created_at)
        """),
        {
            "log_id": log_id,
            "agent_id": agent_id,
            "parent_agent_id": parent_agent_id,
            "task_id": task_id,
            "action": action,
            "resource": resource,
            "result": result,
            "token_chain": json.dumps(token_chain),
            "request_context": json.dumps(request_context),
            "task_context": json.dumps(task_context),
            "delegation_chain_summary": delegation_chain_summary,
            "error_detail": error_detail,
            "created_at": now,
        }
    )


def _get_request_context(request: Request) -> Dict[str, Any]:
    """Extract request context for audit logging."""
    return {
        "ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "method": request.method,
        "path": str(request.url.path),
    }


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
