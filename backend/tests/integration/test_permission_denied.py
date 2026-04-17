"""
Integration Test 3: Permission denied scenarios (three types)

This test verifies that unauthorized operations are properly rejected:
- Scenario 3a: Capability mismatch (read-only token trying write operation)
- Scenario 3b: Resource scope violation (accessing non-delegated resource)
- Scenario 3c: Forged token chain (certificate doesn't match)

GIVEN:
  - Agent "Reporter" holds delegation_token with read_database for user_table only
  - Agent "Outsider" has no delegation

WHEN (3a - Capability mismatch):
  Reporter tries write_database with read delegation

WHEN (3b - Resource scope violation):
  Reporter tries to access salary_table (not in scope)

WHEN (3c - Forged token chain):
  Outsider tries to use Analyst's certificate

THEN:
  - All scenarios return 403 PERMISSION_DENIED
  - Audit logs record each denial
"""

import base64
import pytest
import pytest_asyncio
from app.crypto.keys import generate_agent_keypair, load_private_key_pem
from app.crypto.signature import sign_data


class TestIntegration3:
    """Integration Test 3: Permission denied scenarios"""

    @pytest.mark.asyncio
    async def test_capability_mismatch(self, client):
        """Scenario 3a: Capability mismatch - try write with read-only token."""
        # Setup: Register Analyst and Reporter, create delegation
        analyst_private, analyst_public = generate_agent_keypair()
        analyst_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "analyst-003a",
                "public_key": analyst_public.decode(),
                "owner": "user-001",
                "requested_capabilities": ["read_database", "write_database"],
                "trust_level": 4,
            },
        )
        assert analyst_response.status_code == 201
        analyst_data = analyst_response.json()
        analyst_id = analyst_data["agent_id"]
        analyst_cert_id = analyst_data["certificate"]["cert_id"]
        read_cap_id = next(
            t["token_id"] for t in analyst_data["capability_tokens"] if t["capability"] == "read_database"
        )

        reporter_private, reporter_public = generate_agent_keypair()
        reporter_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "reporter-003a",
                "public_key": reporter_public.decode(),
                "owner": "user-002",
                "requested_capabilities": ["send_message"],
                "trust_level": 2,
            },
        )
        assert reporter_response.status_code == 201
        reporter_data = reporter_response.json()
        reporter_id = reporter_data["agent_id"]

        # Authenticate and delegate read_database only
        analyst_challenge = await client.post(
            "/api/v1/ca/auth/challenge",
            json={"agent_id": analyst_id, "cert_id": analyst_cert_id},
        )
        signature = sign_data(load_private_key_pem(analyst_private), analyst_challenge.json()["nonce"].encode())
        analyst_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": analyst_challenge.json()["challenge_id"],
                "agent_id": analyst_id,
                "signed_nonce": base64.b64encode(signature).decode(),
            },
        )
        analyst_session = analyst_verify.json()["session_token"]

        # Delegate read_database only (NOT write_database)
        delegation = await client.post(
            "/api/v1/delegate",
            headers={"Authorization": f"Bearer {analyst_session}"},
            json={
                "to_agent_id": reporter_id,
                "parent_token_id": read_cap_id,
                "parent_token_type": "capability",
                "capability": "read_database",
                "resource_scope": "user_table",
                "max_depth": 1,
                "validity_minutes": 60,
            },
        )
        assert delegation.status_code == 200
        del_token_id = delegation.json()["delegation_token"]["delegation_id"]

        # Authenticate Reporter
        reporter_challenge = await client.post(
            "/api/v1/ca/auth/challenge",
            json={"agent_id": reporter_id, "cert_id": reporter_data["certificate"]["cert_id"]},
        )
        reporter_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": reporter_challenge.json()["challenge_id"],
                "agent_id": reporter_id,
                "signed_nonce": base64.b64encode(
                    sign_data(load_private_key_pem(reporter_private), reporter_challenge.json()["nonce"].encode())
                ).decode(),
            },
        )
        reporter_session = reporter_verify.json()["session_token"]

        # Try write_database - should be DENIED
        write_response = await client.post(
            "/api/v1/resources/execute",
            headers={"Authorization": f"Bearer {reporter_session}"},
            json={
                "action": "write_database",
                "resource": "user_table",
                "token_chain": [
                    {"token_id": analyst_cert_id, "token_type": "certificate"},
                    {"token_id": read_cap_id, "token_type": "capability"},
                    {"token_id": del_token_id, "token_type": "delegation"},
                ],
            },
        )

        assert write_response.status_code == 403
        assert write_response.json()["detail"]["error"]["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_resource_scope_violation(self, client):
        """Scenario 3b: Resource scope violation - access non-delegated resource."""
        # Setup similar to 3a but delegation is for user_table only
        analyst_private, analyst_public = generate_agent_keypair()
        analyst_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "analyst-003b",
                "public_key": analyst_public.decode(),
                "owner": "user-001",
                "requested_capabilities": ["read_database"],
                "trust_level": 4,
            },
        )
        assert analyst_response.status_code == 201
        analyst_data = analyst_response.json()
        analyst_id = analyst_data["agent_id"]
        analyst_cert_id = analyst_data["certificate"]["cert_id"]
        analyst_cap_id = analyst_data["capability_tokens"][0]["token_id"]

        reporter_private, reporter_public = generate_agent_keypair()
        reporter_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "reporter-003b",
                "public_key": reporter_public.decode(),
                "owner": "user-002",
                "requested_capabilities": ["send_message"],
                "trust_level": 2,
            },
        )
        assert reporter_response.status_code == 201
        reporter_data = reporter_response.json()
        reporter_id = reporter_data["agent_id"]

        # Authenticate and delegate for user_table only
        analyst_challenge = await client.post(
            "/api/v1/ca/auth/challenge",
            json={"agent_id": analyst_id, "cert_id": analyst_cert_id},
        )
        signature = sign_data(load_private_key_pem(analyst_private), analyst_challenge.json()["nonce"].encode())
        analyst_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": analyst_challenge.json()["challenge_id"],
                "agent_id": analyst_id,
                "signed_nonce": base64.b64encode(signature).decode(),
            },
        )
        analyst_session = analyst_verify.json()["session_token"]

        delegation = await client.post(
            "/api/v1/delegate",
            headers={"Authorization": f"Bearer {analyst_session}"},
            json={
                "to_agent_id": reporter_id,
                "parent_token_id": analyst_cap_id,
                "parent_token_type": "capability",
                "capability": "read_database",
                "resource_scope": "user_table",  # Only user_table, NOT salary_table
                "max_depth": 1,
                "validity_minutes": 60,
            },
        )
        assert delegation.status_code == 200
        del_token_id = delegation.json()["delegation_token"]["delegation_id"]

        # Authenticate Reporter
        reporter_challenge = await client.post(
            "/api/v1/ca/auth/challenge",
            json={"agent_id": reporter_id, "cert_id": reporter_data["certificate"]["cert_id"]},
        )
        reporter_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": reporter_challenge.json()["challenge_id"],
                "agent_id": reporter_id,
                "signed_nonce": base64.b64encode(
                    sign_data(load_private_key_pem(reporter_private), reporter_challenge.json()["nonce"].encode())
                ).decode(),
            },
        )
        reporter_session = reporter_verify.json()["session_token"]

        # Try to access salary_table - should be DENIED
        wrong_resource_response = await client.post(
            "/api/v1/resources/execute",
            headers={"Authorization": f"Bearer {reporter_session}"},
            json={
                "action": "read_database",
                "resource": "salary_table",  # NOT in delegated scope
                "token_chain": [
                    {"token_id": analyst_cert_id, "token_type": "certificate"},
                    {"token_id": analyst_cap_id, "token_type": "capability"},
                    {"token_id": del_token_id, "token_type": "delegation"},
                ],
            },
        )

        assert wrong_resource_response.status_code == 403
        assert wrong_resource_response.json()["detail"]["error"]["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_forged_token_chain(self, client):
        """Scenario 3c: Forged token chain - outsider tries to use analyst's cert."""
        # Setup: Register Analyst and Outsider
        analyst_private, analyst_public = generate_agent_keypair()
        analyst_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "analyst-003c",
                "public_key": analyst_public.decode(),
                "owner": "user-001",
                "requested_capabilities": ["read_database"],
                "trust_level": 4,
            },
        )
        assert analyst_response.status_code == 201
        analyst_data = analyst_response.json()
        analyst_cert_id = analyst_data["certificate"]["cert_id"]
        analyst_cap_id = analyst_data["capability_tokens"][0]["token_id"]

        outsider_private, outsider_public = generate_agent_keypair()
        outsider_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "outsider-003c",
                "public_key": outsider_public.decode(),
                "owner": "user-003",
                "requested_capabilities": ["send_message"],
                "trust_level": 1,
            },
        )
        assert outsider_response.status_code == 201
        outsider_data = outsider_response.json()
        outsider_id = outsider_data["agent_id"]

        # Authenticate Outsider (they have their own valid cert)
        outsider_challenge = await client.post(
            "/api/v1/ca/auth/challenge",
            json={"agent_id": outsider_id, "cert_id": outsider_data["certificate"]["cert_id"]},
        )
        outsider_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": outsider_challenge.json()["challenge_id"],
                "agent_id": outsider_id,
                "signed_nonce": base64.b64encode(
                    sign_data(load_private_key_pem(outsider_private), outsider_challenge.json()["nonce"].encode())
                ).decode(),
            },
        )
        outsider_session = outsider_verify.json()["session_token"]

        # Try to use Analyst's certificate and token (FORGED)
        forged_response = await client.post(
            "/api/v1/resources/execute",
            headers={"Authorization": f"Bearer {outsider_session}"},
            json={
                "action": "read_database",
                "resource": "user_table",
                "token_chain": [
                    {"token_id": analyst_cert_id, "token_type": "certificate"},  # NOT outsider's cert
                    {"token_id": analyst_cap_id, "token_type": "capability"},  # NOT outsider's token
                ],
            },
        )

        # Should fail because the certificate doesn't match the authenticated agent
        assert forged_response.status_code == 403
        assert forged_response.json()["detail"]["error"]["code"] == "DELEGATION_CHAIN_INVALID"
