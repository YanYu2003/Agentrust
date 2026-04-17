"""
Pytest configuration and fixtures.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.database import SCHEMA_STATEMENTS
from app.config import Settings


# Test settings constants - must match what's used in tests
TEST_CA_KEY_PASSWORD = "test-ca-password-12345"
TEST_SESSION_SECRET = "test-secret-key-32-bytes-long!!"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_settings():
    """Create test settings."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        session_secret=TEST_SESSION_SECRET,
        ca_key_password=TEST_CA_KEY_PASSWORD,
    )


@pytest_asyncio.fixture(scope="function")
async def test_db(test_settings):
    """Create an in-memory test database with CA root key."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        for statement in SCHEMA_STATEMENTS:
            await conn.execute(text(statement))
        await conn.execute(
            text("INSERT INTO schema_version (version, description) VALUES (1, 'Initial schema')")
        )

        # Initialize CA root key for tests - use the same password that will be in settings
        from app.crypto.keys import generate_ca_keypair, save_ca_keypair

        key_data = generate_ca_keypair(
            password=TEST_CA_KEY_PASSWORD,
            validity_days=365,
        )

        public_key_blob, encrypted_private_key_blob = save_ca_keypair(key_data)

        await conn.execute(
            text("""
                INSERT INTO ca_root_keys (key_id, public_key, encrypted_private_key, algorithm, created_at, expires_at)
                VALUES (:key_id, :public_key, :encrypted_private_key, 'ES256', :created_at, :expires_at)
            """),
            {
                "key_id": key_data["key_id"],
                "public_key": public_key_blob,
                "encrypted_private_key": encrypted_private_key_blob,
                "created_at": key_data["created_at"],
                "expires_at": key_data["expires_at"],
            }
        )

    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_maker() as session:
        yield session

    await engine.dispose()


# Alias for convenience
@pytest_asyncio.fixture(scope="function")
async def db_session(test_db):
    """Alias for test_db fixture with settings patching."""
    yield test_db


# Fixture for patching settings in tests that need it
@pytest.fixture(scope="function")
def patched_settings(test_settings):
    """Patch settings for tests that need consistent passwords."""
    with patch('app.config.settings', test_settings):
        with patch('app.crypto.keys.settings', test_settings):
            yield test_settings
