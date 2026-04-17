"""
Tests for Phase 4: Delegation Service and API.
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.services.delegation_service import (
    DelegationService,
    DelegationError,
    TRUST_LEVEL_MAX_DEPTH,
)
from app.schemas.common import ErrorCode

# Import test constants from conftest
from tests.conftest import TEST_CA_KEY_PASSWORD, TEST_SESSION_SECRET


# =============================================================================
# Delegation Service Unit Tests
# =============================================================================

class TestDelegationServiceHelpers:
    """Tests for DelegationService helper methods."""

    def test_is_scope_subset_exact_match(self):
        """Test scope subset with exact match."""
        service = DelegationService(None)
        assert service._is_scope_subset("user_table", "user_table")

    def test_is_scope_subset_wildcard(self):
        """Test scope subset with wildcard parent."""
        service = DelegationService(None)
        assert service._is_scope_subset("user_table", "*")
        assert service._is_scope_subset("any_table", "*")

    def test_is_scope_subset_prefix_wildcard(self):
        """Test scope subset with prefix wildcard."""
        service = DelegationService(None)
        assert service._is_scope_subset("db.users", "db.*")
        assert service._is_scope_subset("db.orders", "db.*")
        assert not service._is_scope_subset("other.users", "db.*")

    def test_is_scope_subset_no_match(self):
        """Test scope subset with no match."""
        service = DelegationService(None)
        assert not service._is_scope_subset("salary_table", "user_table")
        assert not service._is_scope_subset("db.users", "other.*")

    def test_validate_capability_match(self):
        """Test capability validation with matching capability."""
        service = DelegationService(None)
        service._validate_capability("read_database", "read_database")

    def test_validate_capability_mismatch(self):
        """Test capability validation with mismatched capability."""
        service = DelegationService(None)
        with pytest.raises(DelegationError) as exc_info:
            service._validate_capability("write_database", "read_database")
        assert exc_info.value.code == ErrorCode.INVALID_CAPABILITY

    def test_validate_capability_invalid(self):
        """Test capability validation with invalid capability."""
        service = DelegationService(None)
        with pytest.raises(DelegationError) as exc_info:
            service._validate_capability("invalid_capability", "invalid_capability")
        assert exc_info.value.code == ErrorCode.INVALID_CAPABILITY

    def test_validate_resource_scope_valid(self):
        """Test resource scope validation with valid subset."""
        service = DelegationService(None)
        service._validate_resource_scope("user_table", "*")
        service._validate_resource_scope("user_table", "user_table")
        service._validate_resource_scope("db.users", "db.*")

    def test_validate_resource_scope_invalid(self):
        """Test resource scope validation with invalid scope."""
        service = DelegationService(None)
        with pytest.raises(DelegationError) as exc_info:
            service._validate_resource_scope("salary_table", "user_table")
        assert exc_info.value.code == ErrorCode.INVALID_ATTENUATIONS

    def test_validate_expiry_valid(self):
        """Test expiry validation with valid expiry."""
        service = DelegationService(None)
        parent_expiry = (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"
        requested_expiry = datetime.utcnow() + timedelta(hours=1)
        result = service._validate_expiry(requested_expiry, parent_expiry)
        assert result == requested_expiry

    def test_validate_expiry_exceeds_parent(self):
        """Test expiry validation when exceeding parent."""
        service = DelegationService(None)
        parent_expiry = (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z"
        requested_expiry = datetime.utcnow() + timedelta(hours=2)
        with pytest.raises(DelegationError) as exc_info:
            service._validate_expiry(requested_expiry, parent_expiry)
        assert exc_info.value.code == ErrorCode.DELEGATION_EXPIRY_EXCEEDS_PARENT

    def test_trust_level_max_depth(self):
        """Test trust level to max depth mapping."""
        assert TRUST_LEVEL_MAX_DEPTH[1] == 0
        assert TRUST_LEVEL_MAX_DEPTH[2] == 1
        assert TRUST_LEVEL_MAX_DEPTH[3] == 2
        assert TRUST_LEVEL_MAX_DEPTH[4] == 5
        assert TRUST_LEVEL_MAX_DEPTH[5] == 10


# =============================================================================
# Integration Tests (require database)
# =============================================================================

from app.services.ca_service import CAService
from app.services.token_verifier import TokenVerifier
from app.crypto.keys import generate_ecdsa_keypair, public_key_to_pem
from app.config import Settings


def get_test_settings():
    """Get test settings."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        session_secret=TEST_SESSION_SECRET,
        ca_key_password=TEST_CA_KEY_PASSWORD,
    )


