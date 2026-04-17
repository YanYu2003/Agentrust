"""
Integration Test 2: Delegation authorization -> Delegatee operation -> Permission attenuation

This test verifies:
1. Analyst delegates read_database capability to Reporter
2. Reporter uses the delegated token to perform operation
3. Attenuation parameters are correctly applied

GIVEN:
  - Agent "Analyst" is registered with read_database capability (scope: *, attenuations: {})
  - Agent "Reporter" is registered without read_database capability

WHEN:
  1. Analyst delegates to Reporter with attenuations
  2. Reporter authenticates
  3. Reporter executes with delegation token

THEN:
  - Step 1: Returns 201, delegation_token.current_depth == 1
  - Step 3: Returns 200 with effective_attenuations applied
"""

import base64
import pytest
import pytest_asyncio
from app.crypto.keys import generate_agent_keypair, load_private_key_pem
from app.crypto.signature import sign_data


class TestIntegration2:
    """Integration Test 2: Delegation -> Attenuation"""

    @pytest.mark.asyncio
    async def test_delegation_with_attenuation(self, client):
        """Test delegation flow with permission attenuation."""
        # Step 1: Register Analyst
        analyst_private, analyst_public = generate_agent_keypair()
        analyst_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "analyst-002",
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
        analyst_cap_token_id = analyst_data["capability_tokens"][0]["token_id"]

        # Register Reporter
        reporter_private, reporter_public = generate_agent_keypair()
        reporter_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "reporter-002",
                "public_key": reporter_public.decode(),
                "owner": "user-002",
                "requested_capabilities": ["send_message"],  # Any capability that doesn't interfere
                "trust_level": 2,
            },
        )
        assert reporter_response.status_code == 201
        reporter_data = reporter_response.json()
        reporter_id = reporter_data["agent_id"]

        # Authenticate Analyst
        analyst_challenge = await client.post(
            "/api/v1/ca/auth/challenge",
            json={"agent_id": analyst_id, "cert_id": analyst_cert_id},
        )
        assert analyst_challenge.status_code == 200
        challenge_data = analyst_challenge.json()

        signature = sign_data(load_private_key_pem(analyst_private), challenge_data["nonce"].encode())
        analyst_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": challenge_data["challenge_id"],
                "agent_id": analyst_id,
                "signed_nonce": base64.b64encode(signature).decode(),
            },
        )
        assert analyst_verify.status_code == 200
        analyst_session = analyst_verify.json()["session_token"]

        # Step 2: Analyst delegates to Reporter with attenuations
        delegation_response = await client.post(
            "/api/v1/delegate",
            headers={"Authorization": f"Bearer {analyst_session}"},
            json={
                "to_agent_id": reporter_id,
                "parent_token_id": analyst_cap_token_id,
                "parent_token_type": "capability",
                "capability": "read_database",
                "resource_scope": "user_table",
                "attenuations": {"rows_limit": 50, "fields": ["name", "email"]},
                "max_depth": 2,
                "validity_minutes": 30,
            },
        )

        assert delegation_response.status_code == 200, f"Delegation failed: {delegation_response.text}"
        delegation_data = delegation_response.json()
        delegation_token = delegation_data["delegation_token"]
        assert delegation_token["current_depth"] == 1  # max_depth 2 -> current_depth 1
        assert delegation_token["attenuations"]["rows_limit"] == 50
        assert delegation_token["attenuations"]["fields"] == ["name", "email"]

        # Authenticate Reporter
        reporter_challenge = await client.post(
            "/api/v1/ca/auth/challenge",
            json={"agent_id": reporter_id, "cert_id": reporter_data["certificate"]["cert_id"]},
        )
        assert reporter_challenge.status_code == 200

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
        assert reporter_verify.status_code == 200
        reporter_session = reporter_verify.json()["session_token"]

        # Step 3: Reporter executes with delegation token
        execute_response = await client.post(
            "/api/v1/resources/execute",
            headers={"Authorization": f"Bearer {reporter_session}"},
            json={
                "action": "read_database",
                "resource": "user_table",
                "token_chain": [
                    {"token_id": analyst_cert_id, "token_type": "certificate"},
                    {"token_id": analyst_cap_token_id, "token_type": "capability"},
                    {"token_id": delegation_token["delegation_id"], "token_type": "delegation"},
                ],
            },
        )

        assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"
        execute_data = execute_response.json()

        # Verify attenuation was applied
        assert execute_data["verification"]["effective_attenuations"]["rows_limit"] == 50
        assert execute_data["verification"]["effective_attenuations"]["fields"] == ["name", "email"]
        assert execute_data["verification"]["delegation_path"] == "analyst-002 -> reporter-002"
        assert execute_data["verification"]["chain_length"] == 3
