"""
Integration tests configuration and fixtures.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import settings
from app.database import SCHEMA_STATEMENTS, get_session


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session():
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

        # Initialize CA root key for tests
        from app.crypto.keys import generate_ca_keypair, save_ca_keypair

        key_data = generate_ca_keypair(
            password=settings.ca_key_password,
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


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    """Create an async test client with mocked database."""
    # Import here to avoid circular imports
    from main import app

    # Override the database dependency - must use the same get_session function
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
