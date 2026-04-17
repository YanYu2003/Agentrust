"""
Token Chain Verification - Core security logic.

Implements verification of the complete token chain including:
- Certificate chain integrity (CA signature)
- Delegation chain verification (delegator signature)
- CRL checks
- Expiration checks
- trust_level runtime constraints
"""

import base64
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crypto.keys import load_public_key_pem
from app.crypto.signature import verify_json_signature
from app.crypto.canonical import canonical_json
from app.schemas.common import ErrorCode
from app.utils import parse_iso, generate_id, now_iso
from app.services.attenuator import (
    merge_and_validate_attenuations,
    is_attenuation_stricter_or_equal,
    AttenuationError,
)

logger = logging.getLogger(__name__)


# Destructive operations that trust_level=1 agents cannot perform
DESTRUCTIVE_OPERATIONS = {
    "write_database",
    "delete_database",
    "delete_document",
    "manage_agents",
}


class TokenVerificationError(Exception):
    """Token verification error."""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class VerificationResult:
    """Result of successful token chain verification."""

    def __init__(
        self,
        agent_id: str,
        capability: str,
        resource_scope: str,
        effective_attenuations: Dict[str, Any],
        chain_length: int,
        delegation_path: str,
        trust_level: int,
        cert_id: str,
    ):
        self.agent_id = agent_id
        self.capability = capability
        self.resource_scope = resource_scope
        self.effective_attenuations = effective_attenuations
        self.chain_length = chain_length
        self.delegation_path = delegation_path
        self.trust_level = trust_level
        self.cert_id = cert_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "token_chain_valid": True,
            "chain_length": self.chain_length,
            "effective_attenuations": self.effective_attenuations,
            "delegation_path": self.delegation_path,
            "agent_id": self.agent_id,
            "capability": self.capability,
            "resource_scope": self.resource_scope,
            "trust_level": self.trust_level,
        }


