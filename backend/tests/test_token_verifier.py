"""
Tests for Phase 3 components: Token Verifier, Attenuator, Executor.
"""

import base64
import json
import pytest
from datetime import datetime, timedelta

from app.services.attenuator import (
    merge_and_validate_attenuations,
    is_attenuation_stricter_or_equal,
    apply_attenuations_to_data,
    check_time_window_constraint,
    AttenuationError,
)
from app.schemas.common import ErrorCode


# =============================================================================
# Attenuator Tests
# =============================================================================

class TestAttenuator:
    """Tests for attenuation parameter handling."""

    def test_merge_empty_attenuations(self):
        """Test merging empty attenuations."""
        result = merge_and_validate_attenuations({}, {})
        assert result == {}

    def test_merge_new_restriction(self):
        """Test adding a new restriction (allowed)."""
        result = merge_and_validate_attenuations({}, {"rows_limit": 100})
        assert result == {"rows_limit": 100}

    def test_merge_rows_limit_valid(self):
        """Test valid rows_limit merge (child <= parent)."""
        result = merge_and_validate_attenuations(
            {"rows_limit": 100},
            {"rows_limit": 50}
        )
        assert result == {"rows_limit": 50}

    def test_merge_rows_limit_invalid(self):
        """Test invalid rows_limit merge (child > parent)."""
        with pytest.raises(AttenuationError) as exc_info:
            merge_and_validate_attenuations(
                {"rows_limit": 50},
                {"rows_limit": 100}
            )
        assert exc_info.value.code == ErrorCode.INVALID_ATTENUATIONS

    def test_merge_fields_valid_subset(self):
        """Test valid fields merge (child subset of parent)."""
        result = merge_and_validate_attenuations(
            {"fields": ["name", "email", "phone"]},
            {"fields": ["name", "email"]}
        )
        assert result == {"fields": ["name", "email"]}

    def test_merge_fields_wildcard_parent(self):
        """Test fields merge when parent is wildcard."""
        result = merge_and_validate_attenuations(
            {"fields": ["*"]},
            {"fields": ["name", "email"]}
        )
        assert result == {"fields": ["name", "email"]}

    def test_merge_fields_invalid_not_subset(self):
        """Test invalid fields merge (child not subset of parent)."""
        with pytest.raises(AttenuationError) as exc_info:
            merge_and_validate_attenuations(
                {"fields": ["name", "email"]},
                {"fields": ["name", "phone"]}  # phone not in parent
            )
        assert exc_info.value.code == ErrorCode.INVALID_ATTENUATIONS

    def test_merge_time_window_valid(self):
        """Test valid time_window merge (child within parent)."""
        result = merge_and_validate_attenuations(
            {"time_window": {"start": "08:00", "end": "18:00"}},
            {"time_window": {"start": "09:00", "end": "17:00"}}
        )
        assert result == {"time_window": {"start": "09:00", "end": "17:00"}}

    def test_merge_time_window_invalid(self):
        """Test invalid time_window merge (child outside parent)."""
        with pytest.raises(AttenuationError) as exc_info:
            merge_and_validate_attenuations(
                {"time_window": {"start": "09:00", "end": "17:00"}},
                {"time_window": {"start": "08:00", "end": "18:00"}}  # Outside parent
            )
        assert exc_info.value.code == ErrorCode.INVALID_ATTENUATIONS

    def test_merge_multiple_attenuations(self):
        """Test merging multiple attenuation parameters."""
        result = merge_and_validate_attenuations(
            {"rows_limit": 100, "fields": ["name", "email", "phone"]},
            {"rows_limit": 50, "fields": ["name", "email"]}
        )
        assert result == {"rows_limit": 50, "fields": ["name", "email"]}

    def test_is_stricter_or_equal_valid(self):
        """Test stricter_or_equal check for valid case."""
        assert is_attenuation_stricter_or_equal(
            {"rows_limit": 50},
            {"rows_limit": 100}
        )

    def test_is_stricter_or_equal_invalid(self):
        """Test stricter_or_equal check for invalid case."""
        assert not is_attenuation_stricter_or_equal(
            {"rows_limit": 100},
            {"rows_limit": 50}
        )

    def test_apply_attenuations_rows_limit(self):
        """Test applying rows_limit to data."""
        data = [{"id": i} for i in range(10)]
        result, applied = apply_attenuations_to_data(data, {"rows_limit": 5})
        assert len(result) == 5
        assert applied == {"rows_limit": 5}

    def test_apply_attenuations_fields(self):
        """Test applying fields filter to data."""
        data = [
            {"name": "Alice", "email": "a@b.com", "phone": "111"},
            {"name": "Bob", "email": "b@c.com", "phone": "222"},
        ]
        result, applied = apply_attenuations_to_data(data, {"fields": ["name", "email"]})
        assert all(set(row.keys()) == {"name", "email"} for row in result)
        assert applied == {"fields": ["name", "email"]}

    def test_apply_attenuations_combined(self):
        """Test applying combined attenuations."""
        data = [
            {"name": "Alice", "email": "a@b.com", "phone": "111"},
            {"name": "Bob", "email": "b@c.com", "phone": "222"},
            {"name": "Charlie", "email": "c@d.com", "phone": "333"},
        ]
        result, applied = apply_attenuations_to_data(
            data,
            {"rows_limit": 2, "fields": ["name"]}
        )
        assert len(result) == 2
        assert all(set(row.keys()) == {"name"} for row in result)


# =============================================================================
# Executor Tests
# =============================================================================

from app.services.executor import ResourceExecutor, ExecutionError


