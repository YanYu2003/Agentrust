"""
Integration Test 4: Multi-level delegation chain -> Permission attenuation -> Depth exhaustion

This test verifies:
1. Agent A delegates to B with max_depth=2
2. B further delegates to C with additional attenuation
3. C performs operation with accumulated attenuation
4. C tries to delegate but depth is exhausted

GIVEN:
  - Agent A (Analyst): has read_database capability, scope *, attenuations {}
  - Agent B (Reporter): no initial capability
  - Agent C (Runner): no initial capability

WHEN:
  1. A delegates to B: rows_limit=100, max_depth=2 -> current_depth=1
  2. B delegates to C: rows_limit=50, max_depth=1 -> current_depth=0
  3. C executes with token chain [A_cert, A_cap, del_A->B, del_B->C]
  4. C tries to delegate to D

THEN:
  - Step 2: B->C attenuations.rows_limit == 50 (stricter than A->B's 100)
  - Step 3: effective_attenuations.rows_limit == 50, delegation_path == "A -> B -> C"
  - Step 4: Returns 400 INVALID_DELEGATION_DEPTH
"""

import base64
import pytest
import pytest_asyncio
from app.crypto.keys import generate_agent_keypair, load_private_key_pem
from app.crypto.signature import sign_data


class TestIntegration4:
    """Integration Test 4: Multi-level delegation chain"""

    @pytest.mark.asyncio
    async def test_multi_level_delegation(self, client):
        """Test multi-level delegation with accumulated attenuation."""
        # Register Agent A (Analyst)
        a_private, a_public = generate_agent_keypair()
        a_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "analyst-004",
                "public_key": a_public.decode(),
                "owner": "user-001",
                "requested_capabilities": ["read_database"],
                "trust_level": 4,
            },
        )
        assert a_response.status_code == 201
        a_data = a_response.json()
        a_id = a_data["agent_id"]
        a_cert_id = a_data["certificate"]["cert_id"]
        a_cap_id = a_data["capability_tokens"][0]["token_id"]

        # Register Agent B (Reporter)
        b_private, b_public = generate_agent_keypair()
        b_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "reporter-004",
                "public_key": b_public.decode(),
                "owner": "user-002",
                "requested_capabilities": ["send_message"],
                "trust_level": 3,
            },
        )
        assert b_response.status_code == 201
        b_data = b_response.json()
        b_id = b_data["agent_id"]
        b_cert_id = b_data["certificate"]["cert_id"]

        # Register Agent C (Runner)
        c_private, c_public = generate_agent_keypair()
        c_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "runner-004",
                "public_key": c_public.decode(),
                "owner": "user-003",
                "requested_capabilities": ["send_message"],
                "trust_level": 2,
            },
        )
        assert c_response.status_code == 201
        c_data = c_response.json()
        c_id = c_data["agent_id"]
        c_cert_id = c_data["certificate"]["cert_id"]

        # Authenticate A
        a_challenge = await client.post(
            "/api/v1/ca/auth/challenge", json={"agent_id": a_id, "cert_id": a_cert_id}
        )
        a_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": a_challenge.json()["challenge_id"],
                "agent_id": a_id,
                "signed_nonce": base64.b64encode(
                    sign_data(load_private_key_pem(a_private), a_challenge.json()["nonce"].encode())
                ).decode(),
            },
        )
        assert a_verify.status_code == 200
        a_session = a_verify.json()["session_token"]

        # Step 1: A delegates to B with max_depth=2
        delegation_a_to_b = await client.post(
            "/api/v1/delegate",
            headers={"Authorization": f"Bearer {a_session}"},
            json={
                "to_agent_id": b_id,
                "parent_token_id": a_cap_id,
                "parent_token_type": "capability",
                "capability": "read_database",
                "resource_scope": "user_table",
                "attenuations": {"rows_limit": 100},
                "max_depth": 2,
                "validity_minutes": 60,
            },
        )
        assert delegation_a_to_b.status_code == 200
        del_a_to_b = delegation_a_to_b.json()["delegation_token"]
        assert del_a_to_b["current_depth"] == 1  # max_depth=2, so current_depth=1

        # Authenticate B
        b_challenge = await client.post(
            "/api/v1/ca/auth/challenge", json={"agent_id": b_id, "cert_id": b_cert_id}
        )
        b_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": b_challenge.json()["challenge_id"],
                "agent_id": b_id,
                "signed_nonce": base64.b64encode(
                    sign_data(load_private_key_pem(b_private), b_challenge.json()["nonce"].encode())
                ).decode(),
            },
        )
        b_session = b_verify.json()["session_token"]

        # Step 2: B delegates to C with stricter attenuation
        delegation_b_to_c = await client.post(
            "/api/v1/delegate",
            headers={"Authorization": f"Bearer {b_session}"},
            json={
                "to_agent_id": c_id,
                "parent_token_id": del_a_to_b["delegation_id"],
                "parent_token_type": "delegation",
                "capability": "read_database",
                "resource_scope": "user_table",
                "attenuations": {"rows_limit": 50},  # Stricter than 100
                "max_depth": 1,
                "validity_minutes": 30,
            },
        )
        assert delegation_b_to_c.status_code == 200
        del_b_to_c = delegation_b_to_c.json()["delegation_token"]
        assert del_b_to_c["current_depth"] == 0  # max_depth=1, so current_depth=0
        assert del_b_to_c["attenuations"]["rows_limit"] == 50

        # Authenticate C
        c_challenge = await client.post(
            "/api/v1/ca/auth/challenge", json={"agent_id": c_id, "cert_id": c_cert_id}
        )
        c_verify = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": c_challenge.json()["challenge_id"],
                "agent_id": c_id,
                "signed_nonce": base64.b64encode(
                    sign_data(load_private_key_pem(c_private), c_challenge.json()["nonce"].encode())
                ).decode(),
            },
        )
        c_session = c_verify.json()["session_token"]

        # Step 3: C executes with accumulated attenuation
        execute_response = await client.post(
            "/api/v1/resources/execute",
            headers={"Authorization": f"Bearer {c_session}"},
            json={
                "action": "read_database",
                "resource": "user_table",
                "token_chain": [
                    {"token_id": a_cert_id, "token_type": "certificate"},
                    {"token_id": a_cap_id, "token_type": "capability"},
                    {"token_id": del_a_to_b["delegation_id"], "token_type": "delegation"},
                    {"token_id": del_b_to_c["delegation_id"], "token_type": "delegation"},
                ],
            },
        )
        assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"
        execute_data = execute_response.json()
        assert execute_data["verification"]["effective_attenuations"]["rows_limit"] == 50
        assert execute_data["verification"]["delegation_path"] == "analyst-004 -> reporter-004 -> runner-004"
        assert execute_data["verification"]["chain_length"] == 4

        # Step 4: C tries to delegate but depth is exhausted
        register_d_private, register_d_public = generate_agent_keypair()
        d_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "runner-004-d",
                "public_key": register_d_public.decode(),
                "owner": "user-004",
                "requested_capabilities": ["send_message"],
                "trust_level": 2,
            },
        )
        assert d_response.status_code == 201
        d_id = d_response.json()["agent_id"]

        # C tries to delegate to D but current_depth=0
        try_delegate_response = await client.post(
            "/api/v1/delegate",
            headers={"Authorization": f"Bearer {c_session}"},
            json={
                "to_agent_id": d_id,
                "parent_token_id": del_b_to_c["delegation_id"],
                "parent_token_type": "delegation",
                "capability": "read_database",
                "resource_scope": "user_table",
                "max_depth": 1,
                "validity_minutes": 30,
            },
        )

        assert try_delegate_response.status_code == 400
        assert try_delegate_response.json()["detail"]["error"]["code"] == "INVALID_DELEGATION_DEPTH"
