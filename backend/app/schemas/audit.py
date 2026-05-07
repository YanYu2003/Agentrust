"""
Pydantic schemas for Audit API.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AuditLogSummary(BaseModel):
    """Audit log summary for list view."""
    log_id: str
    agent_id: str
    parent_agent_id: Optional[str] = None
    task_id: Optional[str] = None
    action: str
    resource: str
    result: str  # "ALLOWED", "DENIED", "ERROR"
    delegation_chain_summary: Optional[str] = None
    created_at: str


class AuditLogListResponse(BaseModel):
    """Response model for audit log list."""
    total: int
    page: int
    page_size: int
    logs: List[AuditLogSummary]


class TokenChainItemDetail(BaseModel):
    """Single item in token chain for detail view."""
    type: str  # "certificate", "capability", "delegation"
    token_id: str
    agent: Optional[str] = None
    capability: Optional[str] = None
    from_agent: Optional[str] = None
    to_agent: Optional[str] = None
    attenuations: Optional[Dict[str, Any]] = None


class RequestContext(BaseModel):
    """Request context information."""
    ip: str
    user_agent: str
    method: str
    path: str


class AuditLogDetailResponse(BaseModel):
    """Response model for single audit log detail."""
    log_id: str
    agent_id: str
    parent_agent_id: Optional[str] = None
    task_id: Optional[str] = None
    action: str
    resource: str
    result: str
    token_chain: List[Dict[str, Any]]
    request_context: Dict[str, Any]
    task_context: Dict[str, Any] = Field(default_factory=dict)
    delegation_chain_summary: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: str


class DelegationGraphNode(BaseModel):
    """Node in delegation graph."""
    id: str
    name: str
    trust_level: int
    status: str


class DelegationGraphEdge(BaseModel):
    """Edge in delegation graph."""
    from_agent: str
    to_agent: str
    delegation_id: str
    capability: str
    attenuations: Dict[str, Any]
    status: str
    expires_at: str


class DelegationGraphResponse(BaseModel):
    """Response model for delegation graph."""
    nodes: List[DelegationGraphNode]
    edges: List[DelegationGraphEdge]


class AlertStatusResponse(BaseModel):
    """Response model for alert status."""
    enabled: bool
    threshold: int
    window_minutes: int
    recent_denial_count: int
    is_above_threshold: bool
    last_checked_at: str


class RecentTaskSummary(BaseModel):
    """One row for recent task_id picker."""
    task_id: str
    step_count: int
    last_at: str


class RecentTasksResponse(BaseModel):
    """Recent tasks with audit trail."""
    tasks: List[RecentTaskSummary]


class TaskTraceStep(BaseModel):
    """Single step in a task trace."""
    log_id: str
    agent_id: str
    parent_agent_id: Optional[str] = None
    task_id: Optional[str] = None
    action: str
    resource: str
    result: str
    request_context: Dict[str, Any] = Field(default_factory=dict)
    task_context: Dict[str, Any] = Field(default_factory=dict)
    error_detail: Optional[str] = None
    created_at: str


class TaskTraceResponse(BaseModel):
    """Full trace for one task_id."""
    task_id: str
    total_steps: int
    trace: List[TaskTraceStep]


class AuditLogQueryParams(BaseModel):
    """Query parameters for audit log list."""
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
