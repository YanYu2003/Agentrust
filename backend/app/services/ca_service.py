"""
CA Service - Certificate Authority business logic.

Handles agent registration, certificate issuance, and revocation.
"""

import base64
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crypto.keys import (
    generate_ecdsa_keypair,
    load_ca_private_key,
    load_public_key_pem,
    public_key_to_pem,
)
from app.crypto.signature import sign_json
from app.crypto.canonical import canonical_json
from app.utils import generate_id, now_iso, hours_to_iso, parse_iso
from app.schemas.common import VALID_CAPABILITIES, ErrorCode

logger = logging.getLogger(__name__)


class CAServiceError(Exception):
    """CA Service error."""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class CAService:
    """Certificate Authority service."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_ca_key(self) -> Tuple[str, bytes, Any]:
        """
        Load CA root key from database.

        Returns:
            Tuple of (key_id, public_key_pem, private_key)
        """
        result = await self.session.execute(
            text("SELECT key_id, public_key, encrypted_private_key FROM ca_root_keys ORDER BY created_at DESC LIMIT 1")
        )
        row = result.fetchone()

        if not row:
            raise CAServiceError(ErrorCode.INTERNAL_ERROR, "CA root key not found")

        key_id, public_key_blob, encrypted_private_key = row

        # Load private key
        private_key = load_ca_private_key(encrypted_private_key)

        return key_id, public_key_blob, private_key

    async def register_agent(
        self,
        name: str,
        public_key_pem: str,
        owner: str,
        requested_capabilities: List[str],
        description: str = "",
        trust_level: int = 1,
        cert_validity_hours: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Register a new agent and issue certificate.

        Args:
            name: Agent unique name
            public_key_pem: PEM-encoded public key
            owner: Agent owner identifier
            requested_capabilities: List of requested capabilities
            description: Agent description
            trust_level: Trust level (1-5)
            cert_validity_hours: Optional certificate validity override

        Returns:
            Dictionary with agent_id, certificate, and capability_tokens
        """
        # Validate capabilities
        invalid = [cap for cap in requested_capabilities if cap not in VALID_CAPABILITIES]
        if invalid:
            raise CAServiceError(
                ErrorCode.INVALID_CAPABILITY,
                f"Invalid capabilities: {invalid}",
                {"invalid_capabilities": invalid}
            )

        # Check if name already exists
        result = await self.session.execute(
            text("SELECT agent_id FROM agents WHERE name = :name"),
            {"name": name}
        )
        if result.fetchone():
            raise CAServiceError(
                ErrorCode.CONFLICT,
                f"Agent name '{name}' already exists",
                {"name": name}
            )

        # Validate public key format
        try:
            agent_public_key = load_public_key_pem(public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem)
        except Exception as e:
            raise CAServiceError(
                ErrorCode.INVALID_REQUEST,
                f"Invalid public key format: {str(e)}",
                {"field": "public_key"}
            )

        # Calculate certificate validity based on trust_level
        default_hours = settings.trust_level_default_hours.get(trust_level, 24)
        if cert_validity_hours is not None:
            if cert_validity_hours > default_hours:
                raise CAServiceError(
                    ErrorCode.INVALID_REQUEST,
                    f"cert_validity_hours ({cert_validity_hours}) exceeds trust_level default ({default_hours})",
                    {"max_allowed_hours": default_hours}
                )
            effective_hours = cert_validity_hours
        else:
            effective_hours = default_hours

        # Get CA key
        ca_key_id, ca_public_key_pem, ca_private_key = await self.get_ca_key()

        # Generate IDs
        agent_id = generate_id("agent")
        cert_id = generate_id("cert")

        # Timestamps
        now = now_iso()
        expires_at = hours_to_iso(effective_hours)

        # Create agent record
        await self.session.execute(
            text("""
                INSERT INTO agents (agent_id, name, description, owner, trust_level, status, registered_at)
                VALUES (:agent_id, :name, :description, :owner, :trust_level, 'active', :registered_at)
            """),
            {
                "agent_id": agent_id,
                "name": name,
                "description": description,
                "owner": owner,
                "trust_level": trust_level,
                "registered_at": now,
            }
        )

        # Build certificate payload for signing
        cert_payload = {
            "cert_id": cert_id,
            "agent_id": agent_id,
            "public_key": public_key_pem,
            "capabilities": requested_capabilities,
            "trust_level": trust_level,
            "issued_at": now,
            "expires_at": expires_at,
            "algorithm": "ES256",
        }

        # Sign certificate with CA private key
        cert_signature = sign_json(ca_private_key, cert_payload)

        # Store certificate
        await self.session.execute(
            text("""
                INSERT INTO certificates
                (cert_id, agent_id, public_key, issuer_key_id, signature, algorithm, capabilities, trust_level, issued_at, expires_at, status)
                VALUES (:cert_id, :agent_id, :public_key, :issuer_key_id, :signature, :algorithm, :capabilities, :trust_level, :issued_at, :expires_at, 'valid')
            """),
            {
                "cert_id": cert_id,
                "agent_id": agent_id,
                "public_key": public_key_pem.encode() if isinstance(public_key_pem, str) else public_key_pem,
                "issuer_key_id": ca_key_id,
                "signature": cert_signature,
                "algorithm": "ES256",
                "capabilities": json.dumps(requested_capabilities),
                "trust_level": trust_level,
                "issued_at": now,
                "expires_at": expires_at,
            }
        )

        # Issue capability tokens
        capability_tokens = []
        for capability in requested_capabilities:
            token_id = generate_id("cap")

            token_payload = {
                "token_id": token_id,
                "holder_agent_id": agent_id,
                "cert_id": cert_id,
                "capability": capability,
                "resource_scope": "*",
                "attenuations": {},
                "issued_at": now,
                "expires_at": expires_at,
            }

            # Sign capability token with CA private key
            token_signature = sign_json(ca_private_key, token_payload)

            # Store capability token
            await self.session.execute(
                text("""
                    INSERT INTO capability_tokens
                    (token_id, holder_agent_id, cert_id, capability, resource_scope, attenuations, issued_at, expires_at, signature)
                    VALUES (:token_id, :holder_agent_id, :cert_id, :capability, :resource_scope, :attenuations, :issued_at, :expires_at, :signature)
                """),
                {
                    "token_id": token_id,
                    "holder_agent_id": agent_id,
                    "cert_id": cert_id,
                    "capability": capability,
                    "resource_scope": "*",
                    "attenuations": "{}",
                    "issued_at": now,
                    "expires_at": expires_at,
                    "signature": token_signature,
                }
            )

            capability_tokens.append({
                "token_id": token_id,
                "capability": capability,
                "resource_scope": "*",
                "attenuations": {},
                "expires_at": expires_at,
            })

        await self.session.commit()

        logger.info(f"Registered agent {agent_id} with certificate {cert_id}")

        return {
            "agent_id": agent_id,
            "certificate": {
                "cert_id": cert_id,
                "public_key": public_key_pem,
                "issuer_key_id": ca_key_id,
                "capabilities": requested_capabilities,
                "trust_level": trust_level,
                "algorithm": "ES256",
                "issued_at": now,
                "expires_at": expires_at,
                "signature": base64.b64encode(cert_signature).decode(),
            },
            "capability_tokens": capability_tokens,
        }

    async def create_challenge(self, agent_id: str, cert_id: str) -> Dict[str, Any]:
        """
        Create a challenge for authentication.

        Args:
            agent_id: Agent ID
            cert_id: Certificate ID

        Returns:
            Dictionary with challenge_id, nonce, and expires_at
        """
        # Verify agent exists and is active
        result = await self.session.execute(
            text("SELECT status FROM agents WHERE agent_id = :agent_id"),
            {"agent_id": agent_id}
        )
        row = result.fetchone()
        if not row:
            raise CAServiceError(ErrorCode.NOT_FOUND, f"Agent '{agent_id}' not found")
        if row[0] != "active":
            raise CAServiceError(ErrorCode.AGENT_SUSPENDED, f"Agent '{agent_id}' is {row[0]}")

        # Verify certificate exists, belongs to agent, and is valid
        result = await self.session.execute(
            text("SELECT status, expires_at FROM certificates WHERE cert_id = :cert_id AND agent_id = :agent_id"),
            {"cert_id": cert_id, "agent_id": agent_id}
        )
        row = result.fetchone()
        if not row:
            raise CAServiceError(ErrorCode.NOT_FOUND, f"Certificate '{cert_id}' not found for agent '{agent_id}'")

        cert_status, expires_at = row
        if cert_status == "revoked":
            raise CAServiceError(ErrorCode.CERTIFICATE_REVOKED, f"Certificate '{cert_id}' has been revoked")
        if cert_status == "expired" or parse_iso(expires_at) < datetime.utcnow():
            raise CAServiceError(ErrorCode.CERTIFICATE_EXPIRED, f"Certificate '{cert_id}' has expired")

        # Generate challenge
        challenge_id = generate_id("chal")
        nonce = secrets.token_urlsafe(32)
        now = now_iso()
        expires = hours_to_iso(1)  # Challenge expires in 1 hour (actually 1 minute in real use)

        # Store challenge
        await self.session.execute(
            text("""
                INSERT INTO challenges (challenge_id, agent_id, cert_id, nonce, status, created_at, expires_at)
                VALUES (:challenge_id, :agent_id, :cert_id, :nonce, 'pending', :created_at, :expires_at)
            """),
            {
                "challenge_id": challenge_id,
                "agent_id": agent_id,
                "cert_id": cert_id,
                "nonce": nonce,
                "created_at": now,
                "expires_at": expires,
            }
        )

        await self.session.commit()

        return {
            "challenge_id": challenge_id,
            "nonce": nonce,
            "expires_at": expires,
        }

    async def verify_challenge(
        self,
        challenge_id: str,
        agent_id: str,
        signed_nonce: str,
    ) -> Dict[str, Any]:
        """
        Verify challenge signature and issue session token.

        Args:
            challenge_id: Challenge ID
            agent_id: Agent ID
            signed_nonce: Base64-encoded signature of nonce

        Returns:
            Dictionary with session_token, expires_at, agent_id
        """
        # Load challenge
        result = await self.session.execute(
            text("SELECT cert_id, nonce, status, expires_at FROM challenges WHERE challenge_id = :challenge_id AND agent_id = :agent_id"),
            {"challenge_id": challenge_id, "agent_id": agent_id}
        )
        row = result.fetchone()

        if not row:
            raise CAServiceError(ErrorCode.AUTH_INVALID_SIGNATURE, "Challenge not found or does not belong to agent")

        cert_id, nonce, status, expires_at = row

        # Check challenge status
        if status == "used":
            raise CAServiceError(ErrorCode.AUTH_INVALID_SIGNATURE, "Challenge already used")
        if status == "expired" or parse_iso(expires_at) < datetime.utcnow():
            raise CAServiceError(ErrorCode.AUTH_EXPIRED, "Challenge has expired")

        # Load certificate public key
        result = await self.session.execute(
            text("SELECT public_key FROM certificates WHERE cert_id = :cert_id"),
            {"cert_id": cert_id}
        )
        row = result.fetchone()
        if not row:
            raise CAServiceError(ErrorCode.NOT_FOUND, "Certificate not found")

        public_key_pem = row[0]
        public_key = load_public_key_pem(public_key_pem if isinstance(public_key_pem, bytes) else public_key_pem.encode())

        # Verify signature
        try:
            signature_bytes = base64.b64decode(signed_nonce)
        except Exception:
            raise CAServiceError(ErrorCode.AUTH_INVALID_SIGNATURE, "Invalid signature format")

        # Verify the signature
        from app.crypto.signature import verify_signature
        if not verify_signature(public_key, signature_bytes, nonce.encode()):
            raise CAServiceError(ErrorCode.AUTH_INVALID_SIGNATURE, "Signature verification failed")

        # Mark challenge as used
        await self.session.execute(
            text("UPDATE challenges SET status = 'used' WHERE challenge_id = :challenge_id"),
            {"challenge_id": challenge_id}
        )

        # Get agent trust level
        result = await self.session.execute(
            text("SELECT trust_level FROM agents WHERE agent_id = :agent_id"),
            {"agent_id": agent_id}
        )
        row = result.fetchone()
        trust_level = row[0] if row else 1

        # Generate session token
        from app.services.auth_service import AuthService
        auth_service = AuthService(self.session)

        session_token = await auth_service.create_session_token(
            agent_id=agent_id,
            cert_id=cert_id,
            challenge_id=challenge_id,
            trust_level=trust_level,
        )

        await self.session.commit()

        return {
            "session_token": session_token["token"],
            "expires_at": session_token["expires_at"],
            "agent_id": agent_id,
        }

    async def revoke_certificate(
        self,
        cert_id: str,
        reason: str,
        revoked_by: str,
    ) -> Dict[str, Any]:
        """
        Revoke a certificate.

        Args:
            cert_id: Certificate ID to revoke
            reason: Reason for revocation
            revoked_by: Who initiated the revocation

        Returns:
            Dictionary with cert_id, status, revoked_at
        """
        # Check if certificate exists
        result = await self.session.execute(
            text("SELECT cert_id, status FROM certificates WHERE cert_id = :cert_id"),
            {"cert_id": cert_id}
        )
        row = result.fetchone()

        if not row:
            raise CAServiceError(ErrorCode.NOT_FOUND, f"Certificate '{cert_id}' not found")

        if row[1] == "revoked":
            raise CAServiceError(ErrorCode.CONFLICT, f"Certificate '{cert_id}' is already revoked")

        # Update certificate status
        now = now_iso()
        await self.session.execute(
            text("UPDATE certificates SET status = 'revoked' WHERE cert_id = :cert_id"),
            {"cert_id": cert_id}
        )

        # Add to CRL
        entry_id = generate_id("entry")
        await self.session.execute(
            text("""
                INSERT INTO crl_entries (entry_id, cert_id, reason, revoked_at, revoked_by)
                VALUES (:entry_id, :cert_id, :reason, :revoked_at, :revoked_by)
            """),
            {
                "entry_id": entry_id,
                "cert_id": cert_id,
                "reason": reason,
                "revoked_at": now,
                "revoked_by": revoked_by,
            }
        )

        await self.session.commit()

        logger.info(f"Certificate {cert_id} revoked by {revoked_by}: {reason}")

        return {
            "cert_id": cert_id,
            "status": "revoked",
            "revoked_at": now,
        }

    async def get_crl(self) -> Dict[str, Any]:
        """
        Get Certificate Revocation List.

        Returns:
            Dictionary with crl_version, updated_at, entries
        """
        result = await self.session.execute(
            text("""
                SELECT cert_id, revoked_at, reason
                FROM crl_entries
                ORDER BY revoked_at DESC
            """)
        )
        rows = result.fetchall()

        entries = [
            {
                "cert_id": row[0],
                "revoked_at": row[1],
                "reason": row[2],
            }
            for row in rows
        ]

        # Calculate version based on number of entries
        result = await self.session.execute(
            text("SELECT COUNT(*) FROM crl_entries")
        )
        count = result.fetchone()[0]

        return {
            "crl_version": count,
            "updated_at": now_iso(),
            "entries": entries,
        }

    async def get_agent_info(self, agent_id: str) -> Dict[str, Any]:
        """
        Get agent information.

        Args:
            agent_id: Agent ID

        Returns:
            Dictionary with agent info
        """
        result = await self.session.execute(
            text("SELECT agent_id, name, description, owner, trust_level, status, registered_at FROM agents WHERE agent_id = :agent_id"),
            {"agent_id": agent_id}
        )
        row = result.fetchone()

        if not row:
            raise CAServiceError(ErrorCode.NOT_FOUND, f"Agent '{agent_id}' not found")

        # Get certificates
        result = await self.session.execute(
            text("SELECT cert_id, status, capabilities, expires_at FROM certificates WHERE agent_id = :agent_id"),
            {"agent_id": agent_id}
        )
        cert_rows = result.fetchall()

        certificates = [
            {
                "cert_id": row[0],
                "status": row[1],
                "capabilities": json.loads(row[2]) if row[2] else [],
                "expires_at": row[3],
            }
            for row in cert_rows
        ]

        # Count active tokens
        result = await self.session.execute(
            text("SELECT COUNT(*) FROM capability_tokens WHERE holder_agent_id = :agent_id AND expires_at > datetime('now')"),
            {"agent_id": agent_id}
        )
        active_tokens = result.fetchone()[0]

        result = await self.session.execute(
            text("SELECT COUNT(*) FROM delegation_tokens WHERE from_agent_id = :agent_id AND status = 'active' AND expires_at > datetime('now')"),
            {"agent_id": agent_id}
        )
        delegations_from = result.fetchone()[0]

        result = await self.session.execute(
            text("SELECT COUNT(*) FROM delegation_tokens WHERE to_agent_id = :agent_id AND status = 'active' AND expires_at > datetime('now')"),
            {"agent_id": agent_id}
        )
        delegations_to = result.fetchone()[0]

        return {
            "agent_id": row[0],
            "name": row[1],
            "description": row[2] or "",
            "owner": row[3],
            "trust_level": row[4],
            "status": row[5],
            "registered_at": row[6],
            "certificates": certificates,
            "active_capability_tokens": active_tokens,
            "active_delegations_from": delegations_from,
            "active_delegations_to": delegations_to,
        }
