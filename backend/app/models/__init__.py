"""
Data models for database entities.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class Agent:
    """Agent entity."""

    agent_id: str
    name: str
    owner: str
    trust_level: int = 1
    description: str = ""
    status: str = "active"
    registered_at: str = ""

    def __post_init__(self):
        if not self.registered_at:
            from app.utils import now_iso
            self.registered_at = now_iso()


@dataclass
class Certificate:
    """Certificate entity."""

    cert_id: str
    agent_id: str
    public_key: bytes
    issuer_key_id: str
    signature: bytes
    capabilities: List[str]
    trust_level: int
    algorithm: str = "ES256"
    issued_at: str = ""
    expires_at: str = ""
    status: str = "valid"

    def __post_init__(self):
        if not self.issued_at:
            from app.utils import now_iso
            self.issued_at = now_iso()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        import base64
        return {
            "cert_id": self.cert_id,
            "agent_id": self.agent_id,
            "public_key": self.public_key.decode() if isinstance(self.public_key, bytes) else self.public_key,
            "issuer_key_id": self.issuer_key_id,
            "signature": base64.b64encode(self.signature).decode() if self.signature else "",
            "capabilities": self.capabilities,
            "trust_level": self.trust_level,
            "algorithm": self.algorithm,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }


@dataclass
class CapabilityToken:
    """Capability token entity."""

    token_id: str
    holder_agent_id: str
    cert_id: str
    capability: str
    resource_scope: str = "*"
    attenuations: Dict[str, Any] = field(default_factory=dict)
    issued_at: str = ""
    expires_at: str = ""
    signature: bytes = b""

    def __post_init__(self):
        if not self.issued_at:
            from app.utils import now_iso
            self.issued_at = now_iso()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        import base64
        return {
            "token_id": self.token_id,
            "holder_agent_id": self.holder_agent_id,
            "cert_id": self.cert_id,
            "capability": self.capability,
            "resource_scope": self.resource_scope,
            "attenuations": self.attenuations,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature": base64.b64encode(self.signature).decode() if self.signature else "",
        }


@dataclass
class DelegationToken:
    """Delegation token entity."""

    delegation_id: str
    from_agent_id: str
    to_agent_id: str
    parent_token_id: str
    parent_token_type: str
    capability: str
    resource_scope: str
    attenuations: Dict[str, Any] = field(default_factory=dict)
    max_depth: int = 1
    current_depth: int = 0
    issued_at: str = ""
    expires_at: str = ""
    from_signature: bytes = b""
    status: str = "active"

    def __post_init__(self):
        if not self.issued_at:
            from app.utils import now_iso
            self.issued_at = now_iso()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        import base64
        return {
            "delegation_id": self.delegation_id,
            "from_agent_id": self.from_agent_id,
            "to_agent_id": self.to_agent_id,
            "parent_token_id": self.parent_token_id,
            "parent_token_type": self.parent_token_type,
            "capability": self.capability,
            "resource_scope": self.resource_scope,
            "attenuations": self.attenuations,
            "max_depth": self.max_depth,
            "current_depth": self.current_depth,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "from_signature": base64.b64encode(self.from_signature).decode() if self.from_signature else "",
            "status": self.status,
        }


@dataclass
class CRLEntry:
    """Certificate Revocation List entry."""

    entry_id: str
    cert_id: str
    reason: str
    revoked_at: str = ""
    revoked_by: str = ""

    def __post_init__(self):
        if not self.revoked_at:
            from app.utils import now_iso
            self.revoked_at = now_iso()


@dataclass
class AuditLog:
    """Audit log entry."""

    log_id: str
    agent_id: str
    action: str
    resource: str
    result: str
    token_chain: List[Dict[str, Any]] = field(default_factory=list)
    request_context: Dict[str, Any] = field(default_factory=dict)
    delegation_chain_summary: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            from app.utils import now_iso
            self.created_at = now_iso()


@dataclass
class CARootKey:
    """CA root key entity."""

    key_id: str
    public_key: bytes
    encrypted_private_key: bytes
    algorithm: str = "ES256"
    created_at: str = ""
    expires_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            from app.utils import now_iso
            self.created_at = now_iso()


# Global capability set
GLOBAL_CAPABILITIES = {
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

# Destructive operations that trust_level=1 agents cannot perform
DESTRUCTIVE_OPERATIONS = {
    "write_database",
    "delete_database",
    "delete_document",
    "manage_agents",
}
