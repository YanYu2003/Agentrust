"""
Database connection and initialization.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_database():
    """Initialize database and create tables if not exist."""
    # Ensure data directory exists
    db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        # Check if schema_version table exists
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        )
        exists = result.fetchone()

        if not exists:
            # Create all tables (execute each statement separately)
            for statement in SCHEMA_STATEMENTS:
                await conn.execute(text(statement))
            # Insert initial schema version
            await conn.execute(
                text("INSERT INTO schema_version (version, description) VALUES (1, 'Initial schema')")
            )
            logger.info("Database tables created successfully")
        else:
            # Check current schema version
            result = await conn.execute(text("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"))
            row = result.fetchone()
            current_version = row[0] if row else 0
            logger.info(f"Database schema version: {current_version}")

            # Apply migrations if needed (future versions would add migration logic here)
            # if current_version < 2:
            #     for statement in MIGRATION_002_STATEMENTS:
            #         await conn.execute(text(statement))
            #     await conn.execute(text("UPDATE schema_version SET version = 2"))
            #     logger.info("Applied migration 002")


async def get_session() -> AsyncSession:
    """Get database session dependency."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


# SQL Schema Statements (executed one at a time for SQLite compatibility)
SCHEMA_STATEMENTS = [
    # Schema version management
    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (datetime('now')),
        description TEXT NOT NULL
    )""",

    # CA Root Keys
    """CREATE TABLE IF NOT EXISTS ca_root_keys (
        key_id TEXT PRIMARY KEY NOT NULL,
        public_key BLOB NOT NULL,
        encrypted_private_key BLOB NOT NULL,
        algorithm TEXT NOT NULL DEFAULT 'ES256',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL
    )""",

    # Agents
    """CREATE TABLE IF NOT EXISTS agents (
        agent_id TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL UNIQUE,
        description TEXT DEFAULT '',
        owner TEXT NOT NULL,
        trust_level INTEGER NOT NULL DEFAULT 1 CHECK(trust_level BETWEEN 1 AND 5),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'revoked')),
        registered_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_agents_owner ON agents(owner)",
    "CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status)",

    # Certificates
    """CREATE TABLE IF NOT EXISTS certificates (
        cert_id TEXT PRIMARY KEY NOT NULL,
        agent_id TEXT NOT NULL,
        public_key BLOB NOT NULL,
        issuer_key_id TEXT NOT NULL,
        signature BLOB NOT NULL,
        algorithm TEXT NOT NULL DEFAULT 'ES256',
        capabilities TEXT NOT NULL DEFAULT '[]',
        trust_level INTEGER NOT NULL CHECK(trust_level BETWEEN 1 AND 5),
        issued_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'valid' CHECK(status IN ('valid', 'expired', 'revoked')),
        FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
        FOREIGN KEY (issuer_key_id) REFERENCES ca_root_keys(key_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_certificates_agent_id ON certificates(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_certificates_expires_at ON certificates(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_certificates_status ON certificates(status)",

    # Capability Tokens
    """CREATE TABLE IF NOT EXISTS capability_tokens (
        token_id TEXT PRIMARY KEY NOT NULL,
        holder_agent_id TEXT NOT NULL,
        cert_id TEXT NOT NULL,
        capability TEXT NOT NULL,
        resource_scope TEXT NOT NULL DEFAULT '*',
        attenuations TEXT NOT NULL DEFAULT '{}',
        issued_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL,
        signature BLOB NOT NULL,
        FOREIGN KEY (holder_agent_id) REFERENCES agents(agent_id),
        FOREIGN KEY (cert_id) REFERENCES certificates(cert_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_capability_tokens_holder ON capability_tokens(holder_agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_capability_tokens_capability ON capability_tokens(capability)",
    "CREATE INDEX IF NOT EXISTS idx_capability_tokens_expires_at ON capability_tokens(expires_at)",

    # Delegation Tokens
    """CREATE TABLE IF NOT EXISTS delegation_tokens (
        delegation_id TEXT PRIMARY KEY NOT NULL,
        from_agent_id TEXT NOT NULL,
        to_agent_id TEXT NOT NULL,
        parent_token_id TEXT NOT NULL,
        parent_token_type TEXT NOT NULL CHECK(parent_token_type IN ('capability', 'delegation')),
        capability TEXT NOT NULL,
        resource_scope TEXT NOT NULL,
        attenuations TEXT NOT NULL DEFAULT '{}',
        max_depth INTEGER NOT NULL CHECK(max_depth >= 0),
        current_depth INTEGER NOT NULL CHECK(current_depth >= 0),
        issued_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL,
        from_signature BLOB NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'expired', 'revoked')),
        FOREIGN KEY (from_agent_id) REFERENCES agents(agent_id),
        FOREIGN KEY (to_agent_id) REFERENCES agents(agent_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_delegation_tokens_from ON delegation_tokens(from_agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_delegation_tokens_to ON delegation_tokens(to_agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_delegation_tokens_parent ON delegation_tokens(parent_token_id)",
    "CREATE INDEX IF NOT EXISTS idx_delegation_tokens_capability ON delegation_tokens(capability)",
    "CREATE INDEX IF NOT EXISTS idx_delegation_tokens_expires_at ON delegation_tokens(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_delegation_tokens_status ON delegation_tokens(status)",

    # Certificate Revocation List
    """CREATE TABLE IF NOT EXISTS crl_entries (
        entry_id TEXT PRIMARY KEY NOT NULL,
        cert_id TEXT NOT NULL UNIQUE,
        reason TEXT NOT NULL,
        revoked_at TEXT NOT NULL DEFAULT (datetime('now')),
        revoked_by TEXT NOT NULL,
        FOREIGN KEY (cert_id) REFERENCES certificates(cert_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_crl_entries_cert_id ON crl_entries(cert_id)",
    "CREATE INDEX IF NOT EXISTS idx_crl_entries_revoked_at ON crl_entries(revoked_at)",

    # Audit Logs
    """CREATE TABLE IF NOT EXISTS audit_logs (
        log_id TEXT PRIMARY KEY NOT NULL,
        agent_id TEXT NOT NULL,
        parent_agent_id TEXT DEFAULT NULL,
        task_id TEXT DEFAULT NULL,
        action TEXT NOT NULL,
        resource TEXT NOT NULL,
        result TEXT NOT NULL CHECK(result IN ('ALLOWED', 'DENIED', 'ERROR')),
        token_chain TEXT NOT NULL DEFAULT '[]',
        request_context TEXT DEFAULT '{}',
        task_context TEXT DEFAULT '{}',
        delegation_chain_summary TEXT,
        error_detail TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_agent_id ON audit_logs(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_task_id ON audit_logs(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_result ON audit_logs(result)",
    "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC)",

    # Challenges (for authentication)
    """CREATE TABLE IF NOT EXISTS challenges (
        challenge_id TEXT PRIMARY KEY NOT NULL,
        agent_id TEXT NOT NULL,
        cert_id TEXT NOT NULL,
        nonce TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'used', 'expired')),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_challenges_agent_id ON challenges(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_challenges_status ON challenges(status)",
    "CREATE INDEX IF NOT EXISTS idx_challenges_expires_at ON challenges(expires_at)",

    # Session Tokens
    """CREATE TABLE IF NOT EXISTS session_tokens (
        session_id TEXT PRIMARY KEY NOT NULL,
        agent_id TEXT NOT NULL,
        cert_id TEXT NOT NULL,
        challenge_id TEXT NOT NULL,
        trust_level INTEGER NOT NULL,
        issued_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'revoked')),
        FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
        FOREIGN KEY (cert_id) REFERENCES certificates(cert_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_session_tokens_agent_id ON session_tokens(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_session_tokens_expires_at ON session_tokens(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_session_tokens_status ON session_tokens(status)",
]
