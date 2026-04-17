"""
Key generation and management utilities.

Implements ECDSA P-256 key pair generation with AES-256 encrypted private key storage.
"""

import base64
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

from app.config import settings

logger = logging.getLogger(__name__)

# Constants
ECDSA_CURVE = ec.SECP256R1()  # P-256 curve
KEY_ALGORITHM = "ES256"
AES_KEY_SIZE = 32  # 256 bits
SALT_SIZE = 16
NONCE_SIZE = 12  # GCM nonce size


def generate_ecdsa_keypair() -> Tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    """
    Generate an ECDSA P-256 key pair.

    Returns:
        Tuple of (private_key, public_key)
    """
    private_key = ec.generate_private_key(ECDSA_CURVE, default_backend())
    public_key = private_key.public_key()
    return private_key, public_key


def generate_ca_keypair(
    password: Optional[str] = None,
    validity_days: int = 365,
) -> dict:
    """
    Generate CA root key pair with encrypted private key storage.

    Args:
        password: Password for encrypting the private key.
                  If not provided, uses settings.ca_key_password.
        validity_days: Number of days until the key expires.

    Returns:
        Dictionary containing:
            - key_id: Unique identifier for the key
            - public_key_pem: PEM-encoded public key
            - encrypted_private_key: Base64-encoded encrypted private key
            - algorithm: Key algorithm (ES256)
            - created_at: ISO8601 timestamp
            - expires_at: ISO8601 timestamp
    """
    if password is None:
        password = settings.ca_key_password

    # Generate key pair
    private_key, public_key = generate_ecdsa_keypair()

    # Generate key ID
    key_id = f"root-{_generate_short_id()}"

    # Serialize public key to PEM
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Serialize and encrypt private key
    private_key_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    encrypted_private_key = _encrypt_private_key(private_key_der, password)

    now = datetime.utcnow()
    expires_at = now + timedelta(days=validity_days)

    return {
        "key_id": key_id,
        "public_key": public_key_pem,
        "encrypted_private_key": encrypted_private_key,
        "algorithm": KEY_ALGORITHM,
        "created_at": now.isoformat() + "Z",
        "expires_at": expires_at.isoformat() + "Z",
    }


def generate_agent_keypair() -> Tuple[str, str]:
    """
    Generate an agent key pair for registration.

    Returns:
        Tuple of (private_key_pem, public_key_pem)
    """
    private_key, public_key = generate_ecdsa_keypair()

    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    return private_key_pem, public_key_pem


def load_ca_private_key(
    encrypted_private_key: bytes,
    password: Optional[str] = None,
) -> ec.EllipticCurvePrivateKey:
    """
    Load and decrypt CA private key.

    Args:
        encrypted_private_key: Encrypted private key data.
        password: Password for decryption.
                  If not provided, uses settings.ca_key_password.

    Returns:
        ECDSA private key object.
    """
    if password is None:
        password = settings.ca_key_password

    decrypted_der = _decrypt_private_key(encrypted_private_key, password)

    private_key = serialization.load_der_private_key(
        decrypted_der,
        password=None,
        backend=default_backend(),
    )

    return private_key


def load_public_key_pem(pem_data: bytes) -> ec.EllipticCurvePublicKey:
    """
    Load a public key from PEM format.

    Args:
        pem_data: PEM-encoded public key.

    Returns:
        ECDSA public key object.
    """
    return serialization.load_pem_public_key(pem_data, backend=default_backend())


def load_private_key_pem(pem_data: bytes) -> ec.EllipticCurvePrivateKey:
    """
    Load a private key from PEM format.

    Args:
        pem_data: PEM-encoded private key.

    Returns:
        ECDSA private key object.
    """
    return serialization.load_pem_private_key(
        pem_data,
        password=None,
        backend=default_backend(),
    )


def save_ca_keypair(key_data: dict) -> Tuple[bytes, bytes]:
    """
    Prepare CA key pair for database storage.

    Args:
        key_data: Dictionary from generate_ca_keypair().

    Returns:
        Tuple of (public_key_blob, encrypted_private_key_blob) for database storage.
    """
    public_key_blob = key_data["public_key"] if isinstance(key_data["public_key"], bytes) else key_data["public_key"].encode()
    encrypted_private_key_blob = key_data["encrypted_private_key"] if isinstance(key_data["encrypted_private_key"], bytes) else key_data["encrypted_private_key"].encode()

    return public_key_blob, encrypted_private_key_blob


def public_key_to_pem(public_key: ec.EllipticCurvePublicKey) -> bytes:
    """
    Convert a public key object to PEM format.

    Args:
        public_key: ECDSA public key object.

    Returns:
        PEM-encoded public key bytes.
    """
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _encrypt_private_key(der_data: bytes, password: str) -> bytes:
    """
    Encrypt private key using AES-256-GCM.

    Args:
        der_data: DER-encoded private key.
        password: Encryption password.

    Returns:
        Encrypted data with salt and nonce prepended.
    """
    # Generate salt and derive key
    salt = os.urandom(SALT_SIZE)
    key = _derive_key(password, salt)

    # Generate nonce for GCM
    nonce = os.urandom(NONCE_SIZE)

    # Encrypt using AES-GCM
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(der_data) + encryptor.finalize()

    # Format: salt (16) + nonce (12) + tag (16) + ciphertext
    return salt + nonce + encryptor.tag + ciphertext


def _decrypt_private_key(encrypted_data: bytes, password: str) -> bytes:
    """
    Decrypt private key encrypted with AES-256-GCM.

    Args:
        encrypted_data: Encrypted data with salt and nonce prepended.
        password: Decryption password.

    Returns:
        DER-encoded private key.
    """
    # Extract components
    salt = encrypted_data[:SALT_SIZE]
    nonce = encrypted_data[SALT_SIZE : SALT_SIZE + NONCE_SIZE]
    tag = encrypted_data[SALT_SIZE + NONCE_SIZE : SALT_SIZE + NONCE_SIZE + 16]
    ciphertext = encrypted_data[SALT_SIZE + NONCE_SIZE + 16 :]

    # Derive key
    key = _derive_key(password, salt)

    # Decrypt using AES-GCM
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def _derive_key(password: str, salt: bytes) -> bytes:
    """
    Derive an AES key from password using PBKDF2.

    Args:
        password: Password string.
        salt: Salt bytes.

    Returns:
        Derived key bytes.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=AES_KEY_SIZE,
        salt=salt,
        iterations=100000,
        backend=default_backend(),
    )
    return kdf.derive(password.encode())


def _generate_short_id() -> str:
    """Generate a short random ID."""
    return base64.urlsafe_b64encode(os.urandom(6)).decode().rstrip("=")
