"""
Attenuation parameter handling for capability and delegation tokens.

Implements merging and validation of attenuation parameters to ensure
child tokens are always more restrictive than parent tokens.
"""

import logging
from datetime import datetime, time
from typing import Dict, Any, Optional, List, Tuple

from app.schemas.common import ErrorCode

logger = logging.getLogger(__name__)


class AttenuationError(Exception):
    """Attenuation validation error."""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def merge_and_validate_attenuations(
    parent_attenuations: Dict[str, Any],
    child_attenuations: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge and validate attenuation parameters.

    Child attenuations must be equal or more restrictive than parent.
    This function validates and returns the merged (effective) attenuations.

    Args:
        parent_attenuations: Parent token's attenuation parameters
        child_attenuations: Child token's requested attenuation parameters

    Returns:
        Merged attenuation parameters (child overrides parent where applicable)

    Raises:
        AttenuationError: If child attenuations are less restrictive than parent
    """
    result = dict(parent_attenuations)  # Start with parent's attenuations

    for key, child_value in child_attenuations.items():
        if key not in parent_attenuations:
            # New restriction - always allowed (additional constraints are fine)
            result[key] = child_value
            continue

        parent_value = parent_attenuations[key]

        # Validate based on key type
        if key == "rows_limit":
            result[key] = _validate_rows_limit(parent_value, child_value)
        elif key == "fields":
            result[key] = _validate_fields(parent_value, child_value)
        elif key == "time_window":
            result[key] = _validate_time_window(parent_value, child_value)
        else:
            # Unknown key - reject for safety
            raise AttenuationError(
                ErrorCode.INVALID_ATTENUATIONS,
                f"Unknown attenuation key: {key}",
                {"unknown_key": key}
            )

    return result


def _validate_rows_limit(parent_value: Any, child_value: Any) -> int:
    """
    Validate rows_limit: child must be <= parent.

    Args:
        parent_value: Parent's rows_limit (int or None for unlimited)
        child_value: Child's requested rows_limit

    Returns:
        Validated child rows_limit

    Raises:
        AttenuationError: If child value exceeds parent
    """
    if not isinstance(child_value, int) or child_value < 1:
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"rows_limit must be a positive integer, got: {child_value}",
            {"rows_limit": child_value}
        )

    # If parent has no limit (None or 0), child can set any value
    if parent_value is None or parent_value == 0:
        return child_value

    if not isinstance(parent_value, int):
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"Parent rows_limit must be an integer, got: {parent_value}",
            {"parent_rows_limit": parent_value}
        )

    if child_value > parent_value:
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"rows_limit {child_value} exceeds parent's {parent_value}",
            {"child_rows_limit": child_value, "parent_rows_limit": parent_value}
        )

    return child_value


def _validate_fields(parent_value: Any, child_value: Any) -> List[str]:
    """
    Validate fields: child must be subset of parent.

    Args:
        parent_value: Parent's fields (list of strings, ["*"] means all)
        child_value: Child's requested fields

    Returns:
        Validated child fields

    Raises:
        AttenuationError: If child fields are not a subset of parent
    """
    if not isinstance(child_value, list):
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"fields must be a list, got: {type(child_value).__name__}",
            {"fields": child_value}
        )

    if not child_value:
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            "fields cannot be empty",
            {"fields": child_value}
        )

    # If parent is ["*"] (all fields), child can request any subset
    if parent_value == ["*"]:
        return child_value

    if not isinstance(parent_value, list):
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"Parent fields must be a list, got: {type(parent_value).__name__}",
            {"parent_fields": parent_value}
        )

    parent_set = set(parent_value)
    child_set = set(child_value)

    # Check if child is subset of parent
    extra_fields = child_set - parent_set
    if extra_fields:
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"fields {list(extra_fields)} not in parent's fields",
            {
                "child_fields": child_value,
                "parent_fields": parent_value,
                "extra_fields": list(extra_fields)
            }
        )

    return child_value


def _validate_time_window(parent_value: Any, child_value: Any) -> Dict[str, str]:
    """
    Validate time_window: child window must be within parent window.

    Args:
        parent_value: Parent's time_window {"start": "HH:MM", "end": "HH:MM"}
        child_value: Child's requested time_window

    Returns:
        Validated child time_window

    Raises:
        AttenuationError: If child window is not within parent window
    """
    if not isinstance(child_value, dict):
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"time_window must be a dict, got: {type(child_value).__name__}",
            {"time_window": child_value}
        )

    if "start" not in child_value or "end" not in child_value:
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            "time_window must have 'start' and 'end' fields",
            {"time_window": child_value}
        )

    if not isinstance(parent_value, dict):
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"Parent time_window must be a dict, got: {type(parent_value).__name__}",
            {"parent_time_window": parent_value}
        )

    try:
        child_start = _parse_time(child_value["start"])
        child_end = _parse_time(child_value["end"])
        parent_start = _parse_time(parent_value["start"])
        parent_end = _parse_time(parent_value["end"])
    except ValueError as e:
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"Invalid time format: {e}",
            {"time_window": child_value}
        )

    # Check if child window is within parent window
    if child_start < parent_start:
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"time_window start {child_value['start']} is before parent's start {parent_value['start']}",
            {
                "child_start": child_value["start"],
                "parent_start": parent_value["start"]
            }
        )

    if child_end > parent_end:
        raise AttenuationError(
            ErrorCode.INVALID_ATTENUATIONS,
            f"time_window end {child_value['end']} is after parent's end {parent_value['end']}",
            {
                "child_end": child_value["end"],
                "parent_end": parent_value["end"]
            }
        )

    return child_value


def _parse_time(time_str: str) -> time:
    """
    Parse a time string in HH:MM format.

    Args:
        time_str: Time string like "09:00" or "18:30"

    Returns:
        time object

    Raises:
        ValueError: If format is invalid
    """
    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid time format: {time_str}")
        hour, minute = int(parts[0]), int(parts[1])
        return time(hour, minute)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid time format '{time_str}': {e}")


def is_attenuation_stricter_or_equal(
    child_attenuations: Dict[str, Any],
    parent_attenuations: Dict[str, Any],
) -> bool:
    """
    Check if child attenuations are stricter or equal to parent.

    This is used during token chain verification to ensure
    each delegation in the chain is progressively more restrictive.

    Args:
        child_attenuations: Child token's attenuation parameters
        parent_attenuations: Parent token's attenuation parameters

    Returns:
        True if child is stricter or equal, False otherwise
    """
    try:
        merge_and_validate_attenuations(parent_attenuations, child_attenuations)
        return True
    except AttenuationError:
        return False


def apply_attenuations_to_data(
    data: List[Dict[str, Any]],
    attenuations: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Apply attenuation parameters to result data.

    This is used by the resource executor to filter and limit
    the returned data based on effective attenuations.

    Args:
        data: Raw data from resource execution
        attenuations: Effective attenuation parameters

    Returns:
        Tuple of (filtered_data, applied_attenuations)
    """
    result = data
    applied = {}

    # Apply rows_limit
    if "rows_limit" in attenuations:
        rows_limit = attenuations["rows_limit"]
        if len(result) > rows_limit:
            result = result[:rows_limit]
        applied["rows_limit"] = rows_limit

    # Apply fields filter
    if "fields" in attenuations:
        fields = attenuations["fields"]
        if fields != ["*"]:
            result = [
                {k: v for k, v in row.items() if k in fields}
                for row in result
            ]
        applied["fields"] = fields

    # time_window is checked at execution time, not applied to data

    return result, applied


def check_time_window_constraint(
    attenuations: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Check if current time is within the allowed time window.

    Args:
        attenuations: Attenuation parameters containing time_window

    Returns:
        Tuple of (is_allowed, error_message)
    """
    if "time_window" not in attenuations:
        return True, None

    time_window = attenuations["time_window"]
    if not isinstance(time_window, dict):
        return True, None

    try:
        now = datetime.utcnow().time()
        start = _parse_time(time_window["start"])
        end = _parse_time(time_window["end"])

        if start <= end:
            # Normal case: start <= now <= end
            if start <= now <= end:
                return True, None
        else:
            # Overnight case: e.g., 22:00 to 06:00
            if now >= start or now <= end:
                return True, None

        return False, f"Current time {now.strftime('%H:%M')} is outside allowed window {time_window['start']}-{time_window['end']}"
    except (ValueError, KeyError) as e:
        # If we can't parse the time window, allow the operation
        logger.warning(f"Failed to parse time_window: {e}")
        return True, None
