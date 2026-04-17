"""
Pydantic schemas for Resource Gateway API.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from app.schemas.common import VALID_CAPABILITIES


class TokenType(str, Enum):
    """Token type in the chain."""
    CERTIFICATE = "certificate"
    CAPABILITY = "capability"
    DELEGATION = "delegation"


class TokenChainItem(BaseModel):
    """Single item in a token chain."""
    token_id: str = Field(..., description="Token identifier")
    token_type: TokenType = Field(..., description="Token type")

    @field_validator("token_id")
    @classmethod
    def validate_token_id(cls, v: str) -> str:
        """Validate token ID format."""
        if not v or len(v) < 3:
            raise ValueError("token_id must be at least 3 characters")
        return v


class ExecuteRequest(BaseModel):
    """Resource execute request model."""
    action: str = Field(..., description="Action to perform")
    resource: str = Field(..., description="Target resource")
    params: Optional[Dict[str, Any]] = Field(default=None, description="Operation parameters")
    token_chain: List[TokenChainItem] = Field(
        ...,
        min_length=2,
        description="Token chain (certificate -> capability -> [delegations])"
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Validate action is a known capability."""
        if v not in VALID_CAPABILITIES:
            raise ValueError(f"Invalid action: {v}. Must be one of {VALID_CAPABILITIES}")
        return v


class VerificationInfo(BaseModel):
    """Token chain verification information."""
    token_chain_valid: bool
    chain_length: int
    effective_attenuations: Dict[str, Any]
    delegation_path: str


class ExecuteResult(BaseModel):
    """Resource execution result."""
    action: str
    resource: str
    data: Optional[Any] = None
    rows_returned: Optional[int] = None
    status: Optional[str] = None
    message_id: Optional[str] = None
    meeting_id: Optional[str] = None
    document: Optional[Dict[str, Any]] = None
    events: Optional[List[Dict[str, Any]]] = None
    rows_affected: Optional[int] = None
    bytes_written: Optional[int] = None
    recipient: Optional[str] = None
    sections: Optional[int] = None
    content: Optional[str] = None
    operation: Optional[str] = None
    topic: Optional[str] = None


class ExecuteResponse(BaseModel):
    """Resource execute response model."""
    result: ExecuteResult
    verification: VerificationInfo
    attenuations_applied: Dict[str, Any] = Field(default_factory=dict)


class AuditLogCreate(BaseModel):
    """Audit log creation model (internal use)."""
    agent_id: str
    action: str
    resource: str
    result: str  # "ALLOWED", "DENIED", "ERROR"
    token_chain: List[Dict[str, Any]]
    request_context: Dict[str, Any] = Field(default_factory=dict)
    delegation_chain_summary: Optional[str] = None
    error_detail: Optional[str] = None
