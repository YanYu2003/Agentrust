"""
Tests for cryptographic utilities.
"""

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.crypto.keys import (
    generate_ecdsa_keypair,
    generate_ca_keypair,
    generate_agent_keypair,
    load_ca_private_key,
    load_public_key_pem,
    load_private_key_pem,
    save_ca_keypair,
    _encrypt_private_key,
    _decrypt_private_key,
)
from app.crypto.signature import (
    sign_data,
    verify_signature,
    sign_json,
    verify_json_signature,
)
from app.crypto.canonical import canonical_json


class TestCanonicalJSON:
    """Tests for canonical JSON serialization."""

    def test_sorts_keys(self):
        """Keys should be sorted alphabetically."""
        result = canonical_json({"b": 1, "a": 2, "c": 3})
        assert result == '{"a":2,"b":1,"c":3}'

    def test_no_whitespace(self):
        """Output should have no extra whitespace."""
        result = canonical_json({"key": "value"})
        assert result == '{"key":"value"}'
        assert " " not in result

    def test_nested_objects(self):
        """Nested objects should also be sorted."""
        result = canonical_json({"outer": {"b": 1, "a": 2}})
        assert result == '{"outer":{"a":2,"b":1}}'

    def test_arrays_preserved(self):
        """Array order should be preserved."""
        result = canonical_json({"items": [3, 1, 2]})
        assert result == '{"items":[3,1,2]}'

    def test_deterministic(self):
        """Same logical object should produce same output."""
        obj1 = {"z": 1, "a": 2}
        obj2 = {"a": 2, "z": 1}
        assert canonical_json(obj1) == canonical_json(obj2)


class TestKeyGeneration:
    """Tests for key generation."""

    def test_generate_ecdsa_keypair(self):
        """Should generate valid ECDSA P-256 key pair."""
        private_key, public_key = generate_ecdsa_keypair()

        assert isinstance(private_key, ec.EllipticCurvePrivateKey)
        assert isinstance(public_key, ec.EllipticCurvePublicKey)

        # Check curve is P-256
        assert private_key.curve.name == "secp256r1"

    def test_generate_ca_keypair(self):
        """Should generate CA key pair with encrypted private key."""
        key_data = generate_ca_keypair(password="test_password", validity_days=30)

        assert "key_id" in key_data
        assert key_data["key_id"].startswith("root-")
        assert key_data["algorithm"] == "ES256"
        assert "public_key" in key_data
        assert "encrypted_private_key" in key_data
        assert "expires_at" in key_data

    def test_generate_agent_keypair(self):
        """Should generate agent key pair in PEM format."""
        private_pem, public_pem = generate_agent_keypair()

        assert b"-----BEGIN PRIVATE KEY-----" in private_pem
        assert b"-----BEGIN PUBLIC KEY-----" in public_pem

        # Should be loadable
        private_key = load_private_key_pem(private_pem)
        public_key = load_public_key_pem(public_pem)

        assert isinstance(private_key, ec.EllipticCurvePrivateKey)
        assert isinstance(public_key, ec.EllipticCurvePublicKey)

    def test_encrypt_decrypt_private_key(self):
        """Private key encryption should be reversible."""
        private_key, _ = generate_ecdsa_keypair()

        # Serialize to DER
        from cryptography.hazmat.primitives import serialization
        der_data = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        # Encrypt
        encrypted = _encrypt_private_key(der_data, "password123")

        # Decrypt
        decrypted = _decrypt_private_key(encrypted, "password123")

        assert decrypted == der_data

    def test_decrypt_wrong_password_fails(self):
        """Decryption with wrong password should fail."""
        private_key, _ = generate_ecdsa_keypair()

        from cryptography.hazmat.primitives import serialization
        der_data = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        encrypted = _encrypt_private_key(der_data, "correct_password")

        with pytest.raises(Exception):
            _decrypt_private_key(encrypted, "wrong_password")


class TestSignature:
    """Tests for digital signatures."""

    def test_sign_and_verify_data(self):
        """Should sign and verify data correctly."""
        private_key, public_key = generate_ecdsa_keypair()

        data = b"Hello, World!"
        signature = sign_data(private_key, data)

        assert verify_signature(public_key, signature, data) is True

    def test_verify_wrong_data_fails(self):
        """Verification should fail for different data."""
        private_key, public_key = generate_ecdsa_keypair()

        signature = sign_data(private_key, b"Original data")
        assert verify_signature(public_key, signature, b"Different data") is False

    def test_sign_and_verify_json(self):
        """Should sign and verify JSON correctly."""
        private_key, public_key = generate_ecdsa_keypair()

        data = {"message": "Hello", "number": 42}
        signature = sign_json(private_key, data)

        assert verify_json_signature(public_key, signature, data) is True

    def test_json_key_order_doesnt_matter(self):
        """JSON signature should be independent of key order."""
        private_key, public_key = generate_ecdsa_keypair()

        # Different key orders
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}

        signature1 = sign_json(private_key, data1)
        signature2 = sign_json(private_key, data2)

        # Both should verify with either data
        assert verify_json_signature(public_key, signature1, data1) is True
        assert verify_json_signature(public_key, signature2, data2) is True
        assert verify_json_signature(public_key, signature1, data2) is True
        assert verify_json_signature(public_key, signature2, data1) is True


class TestCAKeyLoading:
    """Tests for CA key loading."""

    def test_load_ca_private_key(self):
        """Should load and decrypt CA private key."""
        key_data = generate_ca_keypair(password="test_password")

        # Save to storage format
        _, encrypted_blob = save_ca_keypair(key_data)

        # Load back
        private_key = load_ca_private_key(encrypted_blob, "test_password")

        assert isinstance(private_key, ec.EllipticCurvePrivateKey)

    def test_load_ca_key_with_default_password(self):
        """Should use default password from settings."""
        key_data = generate_ca_keypair()  # No password, uses settings

        _, encrypted_blob = save_ca_keypair(key_data)

        # Should load with default password
        private_key = load_ca_private_key(encrypted_blob)

        assert isinstance(private_key, ec.EllipticCurvePrivateKey)
