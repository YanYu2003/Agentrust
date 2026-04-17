"""
Cryptographic utilities for Agentrust SDK.

Provides signing and verification functions using ECDSA P-256.
"""

import base64
import hashlib
import json
from typing import Any, Union

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend


def canonical_json(obj: Any) -> str:
    """
    Serialize an object to canonical JSON format.

    Rules:
    1. Keys are sorted alphabetically (recursively)
    2. No extra whitespace
    3. No trailing zeros in numbers

    Args:
        obj: Python object to serialize.

    Returns:
        Canonical JSON string.
    """
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _normalize(obj: Any) -> Any:
    """Recursively normalize an object for canonical serialization."""
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, (list, tuple)):
        return [_normalize(item) for item in obj]
    elif isinstance(obj, float):
        if obj != obj:  # NaN
            return "NaN"
        elif obj == float("inf"):
            return "Infinity"
        elif obj == float("-inf"):
            return "-Infinity"
        return obj
    else:
        return obj


def load_private_key(private_key_pem: str, password: str = None) -> ec.EllipticCurvePrivateKey:
    """
    Load an ECDSA P-256 private key from PEM format.

    Args:
        private_key_pem: PEM-encoded private key.
        password: Optional password for encrypted keys.

    Returns:
        ECDSA private key object.
    """
    if password:
        password_bytes = password.encode() if isinstance(password, str) else password
    else:
        password_bytes = None

    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=password_bytes,
        backend=default_backend(),
    )

    # Verify it's ECDSA P-256
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise ValueError("Key must be an ECDSA key")
    if private_key.curve.name != "secp256r1":
        raise ValueError("Key must be ECDSA P-256 (secp256r1)")

    return private_key


def load_public_key(public_key_pem: str) -> ec.EllipticCurvePublicKey:
    """
    Load an ECDSA P-256 public key from PEM format.

    Args:
        public_key_pem: PEM-encoded public key.

    Returns:
        ECDSA public key object.
    """
    public_key = serialization.load_pem_public_key(
        public_key_pem.encode(),
        backend=default_backend(),
    )

    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise ValueError("Key must be an ECDSA key")

    return public_key


def load_private_key_from_file(key_path: str, password: str = None) -> ec.EllipticCurvePrivateKey:
    """
    Load an ECDSA P-256 private key from a PEM file.

    Args:
        key_path: Path to the PEM file.
        password: Optional password for encrypted keys.

    Returns:
        ECDSA private key object.
    """
    with open(key_path, "rb") as f:
        private_key_pem = f.read().decode("utf-8")
    return load_private_key(private_key_pem, password)


def sign_data(private_key: ec.EllipticCurvePrivateKey, data: bytes) -> bytes:
    """
    Sign data using ECDSA P-256 with SHA-256.

    Args:
        private_key: ECDSA private key.
        data: Data to sign.

    Returns:
        DER-encoded signature bytes.
    """
    return private_key.sign(data, ec.ECDSA(hashes.SHA256()))


def sign_json(private_key: ec.EllipticCurvePrivateKey, data: dict) -> bytes:
    """
    Sign a JSON object using canonical JSON serialization.

    Args:
        private_key: ECDSA private key.
        data: Dictionary to sign.

    Returns:
        DER-encoded signature bytes.
    """
    canonical = canonical_json(data)
    return sign_data(private_key, canonical.encode("utf-8"))


def signature_to_base64(signature: bytes) -> str:
    """
    Convert DER signature to base64 string.

    Args:
        signature: DER-encoded signature bytes.

    Returns:
        Base64-encoded signature string.
    """
    return base64.b64encode(signature).decode("ascii")


def base64_to_signature(b64_signature: str) -> bytes:
    """
    Convert base64 string to DER signature.

    Args:
        b64_signature: Base64-encoded signature string.

    Returns:
        DER-encoded signature bytes.
    """
    return base64.b64decode(b64_signature)