class TestExecutor:
    """Tests for resource executor."""

    @pytest.fixture
    def executor(self):
        """Create an executor instance."""
        return ResourceExecutor()

    @pytest.mark.asyncio
    async def test_read_database(self, executor):
        """Test reading from a database."""
        result, applied = await executor.execute(
            action="read_database",
            resource="user_table",
            params=None,
            attenuations={}
        )
        assert result["action"] == "read_database"
        assert result["resource"] == "user_table"
        assert "data" in result
        assert len(result["data"]) > 0

    @pytest.mark.asyncio
    async def test_read_database_with_rows_limit(self, executor):
        """Test reading with rows_limit attenuation."""
        result, applied = await executor.execute(
            action="read_database",
            resource="user_table",
            params=None,
            attenuations={"rows_limit": 2}
        )
        assert len(result["data"]) <= 2
        assert applied.get("rows_limit") == 2

    @pytest.mark.asyncio
    async def test_read_database_with_fields(self, executor):
        """Test reading with fields filter."""
        result, applied = await executor.execute(
            action="read_database",
            resource="user_table",
            params=None,
            attenuations={"fields": ["name", "email"]}
        )
        # All rows should only have name and email fields
        for row in result["data"]:
            assert set(row.keys()).issubset({"name", "email"})

    @pytest.mark.asyncio
    async def test_read_unknown_resource(self, executor):
        """Test reading an unknown resource (generates mock data)."""
        result, applied = await executor.execute(
            action="read_database",
            resource="unknown_table",
            params=None,
            attenuations={}
        )
        assert result["action"] == "read_database"
        assert len(result["data"]) > 0  # Mock data generated

    @pytest.mark.asyncio
    async def test_write_database(self, executor):
        """Test writing to a database."""
        result, applied = await executor.execute(
            action="write_database",
            resource="user_table",
            params={"data": [{"name": "Test", "email": "test@test.com"}]},
            attenuations={}
        )
        assert result["status"] == "success"
        assert result["rows_affected"] == 1

    @pytest.mark.asyncio
    async def test_send_message(self, executor):
        """Test sending a message."""
        result, applied = await executor.execute(
            action="send_message",
            resource="chat:123",
            params={"receive_id": "user-123", "content": "Hello"},
            attenuations={}
        )
        assert result["status"] == "sent"
        assert "message_id" in result

    @pytest.mark.asyncio
    async def test_read_bitable(self, executor):
        """Test reading a Feishu bitable."""
        result, applied = await executor.execute(
            action="read_bitable",
            resource="app_xxx:tbl_sales",
            params=None,
            attenuations={}
        )
        assert result["action"] == "read_bitable"
        assert len(result["data"]) > 0

    @pytest.mark.asyncio
    async def test_unknown_action(self, executor):
        """Test unknown action raises error."""
        with pytest.raises(ExecutionError) as exc_info:
            await executor.execute(
                action="unknown_action",
                resource="test",
                params=None,
                attenuations={}
            )
        assert exc_info.value.code == ErrorCode.INVALID_CAPABILITY


# =============================================================================
# Token Verifier Tests (Unit tests for helper methods)
# =============================================================================

from app.services.token_verifier import TokenVerifier


class TestTokenVerifierHelpers:
    """Tests for TokenVerifier helper methods."""

    def test_is_scope_subset_exact_match(self):
        """Test scope subset check with exact match."""
        verifier = TokenVerifier(None)
        assert verifier._is_scope_subset("user_table", "user_table")

    def test_is_scope_subset_wildcard(self):
        """Test scope subset check with wildcard."""
        verifier = TokenVerifier(None)
        assert verifier._is_scope_subset("user_table", "*")

    def test_is_scope_subset_prefix_wildcard(self):
        """Test scope subset check with prefix wildcard."""
        verifier = TokenVerifier(None)
        assert verifier._is_scope_subset("db.users", "db.*")
        assert not verifier._is_scope_subset("other.users", "db.*")

    def test_is_scope_subset_no_match(self):
        """Test scope subset check with no match."""
        verifier = TokenVerifier(None)
        assert not verifier._is_scope_subset("salary_table", "user_table")


# =============================================================================
# Integration-style tests (require database)
# =============================================================================

@pytest.mark.asyncio
class TestTokenChainVerification:
    """Integration tests for token chain verification."""

    @pytest.fixture
    async def setup_test_data(self, db_session):
        """Set up test data for verification tests."""
        # This would create test agents, certificates, tokens, etc.
        # For now, we'll skip this in unit tests
        pass

    async def test_chain_structure_validation(self, db_session):
        """Test token chain structure validation."""
        from app.services.token_verifier import TokenVerifier, TokenVerificationError

        verifier = TokenVerifier(db_session)

        # Test chain too short
        with pytest.raises(TokenVerificationError) as exc_info:
            verifier._validate_chain_structure([
                {"token_id": "cert-1", "token_type": "certificate"}
            ])
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST

        # Test chain not starting with certificate
        with pytest.raises(TokenVerificationError) as exc_info:
            verifier._validate_chain_structure([
                {"token_id": "cap-1", "token_type": "capability"},
                {"token_id": "cap-2", "token_type": "capability"}
            ])
        assert exc_info.value.code == ErrorCode.DELEGATION_CHAIN_INVALID

        # Test valid chain structure
        verifier._validate_chain_structure([
            {"token_id": "cert-1", "token_type": "certificate"},
            {"token_id": "cap-1", "token_type": "capability"}
        ])

        # Test valid chain with delegation
        verifier._validate_chain_structure([
            {"token_id": "cert-1", "token_type": "certificate"},
            {"token_id": "cap-1", "token_type": "capability"},
            {"token_id": "del-1", "token_type": "delegation"}
        ])
