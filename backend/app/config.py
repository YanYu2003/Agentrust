"""
Application configuration management.
"""

import os
import secrets
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "sqlite+aiosqlite:///../data/agentrust.db"

    # Security
    session_secret: str = ""  # 32-byte secret for session token signing
    ca_key_password: str = ""  # Password for encrypting CA private key

    # Logging
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Token defaults
    session_token_expire_minutes: int = 15
    challenge_expire_seconds: int = 60

    # Trust level defaults (hours)
    trust_level_default_hours: dict[int, int] = {
        1: 1,
        2: 6,
        3: 24,
        4: 72,
        5: 168,
    }

    # Trust level max delegation depth
    trust_level_max_depth: dict[int, int] = {
        1: 0,
        2: 1,
        3: 2,
        4: 5,
        5: 10,
    }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Generate session secret if not provided
        if not self.session_secret:
            self.session_secret = secrets.token_hex(32)
        if not self.ca_key_password:
            self.ca_key_password = secrets.token_hex(16)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
