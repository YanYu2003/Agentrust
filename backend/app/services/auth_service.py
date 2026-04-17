"""
Authentication Service - Session token management.

Handles session token creation, validation, and HMAC signing.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.utils import generate_id, now_iso, parse_iso
from app.schemas.common import ErrorCode, SessionInfo

logger = logging.getLogger(__name__)


class AuthServiceError(Exception):
    """Auth Service error."""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AuthService:
    """Authentication service for session token management."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.session_secret = settings.session_secret.encode() if isinstance(settings.session_secret, str) else settings.session_secret

    async def create_session_token(
        self,
        agent_id: str,
        cert_id: str,
        challenge_id: str,
        trust_level: int,
    ) -> Dict[str, Any]:
        """
        Create a session token.

        Args:
            agent_id: Agent ID
            cert_id: Certificate ID used for authentication
            challenge_id: Challenge ID that was verified
            trust_level: Agent's trust level

        Returns:
            Dictionary with token and expires_at
        """
        session_id = generate_id("sess")
        now = datetime.utcnow()
        issued_at = now.isoformat() + "Z"
        expires_at = (now + timedelta(minutes=settings.session_token_expire_minutes)).isoformat() + "Z"

        # Build payload
        payload = {
            "session_id": session_id,
            "agent_id": agent_id,
            "cert_id": cert_id,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "challenge_id": challenge_id,
            "trust_level": trust_level,
        }

        # Create token
        token = self._sign_token(payload)

        # Store session in database
        await self.session.execute(
            text("""
                INSERT INTO session_tokens (session_id, agent_id, cert_id, challenge_id, trust_level, issued_at, expires_at, status)
                VALUES (:session_id, :agent_id, :cert_id, :challenge_id, :trust_level, :issued_at, :expires_at, 'active')
            """),
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "cert_id": cert_id,
                "challenge_id": challenge_id,
                "trust_level": trust_level,
                "issued_at": issued_at,
                "expires_at": expires_at,
            }
        )

        return {
            "token": token,
            "session_id": session_id,
            "expires_at": expires_at,
        }

    def _sign_token(self, payload: Dict[str, Any]) -> str:
        """
        Sign a payload with HMAC-SHA256.

        Args:
            payload: Token payload

        Returns:
            Signed token string (header.payload.signature)
        """
        # Header
        header = {"alg": "HS256", "typ": "session"}
        header_b64 = base64.urlsafe_b64encode(
            json.dumps(header, separators=(",", ":")).encode()
        ).decode().rstrip("=")

        # Payload
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).decode().rstrip("=")

        # Signature
        signing_input = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            self.session_secret,
            signing_input.encode(),
            hashlib.sha256
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def verify_token(self, token: str) -> SessionInfo:
        """
        Verify a session token.

        Args:
            token: Session token string

        Returns:
            SessionInfo if valid

        Raises:
            AuthServiceError if invalid
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthServiceError(ErrorCode.AUTH_REQUIRED, "Invalid session token format")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            self.session_secret,
            signing_input.encode(),
            hashlib.sha256
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

        # Constant-time comparison
        if not hmac.compare_digest(signature_b64, expected_sig_b64):
            raise AuthServiceError(ErrorCode.AUTH_REQUIRED, "Session token signature invalid")

        # Decode payload
        try:
            # Add padding if needed
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload_json = base64.urlsafe_b64decode(payload_b64).decode()
            payload = json.loads(payload_json)
        except Exception as e:
            raise AuthServiceError(ErrorCode.AUTH_REQUIRED, f"Invalid session token payload: {e}")

        # Check expiration
        expires_at = payload.get("expires_at")
        if expires_at:
            if parse_iso(expires_at) < datetime.utcnow():
                raise AuthServiceError(ErrorCode.AUTH_EXPIRED, "Session token expired")

        return SessionInfo(
            session_id=payload["session_id"],
            agent_id=payload["agent_id"],
            cert_id=payload["cert_id"],
            issued_at=payload["issued_at"],
            expires_at=payload["expires_at"],
            challenge_id=payload["challenge_id"],
            trust_level=payload["trust_level"],
        )

    async def validate_session(self, token: str) -> SessionInfo:
        """
        Validate a session token including database checks.

        Args:
            token: Session token string

        Returns:
            SessionInfo if valid

        Raises:
            AuthServiceError if invalid
        """
        # First verify the token signature and structure
        session_info = self.verify_token(token)

        # Check if session is still active in database
        result = await self.session.execute(
            text("SELECT status FROM session_tokens WHERE session_id = :session_id"),
            {"session_id": session_info.session_id}
        )
        row = result.fetchone()

        if not row:
            raise AuthServiceError(ErrorCode.AUTH_REQUIRED, "Session not found")

        if row[0] != "active":
            raise AuthServiceError(ErrorCode.AUTH_EXPIRED, "Session has been revoked")

        # Check if certificate is still valid
        result = await self.session.execute(
            text("SELECT status, expires_at FROM certificates WHERE cert_id = :cert_id"),
            {"cert_id": session_info.cert_id}
        )
        row = result.fetchone()

        if not row:
            raise AuthServiceError(ErrorCode.AUTH_REQUIRED, "Associated certificate not found")

        cert_status, cert_expires = row
        if cert_status == "revoked":
            raise AuthServiceError(ErrorCode.CERTIFICATE_REVOKED, "Associated certificate has been revoked")
        if cert_status == "expired" or (cert_expires and parse_iso(cert_expires) < datetime.utcnow()):
            raise AuthServiceError(ErrorCode.CERTIFICATE_EXPIRED, "Associated certificate has expired")

        # Check if agent is still active
        result = await self.session.execute(
            text("SELECT status FROM agents WHERE agent_id = :agent_id"),
            {"agent_id": session_info.agent_id}
        )
        row = result.fetchone()

        if not row:
            raise AuthServiceError(ErrorCode.NOT_FOUND, "Agent not found")

        if row[0] != "active":
            raise AuthServiceError(ErrorCode.AGENT_SUSPENDED, f"Agent is {row[0]}")

        return session_info

    async def revoke_session(self, session_id: str) -> None:
        """
        Revoke a session.

        Args:
            session_id: Session ID to revoke
        """
        await self.session.execute(
            text("UPDATE session_tokens SET status = 'revoked' WHERE session_id = :session_id"),
            {"session_id": session_id}
        )
        await self.session.commit()
