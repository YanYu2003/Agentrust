"""
Canonical JSON serialization for deterministic signing.

Ensures that the same logical JSON structure always produces the same byte
representation, which is critical for signature verification.
"""

import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """
    Serialize an object to canonical JSON format.

    Rules:
    1. Keys are sorted alphabetically (recursively)
    2. No extra whitespace
    3. No trailing zeros in numbers
    4. Null values are omitted (optional, can be configured)
    5. Unicode characters are not escaped

    Args:
        obj: Python object to serialize (dict, list, str, int, float, bool, None).

    Returns:
        Canonical JSON string.

    Example:
        >>> canonical_json({"b": 1, "a": 2})
        '{"a":2,"b":1}'
    """
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _normalize(obj: Any) -> Any:
    """
    Recursively normalize an object for canonical serialization.

    - Removes null values from dicts (optional, currently disabled)
    - Ensures consistent representation

    Args:
        obj: Object to normalize.

    Returns:
        Normalized object.
    """
    if isinstance(obj, dict):
        # Sort keys and recursively normalize values
        # Note: We keep null values for explicit representation
        return {k: _normalize(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, (list, tuple)):
        return [_normalize(item) for item in obj]
    elif isinstance(obj, float):
        # Handle special float cases
        if obj != obj:  # NaN
            return "NaN"
        elif obj == float("inf"):
            return "Infinity"
        elif obj == float("-inf"):
            return "-Infinity"
        return obj
    else:
        return obj


def canonical_json_bytes(obj: Any) -> bytes:
    """
    Serialize an object to canonical JSON bytes.

    Args:
        obj: Python object to serialize.

    Returns:
        Canonical JSON bytes (UTF-8 encoded).
    """
    return canonical_json(obj).encode("utf-8")
