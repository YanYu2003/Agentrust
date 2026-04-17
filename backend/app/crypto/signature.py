"""
Digital signature utilities for ECDSA.

Implements signing and verification using ECDSA P-256 with SHA-256 (ES256).
"""

import hashlib
import logging
from typing import Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
from cryptography.hazmat.backends import default_backend

from app.crypto.canonical import canonical_json

logger = logging.getLogger(__name__)


def sign_data(private_key: ec.EllipticCurvePrivateKey, data: bytes) -> bytes:
    """
    Sign data using ECDSA P-256 with SHA-256.

    Args:
        private_key: ECDSA private key.
        data: Data to sign.

    Returns:
        DER-encoded signature.
    """
    signature = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    return signature


def verify_signature(
    public_key: ec.EllipticCurvePublicKey,
    signature: bytes,
    data: bytes,
) -> bool:
    """
    Verify an ECDSA signature.

    Args:
        public_key: ECDSA public key.
        signature: DER-encoded signature.
        data: Original data that was signed.

    Returns:
        True if signature is valid, False otherwise.
    """
    try:
        public_key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception as e:
        logger.debug(f"Signature verification failed: {e}")
        return False


def sign_json(
    private_key: ec.EllipticCurvePrivateKey,
    data: dict,
) -> bytes:
    """
    Sign a JSON object using canonical JSON serialization.

    This ensures deterministic signing regardless of key ordering.

    Args:
        private_key: ECDSA private key.
        data: Dictionary to sign.

    Returns:
        DER-encoded signature.
    """
    canonical = canonical_json(data)
    return sign_data(private_key, canonical.encode("utf-8"))


def verify_json_signature(
    public_key: ec.EllipticCurvePublicKey,
    signature: bytes,
    data: dict,
) -> bool:
    """
    Verify a signature on a JSON object.

    Args:
        public_key: ECDSA public key.
        signature: DER-encoded signature.
        data: Dictionary that was signed.

    Returns:
        True if signature is valid, False otherwise.
    """
    canonical = canonical_json(data)
    return verify_signature(public_key, signature, canonical.encode("utf-8"))


def signature_to_base64(signature: bytes) -> str:
    """
    Convert a DER signature to base64 string.

    Args:
        signature: DER-encoded signature.

    Returns:
        Base64-encoded signature string.
    """
    import base64
    return base64.b64encode(signature).decode("ascii")


def base64_to_signature(b64_signature: str) -> bytes:
    """
    Convert a base64 string to DER signature.

    Args:
        b64_signature: Base64-encoded signature string.

    Returns:
        DER-encoded signature bytes.
    """
    import base64
    return base64.b64decode(b64_signature)
