"""
Integration tests for CA Service.
"""

import base64
import json
import pytest
import pytest_asyncio
from datetime import datetime
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import Settings, settings
from app.database import SCHEMA_STATEMENTS
from app.services.ca_service import CAService, CAServiceError
from app.services.auth_service import AuthService
from app.crypto.keys import generate_agent_keypair, load_private_key_pem
from app.crypto.signature import sign_data
from app.schemas.common import ErrorCode


@pytest.fixture(scope="session")
def test_settings():
    """Create test settings."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
    )


@pytest_asyncio.fixture(scope="function")
async def session(test_settings):
    """Create an in-memory test database session."""
    engine = create_async_engine(
        test_settings.database_url,
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(text(statement))
        await conn.execute(
            text("INSERT INTO schema_version (version, description) VALUES (1, 'Initial schema')")
        )

        # Insert a test CA key - use the global settings password
        from app.crypto.keys import generate_ca_keypair, save_ca_keypair
        # Use the global settings.ca_key_password for consistency
        key_data = generate_ca_keypair(password=settings.ca_key_password, validity_days=365)
        public_key_blob, encrypted_private_key_blob = save_ca_keypair(key_data)

        await conn.execute(
            text("""
                INSERT INTO ca_root_keys (key_id, public_key, encrypted_private_key, algorithm, created_at, expires_at)
                VALUES (:key_id, :public_key, :encrypted_private_key, :algorithm, :created_at, :expires_at)
            """),
            {
                "key_id": key_data["key_id"],
                "public_key": public_key_blob,
                "encrypted_private_key": encrypted_private_key_blob,
                "algorithm": key_data["algorithm"],
                "created_at": key_data["created_at"],
                "expires_at": key_data["expires_at"],
            },
        )

    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_maker() as session:
        yield session

    await engine.dispose()


class TestCAService:
    """Tests for CA Service."""

    @pytest.mark.asyncio
    async def test_register_agent(self, session):
        """Test agent registration."""
        ca_service = CAService(session)

        # Generate agent key pair
        private_pem, public_pem = generate_agent_keypair()

        result = await ca_service.register_agent(
            name="test-agent",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database", "read_document"],
            description="Test agent",
            trust_level=3,
        )

        assert "agent_id" in result
        assert result["agent_id"].startswith("agent-")
        assert "certificate" in result
        assert "capability_tokens" in result
        assert len(result["capability_tokens"]) == 2

    @pytest.mark.asyncio
    async def test_register_duplicate_name(self, session):
        """Test that duplicate agent names are rejected."""
        ca_service = CAService(session)

        private_pem, public_pem = generate_agent_keypair()

        # First registration
        await ca_service.register_agent(
            name="duplicate-test",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
        )

        # Second registration with same name should fail
        with pytest.raises(CAServiceError) as exc_info:
            await ca_service.register_agent(
                name="duplicate-test",
                public_key_pem=public_pem.decode(),
                owner="test-user",
                requested_capabilities=["read_database"],
            )

        assert exc_info.value.code == ErrorCode.CONFLICT

    @pytest.mark.asyncio
    async def test_register_invalid_capability(self, session):
        """Test that invalid capabilities are rejected."""
        ca_service = CAService(session)

        private_pem, public_pem = generate_agent_keypair()

        with pytest.raises(CAServiceError) as exc_info:
            await ca_service.register_agent(
                name="invalid-cap-agent",
                public_key_pem=public_pem.decode(),
                owner="test-user",
                requested_capabilities=["invalid_capability"],
            )

        assert exc_info.value.code == ErrorCode.INVALID_CAPABILITY

    @pytest.mark.asyncio
    async def test_trust_level_affects_validity(self, session):
        """Test that trust_level affects certificate validity."""
        ca_service = CAService(session)

        private_pem, public_pem = generate_agent_keypair()

        # Trust level 1 = 1 hour
        result1 = await ca_service.register_agent(
            name="trust-level-1",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
            trust_level=1,
        )

        # Trust level 5 = 168 hours (7 days)
        private_pem2, public_pem2 = generate_agent_keypair()
        result5 = await ca_service.register_agent(
            name="trust-level-5",
            public_key_pem=public_pem2.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
            trust_level=5,
        )

        # Parse expiry times and compare
        from app.utils import parse_iso
        expiry1 = parse_iso(result1["certificate"]["expires_at"])
        expiry5 = parse_iso(result5["certificate"]["expires_at"])

        # Trust level 5 should have longer validity
        assert expiry5 > expiry1


class TestChallengeResponse:
    """Tests for challenge-response authentication."""

    @pytest.mark.asyncio
    async def test_challenge_and_verify(self, session):
        """Test complete challenge-response flow."""
        ca_service = CAService(session)

        # Register agent
        private_pem, public_pem = generate_agent_keypair()
        private_key = load_private_key_pem(private_pem)

        result = await ca_service.register_agent(
            name="auth-test-agent",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
            trust_level=3,
        )

        agent_id = result["agent_id"]
        cert_id = result["certificate"]["cert_id"]

        # Create challenge
        challenge = await ca_service.create_challenge(agent_id, cert_id)
        assert "challenge_id" in challenge
        assert "nonce" in challenge

        # Sign the nonce
        signed_nonce = sign_data(private_key, challenge["nonce"].encode())
        signed_nonce_b64 = base64.b64encode(signed_nonce).decode()

        # Verify challenge
        verify_result = await ca_service.verify_challenge(
            challenge_id=challenge["challenge_id"],
            agent_id=agent_id,
            signed_nonce=signed_nonce_b64,
        )

        assert "session_token" in verify_result
        assert verify_result["agent_id"] == agent_id

    @pytest.mark.asyncio
    async def test_wrong_signature_fails(self, session):
        """Test that wrong signature is rejected."""
        ca_service = CAService(session)

        # Register agent
        private_pem, public_pem = generate_agent_keypair()

        result = await ca_service.register_agent(
            name="wrong-sig-agent",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
        )

        agent_id = result["agent_id"]
        cert_id = result["certificate"]["cert_id"]

        # Create challenge
        challenge = await ca_service.create_challenge(agent_id, cert_id)

        # Use wrong signature
        wrong_sig = base64.b64encode(b"wrong_signature").decode()

        with pytest.raises(CAServiceError) as exc_info:
            await ca_service.verify_challenge(
                challenge_id=challenge["challenge_id"],
                agent_id=agent_id,
                signed_nonce=wrong_sig,
            )

        assert exc_info.value.code == ErrorCode.AUTH_INVALID_SIGNATURE

    @pytest.mark.asyncio
    async def test_challenge_cannot_be_reused(self, session):
        """Test that a challenge cannot be used twice."""
        ca_service = CAService(session)

        # Register agent
        private_pem, public_pem = generate_agent_keypair()
        private_key = load_private_key_pem(private_pem)

        result = await ca_service.register_agent(
            name="reuse-test-agent",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
        )

        agent_id = result["agent_id"]
        cert_id = result["certificate"]["cert_id"]

        # Create and verify challenge
        challenge = await ca_service.create_challenge(agent_id, cert_id)
        signed_nonce = base64.b64encode(
            sign_data(private_key, challenge["nonce"].encode())
        ).decode()

        # First verification should succeed
        await ca_service.verify_challenge(
            challenge_id=challenge["challenge_id"],
            agent_id=agent_id,
            signed_nonce=signed_nonce,
        )

        # Second verification should fail
        with pytest.raises(CAServiceError) as exc_info:
            await ca_service.verify_challenge(
                challenge_id=challenge["challenge_id"],
                agent_id=agent_id,
                signed_nonce=signed_nonce,
            )

        assert exc_info.value.code == ErrorCode.AUTH_INVALID_SIGNATURE


class TestCertificateRevocation:
    """Tests for certificate revocation."""

    @pytest.mark.asyncio
    async def test_revoke_certificate(self, session):
        """Test certificate revocation."""
        ca_service = CAService(session)

        # Register agent
        private_pem, public_pem = generate_agent_keypair()

        result = await ca_service.register_agent(
            name="revoke-test-agent",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
        )

        cert_id = result["certificate"]["cert_id"]

        # Revoke certificate
        revoke_result = await ca_service.revoke_certificate(
            cert_id=cert_id,
            reason="Test revocation",
            revoked_by="admin",
        )

        assert revoke_result["status"] == "revoked"

        # Get CRL and verify
        crl = await ca_service.get_crl()
        revoked_ids = [e["cert_id"] for e in crl["entries"]]
        assert cert_id in revoked_ids

    @pytest.mark.asyncio
    async def test_revoked_cert_cannot_auth(self, session):
        """Test that revoked certificate cannot authenticate."""
        ca_service = CAService(session)

        # Register agent
        private_pem, public_pem = generate_agent_keypair()
        private_key = load_private_key_pem(private_pem)

        result = await ca_service.register_agent(
            name="revoked-auth-agent",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
        )

        agent_id = result["agent_id"]
        cert_id = result["certificate"]["cert_id"]

        # Revoke certificate
        await ca_service.revoke_certificate(
            cert_id=cert_id,
            reason="Test revocation",
            revoked_by="admin",
        )

        # Try to create challenge - should fail
        with pytest.raises(CAServiceError) as exc_info:
            await ca_service.create_challenge(agent_id, cert_id)

        assert exc_info.value.code == ErrorCode.CERTIFICATE_REVOKED


class TestSessionToken:
    """Tests for session token."""

    @pytest.mark.asyncio
    async def test_session_token_validation(self, session):
        """Test session token validation."""
        ca_service = CAService(session)
        auth_service = AuthService(session)

        # Register agent and authenticate
        private_pem, public_pem = generate_agent_keypair()
        private_key = load_private_key_pem(private_pem)

        result = await ca_service.register_agent(
            name="session-test-agent",
            public_key_pem=public_pem.decode(),
            owner="test-user",
            requested_capabilities=["read_database"],
        )

        agent_id = result["agent_id"]
        cert_id = result["certificate"]["cert_id"]

        challenge = await ca_service.create_challenge(agent_id, cert_id)
        signed_nonce = base64.b64encode(
            sign_data(private_key, challenge["nonce"].encode())
        ).decode()

        verify_result = await ca_service.verify_challenge(
            challenge_id=challenge["challenge_id"],
            agent_id=agent_id,
            signed_nonce=signed_nonce,
        )

        token = verify_result["session_token"]

        # Validate token
        session_info = await auth_service.validate_session(token)

        assert session_info.agent_id == agent_id
        assert session_info.cert_id == cert_id

    @pytest.mark.asyncio
    async def test_invalid_token_fails(self, session):
        """Test that invalid token is rejected."""
        auth_service = AuthService(session)

        from app.services.auth_service import AuthServiceError

        with pytest.raises(AuthServiceError):
            await auth_service.validate_session("invalid.token.here")
