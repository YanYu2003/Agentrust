"""
Utility functions and helpers.
"""

import uuid
from datetime import datetime
from typing import Optional


def generate_id(prefix: str) -> str:
    """
    Generate a unique ID with a given prefix.

    Args:
        prefix: ID prefix (e.g., "agent", "cert", "cap", "del").

    Returns:
        Unique ID string like "agent-a1b2c3d4".

    Example:
        >>> generate_id("agent")
        'agent-a1b2c3d4'
    """
    short_uuid = uuid.uuid4().hex[:8]
    return f"{prefix}-{short_uuid}"


def now_iso() -> str:
    """
    Get current UTC time in ISO8601 format.

    Returns:
        ISO8601 formatted string like "2025-04-16T14:30:00Z".
    """
    return datetime.utcnow().isoformat() + "Z"


def parse_iso(iso_string: str) -> datetime:
    """
    Parse an ISO8601 formatted string to datetime.

    Args:
        iso_string: ISO8601 formatted string.

    Returns:
        datetime object (timezone-naive, in UTC).

    Raises:
        ValueError: If the string cannot be parsed.
    """
    # Handle 'Z' suffix - convert to naive UTC datetime
    if iso_string.endswith("Z"):
        iso_string = iso_string[:-1]  # Remove Z, treat as naive UTC

    # Try different formats
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(iso_string, fmt)
        except ValueError:
            continue

    raise ValueError(f"Cannot parse ISO8601 string: {iso_string}")


def is_expired(expires_at: str) -> bool:
    """
    Check if a timestamp has expired.

    Args:
        expires_at: ISO8601 formatted expiration timestamp.

    Returns:
        True if expired, False otherwise.
    """
    try:
        expiry = parse_iso(expires_at)
        return datetime.utcnow() > expiry.replace(tzinfo=None)
    except ValueError:
        return True


def hours_to_iso(hours: int) -> str:
    """
    Convert hours from now to ISO8601 timestamp.

    Args:
        hours: Number of hours from now.

    Returns:
        ISO8601 formatted timestamp.
    """
    from datetime import timedelta
    future = datetime.utcnow() + timedelta(hours=hours)
    return future.isoformat() + "Z"
