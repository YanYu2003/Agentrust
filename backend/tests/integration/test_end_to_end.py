"""
Integration Test 1: Complete registration -> Direct operation -> Audit chain

This test verifies the complete flow:
1. Agent registers and gets certificate + capability tokens
2. Agent authenticates via challenge-response
3. Agent performs a direct operation (read_database)
4. Audit log records the operation

GIVEN:
  - System is initialized, CA root key is generated
  - No registered agents exist

WHEN:
  1. Agent "Analyst" calls POST /api/v1/ca/register
  2. Agent completes challenge-response authentication
  3. Agent calls POST /api/v1/resources/execute
  4. Call GET /api/v1/audit/logs

THEN:
  - Step 1: Returns 201 with agent_id, cert_id, capability_token, validity=72h
  - Step 2: Returns 200 with valid session_token
  - Step 3: Returns 200, verification.token_chain_valid == true
  - Step 4: Returns 200 with 1 audit log entry, result == "ALLOWED"
"""

import base64
import pytest
import pytest_asyncio
from app.crypto.keys import generate_agent_keypair, load_private_key_pem


class TestIntegration1:
    """Integration Test 1: Registration -> Direct Operation -> Audit"""

    @pytest.mark.asyncio
    async def test_complete_flow(self, client):
        """Test complete registration -> operation -> audit flow."""
        # Step 1: Register Agent
        private_pem, public_pem = generate_agent_keypair()

        register_response = await client.post(
            "/api/v1/ca/register",
            json={
                "name": "analyst-001",
                "public_key": public_pem.decode(),
                "owner": "user-001",
                "requested_capabilities": ["read_database", "read_bitable"],
                "description": "Data analyst agent",
                "trust_level": 4,
            },
        )

        assert register_response.status_code == 201, f"Registration failed: {register_response.text}"
        register_data = register_response.json()
        assert "agent_id" in register_data
        assert "certificate" in register_data
        assert "capability_tokens" in register_data

        agent_id = register_data["agent_id"]
        cert_id = register_data["certificate"]["cert_id"]
        capability_token_id = register_data["capability_tokens"][0]["token_id"]

        # Verify certificate validity (trust_level 4 = 72 hours)
        from app.utils import parse_iso
        cert_expiry = parse_iso(register_data["certificate"]["expires_at"])
        cert_issued = parse_iso(register_data["certificate"]["issued_at"])
        validity_hours = (cert_expiry - cert_issued).total_seconds() / 3600
        assert validity_hours == 72, f"Expected 72 hours validity, got {validity_hours}"

        # Step 2: Challenge-Response Authentication
        challenge_response = await client.post(
            "/api/v1/ca/auth/challenge",
            json={"agent_id": agent_id, "cert_id": cert_id},
        )

        assert challenge_response.status_code == 200, f"Challenge failed: {challenge_response.text}"
        challenge_data = challenge_response.json()
        assert "challenge_id" in challenge_data
        assert "nonce" in challenge_data

        # Sign the nonce with agent's private key
        from app.crypto.signature import sign_data
        nonce = challenge_data["nonce"].encode()
        private_key = load_private_key_pem(private_pem)
        signature = sign_data(private_key, nonce)
        signature_b64 = base64.b64encode(signature).decode()

        # Verify the challenge
        verify_response = await client.post(
            "/api/v1/ca/auth/verify",
            json={
                "challenge_id": challenge_data["challenge_id"],
                "agent_id": agent_id,
                "signed_nonce": signature_b64,
            },
        )

        assert verify_response.status_code == 200, f"Verify failed: {verify_response.text}"
        verify_data = verify_response.json()
        assert "session_token" in verify_data
        session_token = verify_data["session_token"]

        # Step 3: Execute protected operation (direct - no delegation)
        execute_response = await client.post(
            "/api/v1/resources/execute",
            headers={"Authorization": f"Bearer {session_token}"},
            json={
                "action": "read_database",
                "resource": "user_table",
                "token_chain": [
                    {"token_id": cert_id, "token_type": "certificate"},
                    {"token_id": capability_token_id, "token_type": "capability"},
                ],
            },
        )

        assert execute_response.status_code == 200, f"Execute failed: {execute_response.text}"
        execute_data = execute_response.json()
        assert execute_data["verification"]["token_chain_valid"] is True
        assert execute_data["verification"]["chain_length"] == 2

        # Step 4: Query audit logs
        audit_response = await client.get(
            "/api/v1/audit/logs",
            headers={"Authorization": f"Bearer {session_token}"},
            params={"agent_id": agent_id},
        )

        assert audit_response.status_code == 200, f"Audit query failed: {audit_response.text}"
        audit_data = audit_response.json()
        assert audit_data["total"] >= 1

        # Find our operation in the logs
        our_log = None
        for log in audit_data["logs"]:
            if log["action"] == "read_database" and log["result"] == "ALLOWED":
                our_log = log
                break

        assert our_log is not None, "Our operation not found in audit logs"
        assert our_log["delegation_chain_summary"] == "analyst-001"
