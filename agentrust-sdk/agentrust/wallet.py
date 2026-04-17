"""
AgentWallet - Manage agent's private key, certificates, and tokens.

The wallet is responsible for:
- Storing the agent's private key (never leaves the wallet)
- Caching certificates and tokens
- Providing signing capabilities
"""

import base64
import time
from typing import Dict, List, Optional, Any

from cryptography.hazmat.primitives.asymmetric import ec

from .crypto import load_private_key, sign_json, signature_to_base64


class Certificate:
    """Represents an agent's certificate."""

    def __init__(
        self,
        cert_id: str,
        public_key_pem: str,
        issuer_key_id: str,
        capabilities: List[str],
        trust_level: int,
        algorithm: str,
        issued_at: str,
        expires_at: str,
        signature: str,
    ):
        self.cert_id = cert_id
        self.public_key_pem = public_key_pem
        self.issuer_key_id = issuer_key_id
        self.capabilities = capabilities
        self.trust_level = trust_level
        self.algorithm = algorithm
        self.issued_at = issued_at
        self.expires_at = expires_at
        self.signature = signature

    def is_valid(self) -> bool:
        """Check if certificate is currently valid (not expired)."""
        try:
            from datetime import datetime
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.utcnow() < expiry.replace(tzinfo=None)
        except (ValueError, AttributeError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "cert_id": self.cert_id,
            "public_key_pem": self.public_key_pem,
            "issuer_key_id": self.issuer_key_id,
            "capabilities": self.capabilities,
            "trust_level": self.trust_level,
            "algorithm": self.algorithm,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature": self.signature,
        }


class CapabilityToken:
    """Represents a capability token."""

    def __init__(
        self,
        token_id: str,
        capability: str,
        resource_scope: str = "*",
        attenuations: Dict[str, Any] = None,
        expires_at: str = None,
    ):
        self.token_id = token_id
        self.capability = capability
        self.resource_scope = resource_scope
        self.attenuations = attenuations or {}
        self.expires_at = expires_at

    def is_valid(self) -> bool:
        """Check if token is currently valid."""
        if not self.expires_at:
            return True
        try:
            from datetime import datetime
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.utcnow() < expiry.replace(tzinfo=None)
        except (ValueError, AttributeError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "token_id": self.token_id,
            "capability": self.capability,
            "resource_scope": self.resource_scope,
            "attenuations": self.attenuations,
            "expires_at": self.expires_at,
        }


class DelegationToken:
    """Represents a delegation token received from another agent."""

    def __init__(
        self,
        delegation_id: str,
        from_agent_id: str,
        capability: str,
        resource_scope: str = "*",
        attenuations: Dict[str, Any] = None,
        current_depth: int = 0,
        expires_at: str = None,
    ):
        self.delegation_id = delegation_id
        self.from_agent_id = from_agent_id
        self.capability = capability
        self.resource_scope = resource_scope
        self.attenuations = attenuations or {}
        self.current_depth = current_depth
        self.expires_at = expires_at

    def is_valid(self) -> bool:
        """Check if token is currently valid."""
        if not self.expires_at:
            return True
        try:
            from datetime import datetime
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.utcnow() < expiry.replace(tzinfo=None)
        except (ValueError, AttributeError):
            return False

    def can_delegate(self) -> bool:
        """Check if this token can be used for further delegation."""
        return self.current_depth > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "delegation_id": self.delegation_id,
            "from_agent_id": self.from_agent_id,
            "capability": self.capability,
            "resource_scope": self.resource_scope,
            "attenuations": self.attenuations,
            "current_depth": self.current_depth,
            "expires_at": self.expires_at,
        }