@pytest.mark.asyncio
class TestDelegationIntegration:
    """Integration tests for delegation flow."""

    async def test_full_delegation_flow(self, db_session, patched_settings):
        """Test complete delegation flow."""
        ca_service = CAService(db_session)

        private_key_a, public_key_a = generate_ecdsa_keypair()
        private_key_b, public_key_b = generate_ecdsa_keypair()
        # Convert bytes to string for JSON serialization
        public_key_pem_a = public_key_to_pem(public_key_a).decode('utf-8')
        public_key_pem_b = public_key_to_pem(public_key_b).decode('utf-8')

        result_a = await ca_service.register_agent(
            name="analyst-agent",
            public_key_pem=public_key_pem_a,
            owner="user-001",
            requested_capabilities=["read_database"],
            trust_level=4,
        )
        agent_a_id = result_a["agent_id"]
        cap_token_a_id = result_a["capability_tokens"][0]["token_id"]

        result_b = await ca_service.register_agent(
            name="reporter-agent",
            public_key_pem=public_key_pem_b,
            owner="user-002",
            requested_capabilities=[],
            trust_level=2,
        )
        agent_b_id = result_b["agent_id"]

        delegation_service = DelegationService(db_session)
        delegation_result = await delegation_service.create_delegation(
            from_agent_id=agent_a_id,
            to_agent_id=agent_b_id,
            parent_token_id=cap_token_a_id,
            parent_token_type="capability",
            capability="read_database",
            resource_scope="user_table",
            attenuations={"rows_limit": 100, "fields": ["name", "email"]},
            max_depth=1,
            validity_minutes=60,
        )

        assert "delegation_token" in delegation_result
        del_token = delegation_result["delegation_token"]
        assert del_token["from_agent_id"] == agent_a_id
        assert del_token["to_agent_id"] == agent_b_id
        assert del_token["capability"] == "read_database"
        assert del_token["current_depth"] == 0

    async def test_delegation_depth_limit(self, db_session, patched_settings):
        """Test that trust_level=1 cannot delegate."""
        ca_service = CAService(db_session)

        private_key_a, public_key_a = generate_ecdsa_keypair()
        private_key_b, public_key_b = generate_ecdsa_keypair()

        result_a = await ca_service.register_agent(
            name="low-trust-agent",
            public_key_pem=public_key_to_pem(public_key_a).decode('utf-8'),
            owner="user-001",
            requested_capabilities=["read_database"],
            trust_level=1,
        )

        result_b = await ca_service.register_agent(
            name="target-agent",
            public_key_pem=public_key_to_pem(public_key_b).decode('utf-8'),
            owner="user-002",
            requested_capabilities=[],
            trust_level=2,
        )

        delegation_service = DelegationService(db_session)
        with pytest.raises(DelegationError) as exc_info:
            await delegation_service.create_delegation(
                from_agent_id=result_a["agent_id"],
                to_agent_id=result_b["agent_id"],
                parent_token_id=result_a["capability_tokens"][0]["token_id"],
                parent_token_type="capability",
                capability="read_database",
                resource_scope="user_table",
                max_depth=1,
            )
        assert exc_info.value.code == ErrorCode.INVALID_DELEGATION_DEPTH

    async def test_multi_level_delegation(self, db_session, patched_settings):
        """Test A -> B -> C delegation chain."""
        ca_service = CAService(db_session)

        agents = []
        for i, name in enumerate(["agent-a", "agent-b", "agent-c"]):
            private_key, public_key = generate_ecdsa_keypair()
            result = await ca_service.register_agent(
                name=name,
                public_key_pem=public_key_to_pem(public_key).decode('utf-8'),
                owner=f"user-{i}",
                requested_capabilities=["read_database"] if i == 0 else [],
                trust_level=4 if i == 0 else 3,
            )
            agents.append(result)

        delegation_service = DelegationService(db_session)

        del_a_to_b = await delegation_service.create_delegation(
            from_agent_id=agents[0]["agent_id"],
            to_agent_id=agents[1]["agent_id"],
            parent_token_id=agents[0]["capability_tokens"][0]["token_id"],
            parent_token_type="capability",
            capability="read_database",
            resource_scope="user_table",
            attenuations={"rows_limit": 100},
            max_depth=2,
        )
        assert del_a_to_b["delegation_token"]["current_depth"] == 1

        del_b_to_c = await delegation_service.create_delegation(
            from_agent_id=agents[1]["agent_id"],
            to_agent_id=agents[2]["agent_id"],
            parent_token_id=del_a_to_b["delegation_token"]["delegation_id"],
            parent_token_type="delegation",
            capability="read_database",
            resource_scope="user_table",
            attenuations={"rows_limit": 50},
            validity_minutes=30,  # Must be shorter than parent delegation's remaining validity
        )
        assert del_b_to_c["delegation_token"]["current_depth"] == 0

        private_key_d, public_key_d = generate_ecdsa_keypair()
        agent_d = await ca_service.register_agent(
            name="agent-d",
            public_key_pem=public_key_to_pem(public_key_d).decode('utf-8'),
            owner="user-3",
            requested_capabilities=[],
            trust_level=2,
        )

        with pytest.raises(DelegationError) as exc_info:
            await delegation_service.create_delegation(
                from_agent_id=agents[2]["agent_id"],
                to_agent_id=agent_d["agent_id"],
                parent_token_id=del_b_to_c["delegation_token"]["delegation_id"],
                parent_token_type="delegation",
                capability="read_database",
                resource_scope="user_table",
            )
        assert exc_info.value.code == ErrorCode.INVALID_DELEGATION_DEPTH

    async def test_token_chain_with_delegation(self, db_session, patched_settings):
        """Test token chain verification with delegation tokens."""
        ca_service = CAService(db_session)

        private_key_a, public_key_a = generate_ecdsa_keypair()
        private_key_b, public_key_b = generate_ecdsa_keypair()

        result_a = await ca_service.register_agent(
            name="agent-a",
            public_key_pem=public_key_to_pem(public_key_a).decode('utf-8'),
            owner="user-001",
            requested_capabilities=["read_database"],
            trust_level=4,
        )

        result_b = await ca_service.register_agent(
            name="agent-b",
            public_key_pem=public_key_to_pem(public_key_b).decode('utf-8'),
            owner="user-002",
            requested_capabilities=[],
            trust_level=2,
        )

        delegation_service = DelegationService(db_session)
        del_result = await delegation_service.create_delegation(
            from_agent_id=result_a["agent_id"],
            to_agent_id=result_b["agent_id"],
            parent_token_id=result_a["capability_tokens"][0]["token_id"],
            parent_token_type="capability",
            capability="read_database",
            resource_scope="user_table",
            attenuations={"rows_limit": 10},
            max_depth=1,
        )

        verifier = TokenVerifier(db_session)
        token_chain = [
            {"token_id": result_a["certificate"]["cert_id"], "token_type": "certificate"},
            {"token_id": result_a["capability_tokens"][0]["token_id"], "token_type": "capability"},
            {"token_id": del_result["delegation_token"]["delegation_id"], "token_type": "delegation"},
        ]

        verification = await verifier.verify_token_chain(
            token_chain=token_chain,
            requested_action="read_database",
            requested_resource="user_table",
        )

        assert verification.capability == "read_database"
        assert verification.effective_attenuations["rows_limit"] == 10
        assert verification.chain_length == 3

    async def test_agent_tokens_query(self, db_session, patched_settings):
        """Test querying agent's tokens."""
        ca_service = CAService(db_session)

        private_key_a, public_key_a = generate_ecdsa_keypair()
        private_key_b, public_key_b = generate_ecdsa_keypair()

        result_a = await ca_service.register_agent(
            name="agent-a",
            public_key_pem=public_key_to_pem(public_key_a).decode('utf-8'),
            owner="user-001",
            requested_capabilities=["read_database", "read_document"],
            trust_level=4,
        )

        result_b = await ca_service.register_agent(
            name="agent-b",
            public_key_pem=public_key_to_pem(public_key_b).decode('utf-8'),
            owner="user-002",
            requested_capabilities=[],
            trust_level=2,
        )

        delegation_service = DelegationService(db_session)
        await delegation_service.create_delegation(
            from_agent_id=result_a["agent_id"],
            to_agent_id=result_b["agent_id"],
            parent_token_id=result_a["capability_tokens"][0]["token_id"],
            parent_token_type="capability",
            capability="read_database",
            resource_scope="user_table",
            max_depth=1,
        )

        tokens_a = await delegation_service.get_agent_tokens(
            agent_id=result_a["agent_id"],
            requesting_agent_id=result_a["agent_id"],
        )

        assert len(tokens_a["capability_tokens"]) == 2
        assert len(tokens_a["delegation_tokens_issued"]) == 1
        assert len(tokens_a["delegation_tokens_received"]) == 0

        tokens_b = await delegation_service.get_agent_tokens(
            agent_id=result_b["agent_id"],
            requesting_agent_id=result_b["agent_id"],
        )

        assert len(tokens_b["capability_tokens"]) == 0
        assert len(tokens_b["delegation_tokens_issued"]) == 0
        assert len(tokens_b["delegation_tokens_received"]) == 1
