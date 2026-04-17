"""
Database initialization script.

Run this script to initialize the database and optionally generate CA keys.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.database import init_database, engine
from app.crypto.keys import generate_ca_keypair, save_ca_keypair
from sqlalchemy import text


async def init_ca_key():
    """Initialize CA root key if not exists."""
    async with engine.begin() as conn:
        # Check if CA key exists
        result = await conn.execute(
            text("SELECT key_id FROM ca_root_keys LIMIT 1")
        )
        existing = result.fetchone()

        if existing:
            print(f"CA root key already exists: {existing[0]}")
            return existing[0]

        # Generate new CA key
        print("Generating CA root key pair...")
        key_data = generate_ca_keypair(validity_days=365)

        # Store in database
        public_key_blob, encrypted_private_key_blob = save_ca_keypair(key_data)

        await conn.execute(
            text("""
                INSERT INTO ca_root_keys (key_id, public_key, encrypted_private_key, algorithm, created_at, expires_at)
                VALUES (:key_id, :public_key, :encrypted_private_key, :algorithm, :created_at, :expires_at)
            """),
            {
                "key_id": key_data["key_id"],
                "public_key": public_key_blob,
                "encrypted_private_key": encrypted_private_key_blob,
                "algorithm": key_data["algorithm"],
                "created_at": key_data["created_at"],
                "expires_at": key_data["expires_at"],
            },
        )

        print(f"CA root key generated: {key_data['key_id']}")
        print(f"  Algorithm: {key_data['algorithm']}")
        print(f"  Created at: {key_data['created_at']}")
        print(f"  Expires at: {key_data['expires_at']}")

        return key_data["key_id"]


async def main():
    """Main initialization function."""
    print("=" * 50)
    print("Agentrust Database Initialization")
    print("=" * 50)
    print()

    # Ensure data directory exists
    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Database path: {db_path.absolute()}")
    print()

    # Initialize database schema
    print("Initializing database schema...")
    await init_database()
    print("Database schema initialized.")
    print()

    # Initialize CA key
    print("Initializing CA root key...")
    key_id = await init_ca_key()
    print()

    # Verify tables
    print("Verifying database tables...")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = [row[0] for row in result.fetchall()]
        print(f"Tables created: {', '.join(tables)}")
    print()

    # Get schema version
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT version, description FROM schema_version"))
        row = result.fetchone()
        if row:
            print(f"Schema version: {row[0]} ({row[1]})")
    print()

    print("=" * 50)
    print("Initialization complete!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