class AgentWallet:
    """
    Wallet for managing an agent's identity and tokens.

    The wallet stores:
    - Private key (never exposed outside the wallet)
    - Certificate(s) issued by the CA
    - Capability tokens granted by the CA
    - Delegation tokens received from other agents

    Usage:
        wallet = AgentWallet("./keys/agent_private.pem")

        # After registration, load certificate and tokens
        wallet.load_certificate(cert_data)
        wallet.add_capability_token(token_data)

        # Sign data (private key never leaves wallet)
        signature = wallet.sign(data)
    """

    def __init__(self, private_key_path: str = None, private_key_pem: str = None, password: str = None):
        """
        Initialize the wallet.

        Args:
            private_key_path: Path to PEM file containing private key.
            private_key_pem: PEM string containing private key.
            password: Optional password for encrypted private key.
        """
        if private_key_path:
            self.private_key = load_private_key_from_file(private_key_path, password)
        elif private_key_pem:
            self.private_key = load_private_key(private_key_pem, password)
        else:
            raise ValueError("Either private_key_path or private_key_pem must be provided")

        self._certificates: Dict[str, Certificate] = {}
        self._capability_tokens: Dict[str, CapabilityToken] = {}
        self._delegation_tokens: Dict[str, DelegationToken] = {}
        self._agent_id: Optional[str] = None

    @property
    def agent_id(self) -> Optional[str]:
        """Get the agent ID."""
        return self._agent_id

    @agent_id.setter
    def agent_id(self, value: str):
        """Set the agent ID."""
        self._agent_id = value

    def load_certificate(self, cert_data: Dict[str, Any]):
        """
        Load a certificate into the wallet.

        Args:
            cert_data: Certificate data dictionary from registration response.
        """
        cert = Certificate(
            cert_id=cert_data["cert_id"],
            public_key_pem=cert_data["public_key"],
            issuer_key_id=cert_data["issuer_key_id"],
            capabilities=cert_data["capabilities"],
            trust_level=cert_data["trust_level"],
            algorithm=cert_data["algorithm"],
            issued_at=cert_data["issued_at"],
            expires_at=cert_data["expires_at"],
            signature=cert_data["signature"],
        )
        self._certificates[cert.cert_id] = cert

        # Also set agent_id from certificate's agent_id (if available in cert_data)
        if "agent_id" in cert_data:
            self._agent_id = cert_data["agent_id"]

    def add_capability_token(self, token_data: Dict[str, Any]):
        """
        Add a capability token to the wallet.

        Args:
            token_data: Token data dictionary from registration response.
        """
        token = CapabilityToken(
            token_id=token_data["token_id"],
            capability=token_data["capability"],
            resource_scope=token_data.get("resource_scope", "*"),
            attenuations=token_data.get("attenuations", {}),
            expires_at=token_data.get("expires_at"),
        )
        self._capability_tokens[token.token_id] = token

    def add_delegation_token(self, token_data: Dict[str, Any]):
        """
        Add a delegation token to the wallet.

        Args:
            token_data: Delegation token data from delegation response.
        """
        token = DelegationToken(
            delegation_id=token_data["delegation_id"],
            from_agent_id=token_data["from_agent_id"],
            capability=token_data["capability"],
            resource_scope=token_data.get("resource_scope", "*"),
            attenuations=token_data.get("attenuations", {}),
            current_depth=token_data.get("current_depth", 0),
            expires_at=token_data.get("expires_at"),
        )
        self._delegation_tokens[token.delegation_id] = token

    def get_certificate(self, cert_id: str = None) -> Optional[Certificate]:
        """
        Get a certificate by ID, or the first valid certificate if no ID provided.

        Args:
            cert_id: Optional certificate ID.

        Returns:
            Certificate or None.
        """
        if cert_id:
            return self._certificates.get(cert_id)

        # Return first valid certificate
        for cert in self._certificates.values():
            if cert.is_valid():
                return cert
        return None

    def get_capability_token(self, capability: str) -> Optional[CapabilityToken]:
        """
        Get a capability token by capability name.

        Args:
            capability: Capability name (e.g., "read_database").

        Returns:
            CapabilityToken or None.
        """
        for token in self._capability_tokens.values():
            if token.capability == capability and token.is_valid():
                return token
        return None

    def get_capability_tokens_by_capability(self, capability: str) -> List[CapabilityToken]:
        """
        Get all capability tokens for a given capability.

        Args:
            capability: Capability name.

        Returns:
            List of valid CapabilityTokens.
        """
        return [
            token for token in self._capability_tokens.values()
            if token.capability == capability and token.is_valid()
        ]

    def get_delegation_token(self, delegation_id: str) -> Optional[DelegationToken]:
        """
        Get a delegation token by ID.

        Args:
            delegation_id: Delegation token ID.

        Returns:
            DelegationToken or None.
        """
        token = self._delegation_tokens.get(delegation_id)
        if token and token.is_valid():
            return token
        return None

    def get_all_delegation_tokens(self) -> List[DelegationToken]:
        """
        Get all valid delegation tokens.

        Returns:
            List of valid DelegationTokens.
        """
        return [
            token for token in self._delegation_tokens.values()
            if token.is_valid()
        ]

    def get_delegation_tokens_for_capability(self, capability: str) -> List[DelegationToken]:
        """
        Get all delegation tokens that grant a specific capability.

        Args:
            capability: Capability name.

        Returns:
            List of valid DelegationTokens.
        """
        return [
            token for token in self._delegation_tokens.values()
            if token.capability == capability and token.is_valid()
        ]

    def sign(self, data: dict) -> str:
        """
        Sign data using the wallet's private key.

        The private key NEVER leaves this wallet.

        Args:
            data: Dictionary to sign.

        Returns:
            Base64-encoded signature.
        """
        signature_bytes = sign_json(self.private_key, data)
        return signature_to_base64(signature_bytes)

    def list_capabilities(self) -> List[str]:
        """
        List all capabilities available to this agent.

        Returns:
            List of capability names.
        """
        capabilities = set()

        # From capability tokens
        for token in self._capability_tokens.values():
            if token.is_valid():
                capabilities.add(token.capability)

        # From delegation tokens
        for token in self._delegation_tokens.values():
            if token.is_valid():
                capabilities.add(token.capability)

        return sorted(list(capabilities))
