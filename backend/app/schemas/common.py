"""
Pydantic schemas for API request/response models.
"""

import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class ErrorCode(str, Enum):
    """Error code constants."""
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_CAPABILITY = "INVALID_CAPABILITY"
    INVALID_ATTENUATIONS = "INVALID_ATTENUATIONS"
    INVALID_DELEGATION_DEPTH = "INVALID_DELEGATION_DEPTH"
    DELEGATION_EXPIRY_EXCEEDS_PARENT = "DELEGATION_EXPIRY_EXCEEDS_PARENT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_INVALID_SIGNATURE = "AUTH_INVALID_SIGNATURE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CERTIFICATE_REVOKED = "CERTIFICATE_REVOKED"
    CERTIFICATE_EXPIRED = "CERTIFICATE_EXPIRED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    DELEGATION_CHAIN_INVALID = "DELEGATION_CHAIN_INVALID"
    AGENT_SUSPENDED = "AGENT_SUSPENDED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AgentStatus(str, Enum):
    """Agent status enum."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class CertificateStatus(str, Enum):
    """Certificate status enum."""
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ChallengeStatus(str, Enum):
    """Challenge status enum."""
    PENDING = "pending"
    USED = "used"
    EXPIRED = "expired"


# =============================================================================
# Valid capabilities
# =============================================================================

VALID_CAPABILITIES = {
    "read_database",
    "write_database",
    "delete_database",
    "read_document",
    "write_document",
    "delete_document",
    "send_message",
    "manage_agents",
    "read_bitable",
    "write_bitable",
    "read_doc",
    "write_doc",
    "read_calendar",
    "create_meeting",
}


# =============================================================================
# Error Response
# =============================================================================

class ErrorResponse(BaseModel):
    """Unified error response format."""
    error: Dict[str, Any] = Field(..., description="Error information")

    @classmethod
    def create(
        cls,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> "ErrorResponse":
        """Create an error response."""
        error_data = {
            "code": code.value,
            "message": message,
        }
        if details:
            error_data["details"] = details
        if request_id:
            error_data["request_id"] = request_id
        error_data["timestamp"] = _now_iso()
        return cls(error=error_data)


def _now_iso() -> str:
    """Get current ISO8601 timestamp."""
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"


# =============================================================================
# CA Register
# =============================================================================

class CARegisterRequest(BaseModel):
    """CA register request model."""
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    public_key: str = Field(..., description="PEM-encoded ECDSA P-256 public key")
    owner: str = Field(..., min_length=1, max_length=128)
    requested_capabilities: List[str] = Field(..., min_length=1)
    description: str = Field("", max_length=256)
    trust_level: int = Field(1, ge=1, le=5)
    cert_validity_hours: Optional[int] = Field(None, ge=1, le=720)

    @field_validator("requested_capabilities")
    @classmethod
    def validate_capabilities(cls, v: List[str]) -> List[str]:
        """Validate that all capabilities are valid."""
        invalid = [cap for cap in v if cap not in VALID_CAPABILITIES]
        if invalid:
            raise ValueError(f"Invalid capabilities: {invalid}")
        return v


class CertificateResponse(BaseModel):
    """Certificate response model."""
    cert_id: str
    public_key: str
    issuer_key_id: str
    capabilities: List[str]
    trust_level: int
    algorithm: str
    issued_at: str
    expires_at: str
    signature: str


class CapabilityTokenResponse(BaseModel):
    """Capability token response model."""
    token_id: str
    capability: str
    resource_scope: str
    attenuations: Dict[str, Any]
    expires_at: str


class CARegisterResponse(BaseModel):
    """CA register response model."""
    agent_id: str
    certificate: CertificateResponse
    capability_tokens: List[CapabilityTokenResponse]


# =============================================================================
# Challenge-Response Auth
# =============================================================================

class ChallengeRequest(BaseModel):
    """Challenge request model."""
    agent_id: str
    cert_id: str


class ChallengeResponse(BaseModel):
    """Challenge response model."""
    challenge_id: str
    nonce: str
    expires_at: str


class VerifyRequest(BaseModel):
    """Verify signature request model."""
    challenge_id: str
    agent_id: str
    signed_nonce: str  # Base64-encoded signature


class VerifyResponse(BaseModel):
    """Verify response model."""
    session_token: str
    expires_at: str
    agent_id: str


# =============================================================================
# Certificate Revocation
# =============================================================================

class RevokeRequest(BaseModel):
    """Revoke certificate request model."""
    cert_id: str
    reason: str = Field(..., max_length=256)


class RevokeResponse(BaseModel):
    """Revoke response model."""
    cert_id: str
    status: str
    revoked_at: str


class CRLEntry(BaseModel):
    """CRL entry model."""
    cert_id: str
    revoked_at: str
    reason: str


class CRLResponse(BaseModel):
    """CRL response model."""
    crl_version: int
    updated_at: str
    entries: List[CRLEntry]


# =============================================================================
# Agent Info
# =============================================================================

class AgentInfoResponse(BaseModel):
    """Agent info response model."""
    agent_id: str
    name: str
    description: str
    owner: str
    trust_level: int
    status: str
    registered_at: str
    certificates: List[Dict[str, Any]] = []
    active_capability_tokens: int = 0
    active_delegations_from: int = 0
    active_delegations_to: int = 0


# =============================================================================
# Session Info (for middleware)
# =============================================================================

class SessionInfo(BaseModel):
    """Session information extracted from session_token."""
    session_id: str
    agent_id: str
    cert_id: str
    issued_at: str
    expires_at: str
    challenge_id: str
    trust_level: int
