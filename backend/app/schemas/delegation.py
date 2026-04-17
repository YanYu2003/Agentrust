"""
Pydantic schemas for Delegation API.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class DelegateRequest(BaseModel):
    """Delegation creation request model."""
    to_agent_id: str = Field(..., description="Target agent to delegate to")
    parent_token_id: str = Field(..., description="Parent token ID")
    parent_token_type: str = Field(..., description="Parent token type: 'capability' or 'delegation'")
    capability: str = Field(..., description="Capability to delegate")
    resource_scope: str = Field(..., description="Resource scope for delegation")
    attenuations: Dict[str, Any] = Field(default_factory=dict, description="Attenuation parameters")
    max_depth: Optional[int] = Field(None, ge=0, le=10, description="Maximum delegation depth")
    validity_minutes: int = Field(60, ge=1, le=1440, description="Validity duration in minutes")

    @field_validator("parent_token_type")
    @classmethod
    def validate_parent_token_type(cls, v: str) -> str:
        """Validate parent token type."""
        if v not in ("capability", "delegation"):
            raise ValueError("parent_token_type must be 'capability' or 'delegation'")
        return v


class DelegationTokenResponse(BaseModel):
    """Delegation token response model."""
    delegation_id: str
    from_agent_id: str
    to_agent_id: str
    capability: str
    resource_scope: str
    attenuations: Dict[str, Any]
    max_depth: int
    current_depth: int
    issued_at: str
    expires_at: str
    from_signature: str
    status: str


class DelegateResponse(BaseModel):
    """Delegation creation response model."""
    delegation_token: DelegationTokenResponse


class CapabilityTokenInfo(BaseModel):
    """Capability token info for query response."""
    token_id: str
    capability: str
    resource_scope: str
    attenuations: Dict[str, Any]
    expires_at: str
    status: str


class DelegationTokenInfo(BaseModel):
    """Delegation token info for query response."""
    delegation_id: str
    from_agent_id: Optional[str] = None  # For received tokens
    to_agent_id: Optional[str] = None    # For issued tokens
    capability: str
    attenuations: Dict[str, Any]
    current_depth: int
    expires_at: str
    status: str


class AgentTokensResponse(BaseModel):
    """Agent tokens query response model."""
    agent_id: str
    capability_tokens: List[CapabilityTokenInfo] = []
    delegation_tokens_received: List[DelegationTokenInfo] = []
    delegation_tokens_issued: List[DelegationTokenInfo] = []