class TokenVerifier:
    """Token chain verification service."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._ca_public_keys: Dict[str, Any] = {}  # Cache for CA public keys

    async def verify_token_chain(
        self,
        token_chain: List[Dict[str, str]],
        requested_action: str,
        requested_resource: str,
        session_agent_id: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verify a complete token chain.

        This is the core security function that validates:
        1. Chain structure (certificate -> capability -> [delegation]*)
        2. Certificate validity (CA signature, not revoked, not expired)
        3. Capability token validity
        4. Delegation chain integrity
        5. Permission matching (capability == action, resource in scope)
        6. trust_level constraints

        Args:
            token_chain: List of {"token_id": str, "token_type": str}
            requested_action: Action being requested (e.g., "read_database")
            requested_resource: Resource being accessed (e.g., "user_table")

        Returns:
            VerificationResult if valid

        Raises:
            TokenVerificationError: If verification fails
        """
        # ====== Step 0: Chain structure validation ======
        self._validate_chain_structure(token_chain)

        # ====== Step 1: Verify root certificate ======
        cert_info = await self._verify_certificate(token_chain[0]["token_id"])

        # trust_level runtime constraint
        if cert_info["trust_level"] == 1 and requested_action in DESTRUCTIVE_OPERATIONS:
            raise TokenVerificationError(
                ErrorCode.PERMISSION_DENIED,
                f"trust_level=1 agents cannot perform '{requested_action}'",
                {
                    "trust_level": 1,
                    "action": requested_action,
                    "reason": "destructive_operation_not_allowed"
                }
            )

        # ====== Step 2: Verify capability token ======
        cap_info = await self._verify_capability_token(
            token_chain[1]["token_id"],
            cert_info,
        )

        # Initialize effective state
        effective_capability = cap_info["capability"]
        effective_resource_scope = cap_info["resource_scope"]
        effective_attenuations = cap_info["attenuations"]
        previous_agent_id = cert_info["agent_id"]
        delegation_path = cert_info["agent_name"]

        # ====== Step 3: Verify delegation chain ======
        for i in range(2, len(token_chain)):
            del_info = await self._verify_delegation_token(
                token_chain[i]["token_id"],
                previous_agent_id,
                effective_capability,
                effective_resource_scope,
                effective_attenuations,
                i,
            )

            # Update effective state
            effective_resource_scope = del_info["resource_scope"]
            effective_attenuations = merge_and_validate_attenuations(
                effective_attenuations,
                del_info["attenuations"]
            )
            previous_agent_id = del_info["to_agent_id"]
            delegation_path += f" -> {del_info['to_agent_name']}"

        # Security check: If session_agent_id is provided, verify it matches the chain
        # If session_agent_id differs from the root cert's agent, it must be the final delegatee
        if session_agent_id is not None and session_agent_id != cert_info["agent_id"]:
            if session_agent_id != previous_agent_id:
                raise TokenVerificationError(
                    ErrorCode.DELEGATION_CHAIN_INVALID,
                    f"Session agent '{session_agent_id}' is not authorized to use this token chain (cert agent: '{cert_info['agent_id']}', final delegatee: '{previous_agent_id}')",
                    {
                        "session_agent": session_agent_id,
                        "cert_agent": cert_info["agent_id"],
                        "final_delegatee": previous_agent_id,
                    }
                )

        # ====== Step 4: Final permission check ======
        self._check_permission(
            effective_capability,
            effective_resource_scope,
            effective_attenuations,
            requested_action,
            requested_resource,
            cert_info["trust_level"],
        )

        return VerificationResult(
            agent_id=previous_agent_id,
            capability=effective_capability,
            resource_scope=effective_resource_scope,
            effective_attenuations=effective_attenuations,
            chain_length=len(token_chain),
            delegation_path=delegation_path,
            trust_level=cert_info["trust_level"],
            cert_id=cert_info["cert_id"],
        )

    def _validate_chain_structure(self, token_chain: List[Dict[str, str]]) -> None:
        """Validate the structure of the token chain."""
        if len(token_chain) < 2:
            raise TokenVerificationError(
                ErrorCode.INVALID_REQUEST,
                "Token chain must have at least 2 elements (certificate + capability)",
                {"chain_length": len(token_chain)}
            )

        # First element must be certificate
        if token_chain[0].get("token_type") != "certificate":
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                "Chain must start with a certificate",
                {"position": 0, "expected": "certificate", "got": token_chain[0].get("token_type")}
            )

        # Second element must be capability
        if token_chain[1].get("token_type") != "capability":
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                "Second element must be a capability token",
                {"position": 1, "expected": "capability", "got": token_chain[1].get("token_type")}
            )

        # Remaining elements must be delegations
        for i in range(2, len(token_chain)):
            if token_chain[i].get("token_type") != "delegation":
                raise TokenVerificationError(
                    ErrorCode.DELEGATION_CHAIN_INVALID,
                    f"Element at position {i} must be a delegation token",
                    {"position": i, "expected": "delegation", "got": token_chain[i].get("token_type")}
                )

    async def _verify_certificate(self, cert_id: str) -> Dict[str, Any]:
        """Verify a certificate's validity."""
        # Load certificate
        result = await self.session.execute(
            text("""
                SELECT c.cert_id, c.agent_id, c.public_key, c.issuer_key_id, c.signature,
                       c.capabilities, c.trust_level, c.issued_at, c.expires_at, c.status,
                       a.name as agent_name
                FROM certificates c
                JOIN agents a ON c.agent_id = a.agent_id
                WHERE c.cert_id = :cert_id
            """),
            {"cert_id": cert_id}
        )
        row = result.fetchone()

        if not row:
            raise TokenVerificationError(
                ErrorCode.NOT_FOUND,
                f"Certificate '{cert_id}' not found",
                {"cert_id": cert_id}
            )

        cert_id, agent_id, public_key, issuer_key_id, signature, capabilities, \
            trust_level, issued_at, expires_at, status, agent_name = row

        # Check status
        if status == "revoked":
            raise TokenVerificationError(
                ErrorCode.CERTIFICATE_REVOKED,
                f"Certificate '{cert_id}' has been revoked",
                {"cert_id": cert_id}
            )

        # Check expiration
        if parse_iso(expires_at) < datetime.utcnow():
            raise TokenVerificationError(
                ErrorCode.CERTIFICATE_EXPIRED,
                f"Certificate '{cert_id}' has expired",
                {"cert_id": cert_id, "expires_at": expires_at}
            )

        # Check CRL
        result = await self.session.execute(
            text("SELECT entry_id FROM crl_entries WHERE cert_id = :cert_id"),
            {"cert_id": cert_id}
        )
        if result.fetchone():
            raise TokenVerificationError(
                ErrorCode.CERTIFICATE_REVOKED,
                f"Certificate '{cert_id}' is in the CRL",
                {"cert_id": cert_id}
            )

        # Verify CA signature
        ca_public_key = await self._get_ca_public_key(issuer_key_id)

        cert_payload = {
            "cert_id": cert_id,
            "agent_id": agent_id,
            "public_key": public_key.decode() if isinstance(public_key, bytes) else public_key,
            "capabilities": json.loads(capabilities) if capabilities else [],
            "trust_level": trust_level,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "algorithm": "ES256",
        }

        if not verify_json_signature(ca_public_key, signature, cert_payload):
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                f"Certificate '{cert_id}' signature verification failed",
                {"cert_id": cert_id, "issuer_key_id": issuer_key_id}
            )

        return {
            "cert_id": cert_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "public_key": public_key,
            "trust_level": trust_level,
            "capabilities": json.loads(capabilities) if capabilities else [],
            "issuer_key_id": issuer_key_id,
        }

    async def _get_ca_public_key(self, key_id: str) -> Any:
        """Get CA public key (cached)."""
        if key_id in self._ca_public_keys:
            return self._ca_public_keys[key_id]

        result = await self.session.execute(
            text("SELECT public_key FROM ca_root_keys WHERE key_id = :key_id"),
            {"key_id": key_id}
        )
        row = result.fetchone()

        if not row:
            raise TokenVerificationError(
                ErrorCode.INTERNAL_ERROR,
                f"CA root key '{key_id}' not found",
                {"key_id": key_id}
            )

        public_key = load_public_key_pem(row[0])
        self._ca_public_keys[key_id] = public_key
        return public_key

    async def _verify_capability_token(
        self,
        token_id: str,
        cert_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Verify a capability token."""
        result = await self.session.execute(
            text("""
                SELECT token_id, holder_agent_id, cert_id, capability, resource_scope,
                       attenuations, issued_at, expires_at, signature
                FROM capability_tokens
                WHERE token_id = :token_id
            """),
            {"token_id": token_id}
        )
        row = result.fetchone()

        if not row:
            raise TokenVerificationError(
                ErrorCode.NOT_FOUND,
                f"Capability token '{token_id}' not found",
                {"token_id": token_id}
            )

        token_id, holder_agent_id, cert_id, capability, resource_scope, \
            attenuations, issued_at, expires_at, signature = row

        # Check holder matches certificate
        if holder_agent_id != cert_info["agent_id"]:
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                f"Capability token holder '{holder_agent_id}' does not match certificate agent",
                {
                    "token_id": token_id,
                    "expected_agent": cert_info["agent_id"],
                    "actual_agent": holder_agent_id
                }
            )

        # Check expiration
        if parse_iso(expires_at) < datetime.utcnow():
            raise TokenVerificationError(
                ErrorCode.TOKEN_EXPIRED,
                f"Capability token '{token_id}' has expired",
                {"token_id": token_id, "expires_at": expires_at}
            )

        # Verify CA signature
        ca_public_key = await self._get_ca_public_key(cert_info.get("issuer_key_id", "root"))

        token_payload = {
            "token_id": token_id,
            "holder_agent_id": holder_agent_id,
            "cert_id": cert_id,
            "capability": capability,
            "resource_scope": resource_scope,
            "attenuations": json.loads(attenuations) if attenuations else {},
            "issued_at": issued_at,
            "expires_at": expires_at,
        }

        if not verify_json_signature(ca_public_key, signature, token_payload):
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                f"Capability token '{token_id}' signature verification failed",
                {"token_id": token_id}
            )

        return {
            "token_id": token_id,
            "capability": capability,
            "resource_scope": resource_scope,
            "attenuations": json.loads(attenuations) if attenuations else {},
        }

    async def _verify_delegation_token(
        self,
        delegation_id: str,
        expected_from_agent_id: str,
        expected_capability: str,
        parent_resource_scope: str,
        parent_attenuations: Dict[str, Any],
        position: int,
    ) -> Dict[str, Any]:
        """Verify a delegation token in the chain."""
        result = await self.session.execute(
            text("""
                SELECT d.delegation_id, d.from_agent_id, d.to_agent_id, d.parent_token_id,
                       d.parent_token_type, d.capability, d.resource_scope, d.attenuations,
                       d.max_depth, d.current_depth, d.issued_at, d.expires_at,
                       d.from_signature, d.status, a.name as to_agent_name
                FROM delegation_tokens d
                JOIN agents a ON d.to_agent_id = a.agent_id
                WHERE d.delegation_id = :delegation_id
            """),
            {"delegation_id": delegation_id}
        )
        row = result.fetchone()

        if not row:
            raise TokenVerificationError(
                ErrorCode.NOT_FOUND,
                f"Delegation token '{delegation_id}' not found at position {position}",
                {"delegation_id": delegation_id, "position": position}
            )

        delegation_id, from_agent_id, to_agent_id, parent_token_id, \
            parent_token_type, capability, resource_scope, attenuations, \
            max_depth, current_depth, issued_at, expires_at, \
            from_signature, status, to_agent_name = row

        # Check from_agent_id continuity
        if from_agent_id != expected_from_agent_id:
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                f"Delegation chain broken at position {position}: expected from={expected_from_agent_id}, got from={from_agent_id}",
                {
                    "position": position,
                    "expected_from": expected_from_agent_id,
                    "actual_from": from_agent_id
                }
            )

        # Check status
        if status != "active":
            raise TokenVerificationError(
                ErrorCode.TOKEN_EXPIRED,
                f"Delegation token '{delegation_id}' is not active (status: {status})",
                {"delegation_id": delegation_id, "status": status}
            )

        # Check expiration
        if parse_iso(expires_at) < datetime.utcnow():
            raise TokenVerificationError(
                ErrorCode.TOKEN_EXPIRED,
                f"Delegation token '{delegation_id}' has expired",
                {"delegation_id": delegation_id, "expires_at": expires_at}
            )

        # Check capability consistency
        if capability != expected_capability:
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                f"Capability mismatch at position {position}: expected {expected_capability}, got {capability}",
                {"position": position, "expected": expected_capability, "actual": capability}
            )

        # Check resource scope is subset
        if not self._is_scope_subset(resource_scope, parent_resource_scope):
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                f"Resource scope escalation at position {position}: {resource_scope} not in {parent_resource_scope}",
                {"position": position, "scope": resource_scope, "parent_scope": parent_resource_scope}
            )

        # Check attenuations are stricter or equal
        child_attenuations = json.loads(attenuations) if attenuations else {}
        if not is_attenuation_stricter_or_equal(child_attenuations, parent_attenuations):
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                f"Attenuation escalation at position {position}",
                {
                    "position": position,
                    "attenuations": child_attenuations,
                    "parent_attenuations": parent_attenuations
                }
            )

        # Check delegation depth
        if current_depth < 0:
            raise TokenVerificationError(
                ErrorCode.INVALID_DELEGATION_DEPTH,
                f"Negative delegation depth at position {position}",
                {"position": position, "current_depth": current_depth}
            )

        # Verify from_signature using from_agent's certificate public key
        await self._verify_delegation_signature(
            delegation_id,
            from_agent_id,
            from_signature,
            {
                "delegation_id": delegation_id,
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "parent_token_id": parent_token_id,
                "parent_token_type": parent_token_type,
                "capability": capability,
                "resource_scope": resource_scope,
                "attenuations": child_attenuations,
                "max_depth": max_depth,
                "current_depth": current_depth,
                "issued_at": issued_at,
                "expires_at": expires_at,
            },
            position,
        )

        return {
            "delegation_id": delegation_id,
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "to_agent_name": to_agent_name,
            "capability": capability,
            "resource_scope": resource_scope,
            "attenuations": child_attenuations,
        }

    async def _verify_delegation_signature(
        self,
        delegation_id: str,
        from_agent_id: str,
        from_signature: bytes,
        delegation_payload: Dict[str, Any],
        position: int,
    ) -> None:
        """
        Verify the delegation signature.

        NOTE: In production, this should verify using the delegator's public key
        (from their certificate). The delegator signs with their private key
        locally in their Wallet.

        For this Demo, delegations are signed by the CA (server-side) for simplicity.
        So we verify using the CA public key instead of the delegator's public key.
        """
        # For Demo: Use CA public key to verify (since we sign with CA key)
        # In production, this would use the delegator's certificate public key
        result = await self.session.execute(
            text("SELECT key_id FROM ca_root_keys ORDER BY created_at DESC LIMIT 1")
        )
        ca_row = result.fetchone()

        if not ca_row:
            raise TokenVerificationError(
                ErrorCode.INTERNAL_ERROR,
                "CA root key not found",
                {"position": position}
            )

        ca_key_id = ca_row[0]
        ca_public_key = await self._get_ca_public_key(ca_key_id)

        if not verify_json_signature(ca_public_key, from_signature, delegation_payload):
            raise TokenVerificationError(
                ErrorCode.DELEGATION_CHAIN_INVALID,
                f"Delegation signature verification failed at position {position}",
                {"delegation_id": delegation_id, "from_agent_id": from_agent_id, "position": position}
            )

    def _is_scope_subset(self, child_scope: str, parent_scope: str) -> bool:
        """
        Check if child_scope is a subset of parent_scope.

        Rules:
        - "*" matches everything
        - Exact match is valid
        - "db.*" matches "db.table1", "db.table2", etc.
        """
        if parent_scope == "*":
            return True
        if child_scope == parent_scope:
            return True
        # Handle wildcard patterns like "db.*"
        if parent_scope.endswith(".*"):
            prefix = parent_scope[:-2]  # Remove ".*"
            if child_scope.startswith(prefix + "."):
                return True
            if child_scope == prefix:
                return True
        return False

    def _check_permission(
        self,
        effective_capability: str,
        effective_resource_scope: str,
        effective_attenuations: Dict[str, Any],
        requested_action: str,
        requested_resource: str,
        trust_level: int,
    ) -> None:
        """Check if the effective permissions allow the requested action."""
        # Check capability matches action
        if effective_capability != requested_action:
            raise TokenVerificationError(
                ErrorCode.PERMISSION_DENIED,
                f"Capability '{effective_capability}' does not match action '{requested_action}'",
                {
                    "capability": effective_capability,
                    "action": requested_action
                }
            )

        # Check resource scope
        if not self._is_scope_subset(requested_resource, effective_resource_scope):
            raise TokenVerificationError(
                ErrorCode.PERMISSION_DENIED,
                f"Resource '{requested_resource}' is outside scope '{effective_resource_scope}'",
                {
                    "resource": requested_resource,
                    "scope": effective_resource_scope
                }
            )

        # trust_level=1 must have attenuations
        if trust_level == 1 and not effective_attenuations:
            raise TokenVerificationError(
                ErrorCode.PERMISSION_DENIED,
                "trust_level=1 agents must have attenuations",
                {"trust_level": 1, "attenuations": effective_attenuations}
            )
