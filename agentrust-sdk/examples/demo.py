#!/usr/bin/env python3
"""
Agentrust SDK Demo Script

This script demonstrates the complete flow of:
1. Agent registration (simulated - using backend API)
2. Wallet initialization
3. Challenge-response authentication
4. Protected resource execution
5. Capability delegation with attenuation
6. Cross-agent operation using delegation
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentrust import (
    AgentWallet,
    AgentClient,
    FeishuClient,
    AuthenticationError,
    PermissionDeniedError,
)


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def main():
    """Run the demo."""
    base_url = "http://localhost:8000/api/v1"

    print_section("Agentrust SDK Demo")

    # In a real scenario, the agent would:
    # 1. Generate a key pair
    # 2. Register with the CA (POST /ca/register)
    # 3. Receive certificate and capability tokens
    # 4. Store private key securely
    #
    # For this demo, we assume the wallet is already set up
    # and the agent has valid certificates and tokens.

    print("\nNote: This demo shows how to use the SDK after initial registration.")
    print("In production, you would:")
    print("  1. Generate ECDSA P-256 key pair")
    print("  2. Call POST /ca/register with your public key")
    print("  3. Store the private key securely")
    print("  4. Load certificate and tokens into wallet")

    # Demo: Create a wallet (this would be pre-configured in production)
    print_section("Step 1: Initialize Wallet")

    # Example: Load from a pre-existing PEM file
    # In production, you would have generated this key earlier
    print("Creating AgentWallet (demo mode - no actual key file)...")

    try:
        # This is just for demonstration - in real usage you'd have a key file
        wallet = AgentWallet(private_key_pem="-----BEGIN EC PRIVATE KEY-----\nMHQCAQEEIFxxxxxxxxxxxxxxx\n-----END EC PRIVATE KEY-----\n")
    except ValueError as e:
        print(f"Expected error (no valid key): {e}")
        print("In production, you would use a valid key file.")

    print("\nWallet created (demo mode)")
    print("  - Manages private key (never exposed)")
    print("  - Stores certificates and tokens")
    print("  - Provides signing capabilities")

    # Demo: Create client
    print_section("Step 2: Create Agent Client")
    print(f"Connecting to: {base_url}")
    print("Creating client with wallet...")

    # Create a demo wallet for illustration
    # Note: This won't work without a real key and tokens
    class DemoWallet:
        def __init__(self):
            self.agent_id = "agent-demo-001"
            self._session_token = None

        @property
        def is_authenticated(self):
            return self._session_token is not None

        def get_certificate(self):
            class Cert:
                cert_id = "cert-demo-001"
                is_valid = lambda: True
            return Cert()

        def get_capability_token(self, action):
            class Token:
                token_id = "cap-demo-001"
                capability = action
            return Token()

    print("Client created (demo mode)")
    print("  - Base URL:", base_url)
    print("  - Wallet: configured")
    print("  - Timeout: 30s")

    # Demo: Authentication flow
    print_section("Step 3: Authentication Flow")
    print("In production, authentication uses challenge-response:")
    print("  1. Client requests challenge (nonce) from server")
    print("  2. Client signs nonce with private key (in wallet)")
    print("  3. Server verifies signature using certificate public key")
    print("  4. Server issues session token (15 min validity)")
    print("")
    print("Code example:")
    print("""
    client = AgentClient(base_url, wallet)
    client.authenticate("agent-analyst", "cert-001")
    print(client.session_token)  # 'sess-xxx.xxx.xxx'
    """)

    # Demo: Execute operations
    print_section("Step 4: Execute Protected Operations")
    print("The SDK automatically builds the token chain:")
    print("  [Certificate] → [Capability Token] → [Delegation Tokens]")
    print("")
    print("Code example:")
    print("""
    # Read database (direct capability)
    result = client.execute(
        action="read_database",
        resource="user_table",
        params={"filter": "active"}
    )
    print(result["data"])

    # Read bitable (Feishu)
    feishu = FeishuClient(client)
    records = feishu.read_bitable(
        app_token="app_xxx",
        table_id="tbl_xxx",
        fields=["name", "email"],
        page_size=50
    )
    """)

    # Demo: Delegation
    print_section("Step 5: Capability Delegation")
    print("Delegation allows one agent to grant part of its capability to another.")
    print("Key features:")
    print("  - Attenuation: Restrict rows_limit, fields, time_window")
    print("  - Depth limit: Control how far the delegation can propagate")
    print("  - Expiry: Set validity period")
    print("")
    print("Code example:")
    print("""
    # Analyst delegates read_database to Reporter
    # with row and field restrictions
    delegation = client.delegate(
        to_agent_id="agent-reporter",
        capability="read_database",
        resource_scope="user_table",
        attenuations={
            "rows_limit": 100,
            "fields": ["name", "email"]
        },
        max_depth=1,  # Reporter cannot further delegate
        validity_minutes=60
    )
    print(f"Delegation ID: {delegation['delegation_token']['delegation_id']}")
    """)

    # Demo: Cross-agent operation
    print_section("Step 6: Cross-Agent Operation")
    print("Agent B uses delegation from Agent A:")
    print("")
    print("Code example (on Agent B's side):")
    print("""
    # Agent B receives delegation from A
    wallet.add_delegation_token(delegation['delegation_token'])

    # Agent B executes operation
    # SDK automatically builds chain:
    # [A's Certificate] → [A's Capability] → [A→B Delegation]
    result = client.execute("read_database", "user_table")

    # Result is attenuated:
    # - Only 100 rows max
    # - Only name and email fields returned
    """)

    # Demo: Error handling
    print_section("Step 7: Error Handling")
    print("""
    from agentrust import (
        AuthenticationError,
        PermissionDeniedError,
        TokenExpiredError,
        DelegationChainError,
    )

    try:
        client.authenticate("agent-analyst", "cert-001")
        result = client.execute("read_database", "user_table")
    except AuthenticationError:
        print("Authentication failed - check credentials")
    except PermissionDeniedError as e:
        print(f"Permission denied: {e.message}")
        print(f"Details: {e.details}")
    except TokenExpiredError:
        print("Session expired - re-authenticate")
    except DelegationChainError as e:
        print(f"Delegation chain invalid: {e.message}")
    """)

    # Summary
    print_section("Demo Complete")
    print("""
SDK Features Summary:
✓ AgentWallet - Secure key and token management
✓ AgentClient - HTTP client with auto token-chain assembly
✓ FeishuClient - High-level Feishu API wrappers
✓ Exception handling - Clear error types
✓ Type annotations - Full IDE support

Next Steps:
1. Run the backend: cd backend && uvicorn main:app
2. Register an agent via POST /api/v1/ca/register
3. Use SDK to authenticate and execute operations
4. Try delegation between agents
    """)


if __name__ == "__main__":
    main()
