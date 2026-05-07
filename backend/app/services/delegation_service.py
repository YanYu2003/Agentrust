"""
Delegation Service - Delegation token creation and management.

Implements the core logic for creating delegation tokens:
- Parent token ownership verification
- Capability subset validation
- Resource scope subset validation
- Attenuation strictness validation
- Delegation depth control
- Expiry time validation
"""

import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crypto.keys import load_public_key_pem, load_private_key_pem as load_private_key
from app.crypto.signature import sign_json
from app.crypto.canonical import canonical_json
from app.crypto.jwt import JWTUtils
from app.schemas.common import ErrorCode, VALID_CAPABILITIES
from app.utils import generate_id, now_iso, parse_iso, hours_to_iso
from app.services.attenuator import merge_and_validate_attenuations, AttenuationError

logger = logging.getLogger(__name__)


# Trust level to max delegation depth mapping
TRUST_LEVEL_MAX_DEPTH = {
    1: 0,   # trust_level=1 cannot delegate
    2: 1,
    3: 2,
    4: 5,
    5: 10,
}


class DelegationError(Exception):
    """Delegation service error."""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class DelegationService:
    """Delegation token management service."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_delegation(
        self,
        from_agent_id: str,
        to_agent_id: str,
        parent_token_id: str,
        parent_token_type: str,
        capability: str,
        resource_scope: str,
        attenuations: Optional[Dict[str, Any]] = None,
        max_depth: Optional[int] = None,
        validity_minutes: int = 60,
    ) -> Dict[str, Any]:
        """
        Create a delegation token.

        This implements the delegation logic from document section 5.2.

        Args:
            from_agent_id: The delegator (current authenticated agent)
            to_agent_id: The delegatee (who receives the delegation)
            parent_token_id: Parent token ID (capability or delegation)
            parent_token_type: "capability" or "delegation"
            capability: Capability to delegate
            resource_scope: Resource scope for the delegation
            attenuations: Attenuation parameters (must be stricter than parent)
            max_depth: Maximum delegation depth allowed
            validity_minutes: Delegation validity in minutes

        Returns:
            Dictionary with delegation token details

        Raises:
            DelegationError: If validation fails
        """
        attenuations = attenuations or {}

        # ====== Step 1: Load and validate parent token ======
        parent_info = await self._load_parent_token(
            parent_token_id,
            parent_token_type,
            from_agent_id,
        )

        # ====== Step 2: Validate delegatee ======
        to_agent = await self._validate_delegatee(to_agent_id, from_agent_id)

        # ====== Step 3: Validate capability ======
        self._validate_capability(capability, parent_info["capability"])

        # ====== Step 4: Validate resource scope ======
        self._validate_resource_scope(resource_scope, parent_info["resource_scope"])

        # ====== Step 5: Validate and merge attenuations ======
        effective_attenuations = self._validate_attenuations(
            attenuations,
            parent_info["attenuations"],
        )

        # ====== Step 6: Validate delegation depth ======
        effective_max_depth, new_current_depth = await self._validate_delegation_depth(
            from_agent_id,
            parent_token_type,
            parent_info,
            max_depth,
        )

        # ====== Step 7: Validate expiry time ======
        now = datetime.utcnow()
        requested_expiry = now + timedelta(minutes=validity_minutes)
        effective_expiry = self._validate_expiry(
            requested_expiry,
            parent_info["expires_at"],
        )

        # ====== Step 8: Create delegation token ======
        delegation_id = generate_id("del")
        issued_at = now_iso()
        expires_at = effective_expiry.isoformat() + "Z"

        # Build delegation payload for signing
        delegation_payload = {
            "delegation_id": delegation_id,
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "parent_token_id": parent_token_id,
            "parent_token_type": parent_token_type,
            "capability": capability,
            "resource_scope": resource_scope,
            "attenuations": effective_attenuations,
            "max_depth": effective_max_depth,
            "current_depth": new_current_depth,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }

        # Sign the delegation
        # NOTE: In production, this signature should be created by the delegator's
        # local Wallet (private key never leaves the agent). For this demo,
        # we sign on the server side for simplicity.
        from_signature = await self._sign_delegation(from_agent_id, delegation_payload)

        # Store delegation token
        await self.session.execute(
            text("""
                INSERT INTO delegation_tokens
                (delegation_id, from_agent_id, to_agent_id, parent_token_id, parent_token_type,
                 capability, resource_scope, attenuations, max_depth, current_depth,
                 issued_at, expires_at, from_signature, status)
                VALUES
                (:delegation_id, :from_agent_id, :to_agent_id, :parent_token_id, :parent_token_type,
                 :capability, :resource_scope, :attenuations, :max_depth, :current_depth,
                 :issued_at, :expires_at, :from_signature, 'active')
            """),
            {
                "delegation_id": delegation_id,
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "parent_token_id": parent_token_id,
                "parent_token_type": parent_token_type,
                "capability": capability,
                "resource_scope": resource_scope,
                "attenuations": json.dumps(effective_attenuations),
                "max_depth": effective_max_depth,
                "current_depth": new_current_depth,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "from_signature": from_signature,
            }
        )

        await self.session.commit()

        logger.info(f"Created delegation {delegation_id}: {from_agent_id} -> {to_agent_id}")

        return {
            "delegation_token": {
                "delegation_id": delegation_id,
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "capability": capability,
                "resource_scope": resource_scope,
                "attenuations": effective_attenuations,
                "max_depth": effective_max_depth,
                "current_depth": new_current_depth,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "from_signature": base64.b64encode(from_signature).decode(),
                "status": "active",
            }
        }

    async def _load_parent_token(
        self,
        parent_token_id: str,
        parent_token_type: str,
        from_agent_id: str,
    ) -> Dict[str, Any]:
        """Load and validate parent token."""
        if parent_token_type == "capability":
            result = await self.session.execute(
                text("""
                    SELECT token_id, holder_agent_id, capability, resource_scope,
                           attenuations, expires_at, signature
                    FROM capability_tokens
                    WHERE token_id = :token_id
                """),
                {"token_id": parent_token_id}
            )
            row = result.fetchone()

            if not row:
                raise DelegationError(
                    ErrorCode.NOT_FOUND,
                    f"Capability token '{parent_token_id}' not found",
                    {"parent_token_id": parent_token_id}
                )

            token_id, holder_agent_id, capability, resource_scope, \
                attenuations, expires_at, signature = row

            # Verify ownership
            if holder_agent_id != from_agent_id:
                raise DelegationError(
                    ErrorCode.PERMISSION_DENIED,
                    f"Capability token '{parent_token_id}' does not belong to agent '{from_agent_id}'",
                    {
                        "parent_token_id": parent_token_id,
                        "expected_holder": from_agent_id,
                        "actual_holder": holder_agent_id
                    }
                )

        elif parent_token_type == "delegation":
            result = await self.session.execute(
                text("""
                    SELECT delegation_id, to_agent_id, capability, resource_scope,
                           attenuations, expires_at, current_depth, max_depth, from_signature
                    FROM delegation_tokens
                    WHERE delegation_id = :delegation_id
                """),
                {"delegation_id": parent_token_id}
            )
            row = result.fetchone()

            if not row:
                raise DelegationError(
                    ErrorCode.NOT_FOUND,
                    f"Delegation token '{parent_token_id}' not found",
                    {"parent_token_id": parent_token_id}
                )

            delegation_id, to_agent_id, capability, resource_scope, \
                attenuations, expires_at, current_depth, max_depth, from_signature = row

            # Verify ownership (must be the to_agent_id for delegations)
            if to_agent_id != from_agent_id:
                raise DelegationError(
                    ErrorCode.PERMISSION_DENIED,
                    f"Delegation token '{parent_token_id}' was not granted to agent '{from_agent_id}'",
                    {
                        "parent_token_id": parent_token_id,
                        "expected_holder": from_agent_id,
                        "actual_holder": to_agent_id
                    }
                )

            # Check if delegation is active
            if parse_iso(expires_at) < datetime.utcnow():
                raise DelegationError(
                    ErrorCode.TOKEN_EXPIRED,
                    f"Parent delegation token '{parent_token_id}' has expired",
                    {"parent_token_id": parent_token_id, "expires_at": expires_at}
                )

            # Return with depth info
            return {
                "token_id": delegation_id,
                "capability": capability,
                "resource_scope": resource_scope,
                "attenuations": json.loads(attenuations) if attenuations else {},
                "expires_at": expires_at,
                "current_depth": current_depth,
                "max_depth": max_depth,
            }
        else:
            raise DelegationError(
                ErrorCode.INVALID_REQUEST,
                f"Invalid parent_token_type: {parent_token_type}",
                {"parent_token_type": parent_token_type}
            )

        # Check if capability token is expired
        if parse_iso(expires_at) < datetime.utcnow():
            raise DelegationError(
                ErrorCode.TOKEN_EXPIRED,
                f"Parent capability token '{parent_token_id}' has expired",
                {"parent_token_id": parent_token_id, "expires_at": expires_at}
            )

        return {
            "token_id": token_id,
            "capability": capability,
            "resource_scope": resource_scope,
            "attenuations": json.loads(attenuations) if attenuations else {},
            "expires_at": expires_at,
        }

    async def _validate_delegatee(
        self,
        to_agent_id: str,
        from_agent_id: str,
    ) -> Dict[str, Any]:
        """Validate the delegatee agent."""
        if to_agent_id == from_agent_id:
            raise DelegationError(
                ErrorCode.INVALID_REQUEST,
                "Cannot delegate to self",
                {"to_agent_id": to_agent_id}
            )

        result = await self.session.execute(
            text("SELECT agent_id, name, status, trust_level FROM agents WHERE agent_id = :agent_id"),
            {"agent_id": to_agent_id}
        )
        row = result.fetchone()

        if not row:
            raise DelegationError(
                ErrorCode.NOT_FOUND,
                f"Target agent '{to_agent_id}' not found",
                {"to_agent_id": to_agent_id}
            )

        agent_id, name, status, trust_level = row

        if status != "active":
            raise DelegationError(
                ErrorCode.AGENT_SUSPENDED,
                f"Target agent '{to_agent_id}' is not active (status: {status})",
                {"to_agent_id": to_agent_id, "status": status}
            )

        return {
            "agent_id": agent_id,
            "name": name,
            "trust_level": trust_level,
        }

    def _validate_capability(
        self,
        capability: str,
        parent_capability: str,
    ) -> None:
        """Validate that capability matches parent."""
        if capability != parent_capability:
            raise DelegationError(
                ErrorCode.INVALID_CAPABILITY,
                f"Delegated capability '{capability}' must match parent capability '{parent_capability}'",
                {
                    "capability": capability,
                    "parent_capability": parent_capability
                }
            )

        if capability not in VALID_CAPABILITIES:
            raise DelegationError(
                ErrorCode.INVALID_CAPABILITY,
                f"Invalid capability: {capability}",
                {"capability": capability}
            )

    def _validate_resource_scope(
        self,
        resource_scope: str,
        parent_scope: str,
    ) -> None:
        """Validate that resource scope is a subset of parent."""
        if not self._is_scope_subset(resource_scope, parent_scope):
            raise DelegationError(
                ErrorCode.INVALID_ATTENUATIONS,
                f"Resource scope '{resource_scope}' must be a subset of parent scope '{parent_scope}'",
                {
                    "resource_scope": resource_scope,
                    "parent_scope": parent_scope
                }
            )

    def _is_scope_subset(self, child_scope: str, parent_scope: str) -> bool:
        """Check if child_scope is a subset of parent_scope."""
        if parent_scope == "*":
            return True
        if child_scope == parent_scope:
            return True
        if parent_scope.endswith(".*"):
            prefix = parent_scope[:-2]
            if child_scope.startswith(prefix + "."):
                return True
            if child_scope == prefix:
                return True
        return False

    def _validate_attenuations(
        self,
        child_attenuations: Dict[str, Any],
        parent_attenuations: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate and merge attenuations."""
        try:
            return merge_and_validate_attenuations(parent_attenuations, child_attenuations)
        except AttenuationError as e:
            raise DelegationError(
                ErrorCode.INVALID_ATTENUATIONS,
                f"Attenuation validation failed: {e.message}",
                {"attenuations": child_attenuations, "parent_attenuations": parent_attenuations}
            )

    async def _validate_delegation_depth(
        self,
        from_agent_id: str,
        parent_token_type: str,
        parent_info: Dict[str, Any],
        requested_max_depth: Optional[int],
    ) -> tuple[int, int]:
        """
        Validate delegation depth and return (max_depth, current_depth).

        Rules:
        - For capability parent: use requested max_depth, validate against trust_level
        - For delegation parent: inherit from parent, decrement current_depth
        """
        # Get delegator's trust level
        result = await self.session.execute(
            text("SELECT trust_level FROM agents WHERE agent_id = :agent_id"),
            {"agent_id": from_agent_id}
        )
        row = result.fetchone()
        trust_level = row[0] if row else 1

        # Check trust_level constraint
        max_allowed_depth = TRUST_LEVEL_MAX_DEPTH.get(trust_level, 0)

        if parent_token_type == "capability":
            # First delegation from capability token
            if requested_max_depth is None:
                requested_max_depth = max_allowed_depth

            if requested_max_depth > max_allowed_depth:
                raise DelegationError(
                    ErrorCode.INVALID_DELEGATION_DEPTH,
                    f"Requested max_depth {requested_max_depth} exceeds trust_level {trust_level} limit of {max_allowed_depth}",
                    {
                        "requested_max_depth": requested_max_depth,
                        "max_allowed_depth": max_allowed_depth,
                        "trust_level": trust_level
                    }
                )

            if requested_max_depth < 0:
                raise DelegationError(
                    ErrorCode.INVALID_DELEGATION_DEPTH,
                    f"max_depth cannot be negative: {requested_max_depth}",
                    {"max_depth": requested_max_depth}
                )

            # current_depth = max_depth - 1 for the delegatee
            # But if max_depth=0, the delegatee gets 0 (no further delegation)
            new_current_depth = requested_max_depth - 1 if requested_max_depth > 0 else 0

        else:
            # Delegation from another delegation token
            parent_current_depth = parent_info.get("current_depth", 0)
            parent_max_depth = parent_info.get("max_depth", 1)

            if parent_current_depth <= 0:
                raise DelegationError(
                    ErrorCode.INVALID_DELEGATION_DEPTH,
                    f"Parent delegation has no remaining depth (current_depth={parent_current_depth})",
                    {"parent_current_depth": parent_current_depth}
                )

            # Use parent's max_depth, decrement current_depth
            requested_max_depth = parent_max_depth
            new_current_depth = parent_current_depth - 1 if parent_current_depth > 0 else 0

        return requested_max_depth, new_current_depth

    def _validate_expiry(
        self,
        requested_expiry: datetime,
        parent_expires_at: str,
    ) -> datetime:
        """Validate that delegation expiry doesn't exceed parent."""
        parent_expiry = parse_iso(parent_expires_at)

        if requested_expiry > parent_expiry:
            raise DelegationError(
                ErrorCode.DELEGATION_EXPIRY_EXCEEDS_PARENT,
                f"Delegation expiry {requested_expiry.isoformat()}Z exceeds parent expiry {parent_expires_at}",
                {
                    "requested_expiry": requested_expiry.isoformat() + "Z",
                    "parent_expiry": parent_expires_at
                }
            )

        return requested_expiry

    async def _sign_delegation(
        self,
        from_agent_id: str,
        delegation_payload: Dict[str, Any],
    ) -> bytes:
        """
        Sign the delegation payload.

        NOTE: In production, this should be done by the delegator's local Wallet.
        The private key should never leave the agent's runtime.
        For this demo, we sign on the server side.

        We use the delegator's certificate public key to verify later,
        so we need to sign with the corresponding private key.
        Since we don't have access to the agent's private key in this demo,
        we'll use a server-side key for signing and note this in documentation.
        """
        # Get the delegator's certificate to find their public key
        result = await self.session.execute(
            text("""
                SELECT public_key FROM certificates
                WHERE agent_id = :agent_id AND status = 'valid' AND expires_at > datetime('now')
                ORDER BY issued_at DESC LIMIT 1
            """),
            {"agent_id": from_agent_id}
        )
        row = result.fetchone()

        if not row:
            raise DelegationError(
                ErrorCode.INTERNAL_ERROR,
                f"No valid certificate found for delegator '{from_agent_id}'",
                {"from_agent_id": from_agent_id}
            )

        # For demo purposes, we sign with CA key
        # In production, this would be signed with the agent's private key
        result = await self.session.execute(
            text("SELECT encrypted_private_key FROM ca_root_keys ORDER BY created_at DESC LIMIT 1")
        )
        ca_row = result.fetchone()

        if not ca_row:
            raise DelegationError(
                ErrorCode.INTERNAL_ERROR,
                "CA root key not found",
                {}
            )

        from app.crypto.keys import load_ca_private_key
        ca_private_key = load_ca_private_key(ca_row[0])

        # Sign the delegation payload
        signature = sign_json(ca_private_key, delegation_payload)

        return signature

    async def get_agent_tokens(
        self,
        agent_id: str,
        requesting_agent_id: str,
        has_manage_agents: bool = False,
    ) -> Dict[str, Any]:
        """
        Get all tokens for an agent.

        Args:
            agent_id: Agent to query
            requesting_agent_id: The agent making the request
            has_manage_agents: Whether requesting agent has manage_agents capability

        Returns:
            Dictionary with capability_tokens, delegation_tokens_received, delegation_tokens_issued
        """
        # Authorization check
        if agent_id != requesting_agent_id and not has_manage_agents:
            raise DelegationError(
                ErrorCode.PERMISSION_DENIED,
                "Can only query your own tokens, or need manage_agents capability",
                {"requested_agent_id": agent_id}
            )

        # Get capability tokens
        result = await self.session.execute(
            text("""
                SELECT token_id, capability, resource_scope, attenuations, expires_at
                FROM capability_tokens
                WHERE holder_agent_id = :agent_id AND expires_at > datetime('now')
            """),
            {"agent_id": agent_id}
        )
        cap_rows = result.fetchall()

        capability_tokens = [
            {
                "token_id": row[0],
                "capability": row[1],
                "resource_scope": row[2],
                "attenuations": json.loads(row[3]) if row[3] else {},
                "expires_at": row[4],
                "status": "active",
            }
            for row in cap_rows
        ]

        # Get delegation tokens received (to_agent_id)
        result = await self.session.execute(
            text("""
                SELECT delegation_id, from_agent_id, capability, attenuations,
                       current_depth, expires_at, status
                FROM delegation_tokens
                WHERE to_agent_id = :agent_id
            """),
            {"agent_id": agent_id}
        )
        del_received_rows = result.fetchall()

        delegation_tokens_received = [
            {
                "delegation_id": row[0],
                "from_agent_id": row[1],
                "capability": row[2],
                "attenuations": json.loads(row[3]) if row[3] else {},
                "current_depth": row[4],
                "expires_at": row[5],
                "status": row[6],
            }
            for row in del_received_rows
        ]

        # Get delegation tokens issued (from_agent_id)
        result = await self.session.execute(
            text("""
                SELECT delegation_id, to_agent_id, capability, attenuations,
                       current_depth, expires_at, status
                FROM delegation_tokens
                WHERE from_agent_id = :agent_id
            """),
            {"agent_id": agent_id}
        )
        del_issued_rows = result.fetchall()

        delegation_tokens_issued = [
            {
                "delegation_id": row[0],
                "to_agent_id": row[1],
                "capability": row[2],
                "attenuations": json.loads(row[3]) if row[3] else {},
                "current_depth": row[4],
                "expires_at": row[5],
                "status": row[6],
            }
            for row in del_issued_rows
        ]

        return {
            "agent_id": agent_id,
            "capability_tokens": capability_tokens,
            "delegation_tokens_received": delegation_tokens_received,
            "delegation_tokens_issued": delegation_tokens_issued,
        }
