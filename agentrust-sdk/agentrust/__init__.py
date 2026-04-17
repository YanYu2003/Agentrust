"""
Agentrust SDK - Agent Identity and Permission System

A Python SDK for agents to interact with the Agentrust system.

Example usage:
    from agentrust import AgentWallet, AgentClient

    # Initialize wallet with private key
    wallet = AgentWallet("./keys/agent_private.pem")

    # Create client
    client = AgentClient("http://localhost:8000/api/v1", wallet)

    # Authenticate
    client.authenticate("agent-analyst", "cert-001")

    # Execute operations
    result = client.execute("read_database", "user_table")

    # Delegate capability
    delegation = client.delegate(
        to_agent_id="agent-reporter",
        capability="read_database",
        resource_scope="user_table",
        attenuations={"rows_limit": 100},
    )
"""

from .wallet import AgentWallet, Certificate, CapabilityToken, DelegationToken
from .client import AgentClient
from .feishu import FeishuClient
from .exceptions import (
    AgentrustError,
    AuthenticationError,
    PermissionDeniedError,
    TokenExpiredError,
    DelegationChainError,
    CertificateRevokedError,
    InvalidRequestError,
    NetworkError,
)
from .crypto import (
    canonical_json,
    load_private_key,
    load_public_key,
    load_private_key_from_file,
    sign_data,
    sign_json,
    signature_to_base64,
    base64_to_signature,
)

__version__ = "1.0.0"

__all__ = [
    # Wallet
    "AgentWallet",
    "Certificate",
    "CapabilityToken",
    "DelegationToken",
    # Client
    "AgentClient",
    # Feishu
    "FeishuClient",
    # Exceptions
    "AgentrustError",
    "AuthenticationError",
    "PermissionDeniedError",
    "TokenExpiredError",
    "DelegationChainError",
    "CertificateRevokedError",
    "InvalidRequestError",
    "NetworkError",
    # Crypto utilities
    "canonical_json",
    "load_private_key",
    "load_public_key",
    "load_private_key_from_file",
    "sign_data",
    "sign_json",
    "signature_to_base64",
    "base64_to_signature",
]
