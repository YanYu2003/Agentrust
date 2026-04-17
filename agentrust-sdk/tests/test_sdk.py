"""
Tests for Agentrust SDK.
"""

import pytest

from agentrust import (
    AgentWallet,
    Certificate,
    CapabilityToken,
    DelegationToken,
    AgentClient,
    FeishuClient,
    AgentrustError,
    AuthenticationError,
    PermissionDeniedError,
    TokenExpiredError,
    DelegationChainError,
    CertificateRevokedError,
    InvalidRequestError,
    NetworkError,
)
from agentrust.crypto import canonical_json, sign_data, signature_to_base64, base64_to_signature


class TestExceptions:
    """Test exception classes."""

    def test_agentrust_error(self):
        err = AgentrustError("test error", {"key": "value"})
        assert err.message == "test error"
        assert err.details == {"key": "value"}

    def test_authentication_error(self):
        err = AuthenticationError("auth failed")
        assert "auth failed" in str(err)

    def test_permission_denied_error(self):
        err = PermissionDeniedError("access denied")
        assert "access denied" in str(err)

    def test_token_expired_error(self):
        err = TokenExpiredError("token expired")
        assert "expired" in str(err)

    def test_delegation_chain_error(self):
        err = DelegationChainError("chain invalid")
        assert "invalid" in str(err)


class TestCanonicalJson:
    """Test canonical JSON serialization."""

    def test_sorts_keys(self):
        data = {"b": 1, "a": 2}
        result = canonical_json(data)
        assert '"a":2' in result
        assert '"b":1' in result

    def test_no_whitespace(self):
        data = {"a": 1, "b": 2}
        result = canonical_json(data)
        assert " " not in result

    def test_nested_objects(self):
        data = {"outer": {"b": 1, "a": 2}, "c": 3}
        result = canonical_json(data)
        # Keys should be sorted at all levels
        # c comes before o, and a comes before b
        assert result.index('"a"') < result.index('"b"')
        assert result.index('"c"') < result.index('"outer"')


class TestCertificate:
    """Test Certificate class."""

    def test_certificate_creation(self):
        cert = Certificate(
            cert_id="cert-001",
            public_key_pem="-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...\n-----END PUBLIC KEY-----",
            issuer_key_id="root-key-001",
            capabilities=["read_database", "write_database"],
            trust_level=3,
            algorithm="ES256",
            issued_at="2025-01-01T00:00:00Z",
            expires_at="2025-01-02T00:00:00Z",
            signature="base64sig",
        )
        assert cert.cert_id == "cert-001"
        assert cert.trust_level == 3
        assert "read_database" in cert.capabilities

    def test_certificate_validity(self):
        cert = Certificate(
            cert_id="cert-expired",
            public_key_pem="-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...\n-----END PUBLIC KEY-----",
            issuer_key_id="root-key-001",
            capabilities=[],
            trust_level=1,
            algorithm="ES256",
            issued_at="2020-01-01T00:00:00Z",
            expires_at="2020-01-02T00:00:00Z",
            signature="base64sig",
        )
        assert not cert.is_valid()


class TestCapabilityToken:
    """Test CapabilityToken class."""

    def test_token_creation(self):
        token = CapabilityToken(
            token_id="cap-001",
            capability="read_database",
            resource_scope="*",
            attenuations={"rows_limit": 100},
        )
        assert token.token_id == "cap-001"
        assert token.capability == "read_database"
        assert token.resource_scope == "*"
        assert token.attenuations == {"rows_limit": 100}

    def test_token_validity(self):
        # Token without expiry is always valid
        token = CapabilityToken(
            token_id="cap-001",
            capability="read_database",
        )
        assert token.is_valid()


class TestDelegationToken:
    """Test DelegationToken class."""

    def test_delegation_token_creation(self):
        token = DelegationToken(
            delegation_id="del-001",
            from_agent_id="agent-a",
            capability="read_database",
            resource_scope="user_table",
            attenuations={"rows_limit": 50},
            current_depth=1,
        )
        assert token.delegation_id == "del-001"
        assert token.from_agent_id == "agent-a"
        assert token.current_depth == 1

    def test_can_delegate(self):
        token_full = DelegationToken(
            delegation_id="del-001",
            from_agent_id="agent-a",
            capability="read_database",
            current_depth=1,
        )
        assert token_full.can_delegate()

        token_empty = DelegationToken(
            delegation_id="del-002",
            from_agent_id="agent-a",
            capability="read_database",
            current_depth=0,
        )
        assert not token_empty.can_delegate()


class TestAgentWallet:
    """Test AgentWallet class."""

    @pytest.fixture
    def real_private_key_pem(self):
        """Generate a real EC P-256 private key for testing."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        private_key = ec.generate_private_key(ec.SECP256R1())
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

    def test_wallet_requires_key(self):
        with pytest.raises(ValueError):
            AgentWallet()

    def test_wallet_with_invalid_pem(self):
        with pytest.raises(ValueError):
            AgentWallet(private_key_pem="not a valid pem")

    def test_wallet_certificates(self, real_private_key_pem):
        wallet = AgentWallet(private_key_pem=real_private_key_pem)
        assert wallet.agent_id is None

        # Load a certificate with future expiry
        wallet.load_certificate({
            "cert_id": "cert-001",
            "public_key": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...\n-----END PUBLIC KEY-----",
            "issuer_key_id": "root-key-001",
            "capabilities": ["read_database"],
            "trust_level": 3,
            "algorithm": "ES256",
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2027-12-31T23:59:59Z",
            "signature": "sig",
        })

        cert = wallet.get_certificate()
        assert cert is not None
        assert cert.cert_id == "cert-001"

    def test_add_capability_token(self, real_private_key_pem):
        wallet = AgentWallet(private_key_pem=real_private_key_pem)

        wallet.add_capability_token({
            "token_id": "cap-001",
            "capability": "read_database",
            "resource_scope": "*",
            "attenuations": {},
            "expires_at": "2027-12-31T23:59:59Z",
        })

        token = wallet.get_capability_token("read_database")
        assert token is not None
        assert token.token_id == "cap-001"

    def test_list_capabilities(self, real_private_key_pem):
        wallet = AgentWallet(private_key_pem=real_private_key_pem)

        wallet.add_capability_token({
            "token_id": "cap-001",
            "capability": "read_database",
            "expires_at": "2027-12-31T23:59:59Z",
        })
        wallet.add_capability_token({
            "token_id": "cap-002",
            "capability": "write_database",
            "expires_at": "2027-12-31T23:59:59Z",
        })

        caps = wallet.list_capabilities()
        assert "read_database" in caps
        assert "write_database" in caps
