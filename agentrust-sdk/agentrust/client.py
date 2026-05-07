"""
AgentClient - HTTP client for Agentrust API.

Provides methods for:
- authenticate(): Complete challenge-response authentication
- execute(): Execute protected operations with automatic token chain assembly
- delegate(): Create delegation tokens with local signing
"""

import json
import time
from typing import Dict, List, Optional, Any

import httpx

from .wallet import AgentWallet, DelegationToken
from .exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    TokenExpiredError,
    DelegationChainError,
    CertificateRevokedError,
    InvalidRequestError,
    NetworkError,
)


class AgentClient:
    """
    Client for interacting with the Agentrust API.

    This client manages:
    - Session tokens (obtained via challenge-response)
    - Automatic token chain assembly
    - Delegation token creation with local signing

    Usage:
        wallet = AgentWallet("./keys/agent_private.pem")
        client = AgentClient("http://localhost:8000/api/v1", wallet)

        # Authenticate
        client.authenticate("agent-analyst", "cert-001")

        # Execute operations
        result = client.execute("read_database", "user_table")

        # Delegate capability
        delegation = client.delegate("agent-reporter", "read_database", "user_table")
    """

    def __init__(
        self,
        base_url: str,
        wallet: AgentWallet,
        timeout: float = 30.0,
    ):
        """
        Initialize the client.

        Args:
            base_url: Base URL of the Agentrust API (e.g., "http://localhost:8000/api/v1").
            wallet: AgentWallet instance containing private key and tokens.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.wallet = wallet
        self.timeout = timeout

        self._session_token: Optional[str] = None
        self._session_expires_at: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        """Check if client has a valid session token."""
        if not self._session_token:
            return False

        # Check expiry
        if self._session_expires_at:
            try:
                from datetime import datetime
                expiry = datetime.fromisoformat(self._session_expires_at.replace("Z", "+00:00"))
                if datetime.utcnow() >= expiry.replace(tzinfo=None):
                    self._session_token = None
                    return False
            except (ValueError, AttributeError):
                return False

        return True

    def _make_request(
        self,
        method: str,
        path: str,
        data: Dict[str, Any] = None,
        auth: bool = False,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method.
            path: API path (relative to base_url).
            data: Request body data.
            auth: Whether to include session token in Authorization header.

        Returns:
            Response JSON data.

        Raises:
            NetworkError: If request fails.
            AuthenticationError: If authentication fails.
            PermissionDeniedError: If permission is denied.
            TokenExpiredError: If session/token is expired.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Content-Type": "application/json"}

        if auth:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated. Call authenticate() first.")
            headers["Authorization"] = f"Bearer {self._session_token}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                if method.upper() == "GET":
                    response = client.get(url, headers=headers, params=data)
                elif method.upper() == "POST":
                    response = client.post(url, headers=headers, json=data)
                elif method.upper() == "PUT":
                    response = client.put(url, headers=headers, json=data)
                elif method.upper() == "DELETE":
                    response = client.delete(url, headers=headers, json=data)
                else:
                    raise InvalidRequestError(f"Unsupported HTTP method: {method}")

                return self._handle_response(response)

        except httpx.TimeoutException:
            raise NetworkError(f"Request timeout: {url}")
        except httpx.ConnectError as e:
            raise NetworkError(f"Connection failed: {e}")

    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """
        Handle HTTP response and convert errors to exceptions.

        Args:
            response: httpx Response object.

        Returns:
            Response JSON data.

        Raises:
            Various exceptions based on status code.
        """
        if response.status_code == 200 or response.status_code == 201:
            return response.json()

        # Parse error response
        error_detail = None
        try:
            error_data = response.json()
            if "detail" in error_data:
                detail = error_data["detail"]
                if isinstance(detail, dict):
                    error_detail = detail.get("error", {})
                else:
                    error_detail = {"message": str(detail)}
        except (ValueError, json.JSONDecodeError):
            error_detail = {"message": response.text or "Unknown error"}

        code = error_detail.get("code", "UNKNOWN") if error_detail else "UNKNOWN"
        message = error_detail.get("message", "Unknown error") if error_detail else "Unknown error"

        # Map status codes to exceptions
        if response.status_code == 401:
            if code in ("AUTH_EXPIRED", "AUTH_REQUIRED"):
                raise TokenExpiredError(message, error_detail)
            raise AuthenticationError(message, error_detail)

        elif response.status_code == 403:
            if code == "CERTIFICATE_REVOKED":
                raise CertificateRevokedError(message, error_detail)
            elif code == "TOKEN_EXPIRED":
                raise TokenExpiredError(message, error_detail)
            elif code in ("PERMISSION_DENIED", "AGENT_SUSPENDED"):
                raise PermissionDeniedError(message, error_detail)
            elif code == "DELEGATION_CHAIN_INVALID":
                raise DelegationChainError(message, error_detail)
            raise PermissionDeniedError(message, error_detail)

        elif response.status_code == 404:
            raise InvalidRequestError(f"Resource not found: {message}", error_detail)

        elif response.status_code >= 400:
            raise InvalidRequestError(message, error_detail)

        raise NetworkError(f"Unexpected response: {response.status_code}", error_detail)

    def authenticate(self, agent_id: str, cert_id: str) -> str:
        """
        Authenticate using challenge-response flow.

        This method:
        1. Requests a challenge (nonce) from the server
        2. Signs the nonce with the wallet's private key
        3. Submits the signature to obtain a session token

        Args:
            agent_id: The agent's ID.
            cert_id: The certificate ID to use for authentication.

        Returns:
            Session token string.

        Raises:
            AuthenticationError: If authentication fails.
        """
        # Step 1: Get challenge
        challenge_data = self._make_request(
            "POST",
            "/ca/auth/challenge",
            data={"agent_id": agent_id, "cert_id": cert_id},
        )

        nonce = challenge_data["nonce"]
        challenge_id = challenge_data["challenge_id"]
        expires_at = challenge_data["expires_at"]

        # Step 2: Sign nonce with private key
        # The nonce is signed directly as bytes
        from .crypto import sign_data, signature_to_base64, load_private_key
        private_key = self.wallet.private_key
        signature_bytes = sign_data(private_key, nonce.encode("utf-8"))
        signed_nonce = signature_to_base64(signature_bytes)

        # Step 3: Verify signature and get session token
        verify_data = self._make_request(
            "POST",
            "/ca/auth/verify",
            data={
                "challenge_id": challenge_id,
                "agent_id": agent_id,
                "signed_nonce": signed_nonce,
            },
        )

        self._session_token = verify_data["session_token"]
        self._session_expires_at = verify_data["expires_at"]

        return self._session_token

    def _build_token_chain(
        self,
        action: str,
        delegation_chain: List[Dict[str, str]] = None,
    ) -> List[Dict[str, str]]:
        """
        Build a token chain for an operation.

        The chain consists of:
        1. Certificate (from wallet)
        2. Capability token (from wallet or delegation)
        3. Optional delegation tokens

        Args:
            action: The action to perform.
            delegation_chain: Optional list of delegation tokens to include.

        Returns:
            List of token chain items.

        Raises:
            PermissionDeniedError: If required token is not found.
        """
        chain = []

        # Get certificate
        cert = self.wallet.get_certificate()
        if not cert:
            raise PermissionDeniedError("No valid certificate found in wallet")
        chain.append({"token_id": cert.cert_id, "token_type": "certificate"})

        # Look for capability token (first check capability tokens, then delegation tokens)
        cap_token = self.wallet.get_capability_token(action)

        if cap_token:
            chain.append({"token_id": cap_token.token_id, "token_type": "capability"})
        else:
            # Check delegation tokens for this capability
            del_tokens = self.wallet.get_delegation_tokens_for_capability(action)
            if not del_tokens:
                raise PermissionDeniedError(f"No token found for capability: {action}")

            # Use the first valid delegation token
            # For proper selection, we'd need to match resource scope too
            del_token = del_tokens[0]

            # Need to include the original capability token from the delegator
            # In a real scenario, we'd track which capability token was used in delegation
            # For now, we'll construct the chain assuming delegation
            chain.append({"token_id": del_token.delegation_id, "token_type": "delegation"})

        # Add additional delegation tokens if provided
        if delegation_chain:
            for del_data in delegation_chain:
                chain.append({
                    "token_id": del_data["delegation_id"],
                    "token_type": "delegation",
                })

        return chain

    def execute(
        self,
        action: str,
        resource: str,
        params: Dict[str, Any] = None,
        delegation_chain: List[Dict[str, str]] = None,
        task_id: str = None,
        parent_agent_id: str = None,
        task_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a protected operation.

        This method automatically builds the token chain from the wallet.

        Args:
            action: Action to perform (e.g., "read_database").
            resource: Resource identifier (e.g., "user_table").
            params: Optional operation parameters.
            delegation_chain: Optional list of delegation tokens to include.
            task_id: Optional task correlation ID for audit tracing.
            parent_agent_id: Optional upstream agent ID for audit tracing.
            task_context: Optional client metadata merged into audit task_context.

        Returns:
            Operation result data.

        Raises:
            AuthenticationError: If not authenticated.
            PermissionDeniedError: If permission denied.
            TokenExpiredError: If token expired.
        """
        token_chain = self._build_token_chain(action, delegation_chain)

        data: Dict[str, Any] = {
            "action": action,
            "resource": resource,
            "params": params or {},
            "token_chain": token_chain,
        }
        if task_id is not None:
            data["task_id"] = task_id
        if parent_agent_id is not None:
            data["parent_agent_id"] = parent_agent_id
        if task_context is not None:
            data["task_context"] = task_context

        return self._make_request(
            "POST",
            "/resources/execute",
            data=data,
            auth=True,
        )

    def delegate(
        self,
        to_agent_id: str,
        capability: str,
        resource_scope: str,
        attenuations: Dict[str, Any] = None,
        max_depth: int = 1,
        validity_minutes: int = 60,
        parent_token_id: str = None,
        parent_token_type: str = "capability",
    ) -> Dict[str, Any]:
        """
        Create a delegation token.

        This method creates a delegation payload, signs it locally,
        and submits it to the server.

        Args:
            to_agent_id: Target agent ID to delegate to.
            capability: Capability to delegate.
            resource_scope: Resource scope for the delegation.
            attenuations: Attenuation parameters.
            max_depth: Maximum delegation depth.
            validity_minutes: Token validity in minutes.
            parent_token_id: Parent token ID (from wallet if not specified).
            parent_token_type: Parent token type ("capability" or "delegation").

        Returns:
            Delegation token data.

        Raises:
            AuthenticationError: If not authenticated.
            PermissionDeniedError: If delegation not allowed.
        """
        # Get parent token from wallet if not specified
        if not parent_token_id:
            cap_token = self.wallet.get_capability_token(capability)
            if not cap_token:
                raise PermissionDeniedError(f"No capability token found for: {capability}")
            parent_token_id = cap_token.token_id

        # Build delegation payload
        now = time.time()
        payload = {
            "to_agent_id": to_agent_id,
            "parent_token_id": parent_token_id,
            "parent_token_type": parent_token_type,
            "capability": capability,
            "resource_scope": resource_scope,
            "attenuations": attenuations or {},
            "max_depth": max_depth,
            "validity_minutes": validity_minutes,
        }

        # Sign the payload locally (private key never leaves wallet)
        from .crypto import canonical_json, sign_json, signature_to_base64
        private_key = self.wallet.private_key
        signature_bytes = sign_json(private_key, payload)
        signature = signature_to_base64(signature_bytes)

        # Add signature to payload
        payload["from_signature"] = signature

        # Submit delegation request
        result = self._make_request(
            "POST",
            "/delegate",
            data=payload,
            auth=True,
        )

        # Store delegation token in wallet
        if "delegation_token" in result:
            self.wallet.add_delegation_token(result["delegation_token"])

        return result

    def revoke_certificate(self, cert_id: str, reason: str) -> Dict[str, Any]:
        """
        Revoke a certificate.

        Requires manage_agents capability.

        Args:
            cert_id: Certificate ID to revoke.
            reason: Reason for revocation.

        Returns:
            Revocation confirmation data.
        """
        return self._make_request(
            "POST",
            "/ca/revoke",
            data={"cert_id": cert_id, "reason": reason},
            auth=True,
        )

    def get_agent_tokens(self, agent_id: str = None) -> Dict[str, Any]:
        """
        Get tokens for an agent.

        Args:
            agent_id: Agent ID to query (default: own agent).

        Returns:
            Token information.
        """
        target_id = agent_id or self.wallet.agent_id
        if not target_id:
            raise InvalidRequestError("No agent_id specified and wallet has no agent_id")

        return self._make_request(
            "GET",
            f"/agents/{target_id}/tokens",
            auth=True,
        )
