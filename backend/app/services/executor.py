"""
Resource Executor - Simulated resource execution.

Implements mock executors for various capabilities that:
- Return simulated data
- Apply attenuation parameters (rows_limit, fields filter)
- Do not connect to real external APIs
"""

import logging
import random
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.services.attenuator import (
    apply_attenuations_to_data,
    check_time_window_constraint,
)
from app.schemas.common import ErrorCode

logger = logging.getLogger(__name__)


class ExecutionError(Exception):
    """Execution error."""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ResourceExecutor:
    """Resource execution service (simulated)."""

    def __init__(self):
        # Mock data for different resources
        self._mock_databases = {
            "user_table": [
                {"id": 1, "name": "Alice", "email": "alice@example.com", "phone": "111-1111", "department": "Engineering"},
                {"id": 2, "name": "Bob", "email": "bob@example.com", "phone": "222-2222", "department": "Sales"},
                {"id": 3, "name": "Charlie", "email": "charlie@example.com", "phone": "333-3333", "department": "Engineering"},
                {"id": 4, "name": "Diana", "email": "diana@example.com", "phone": "444-4444", "department": "Marketing"},
                {"id": 5, "name": "Eve", "email": "eve@example.com", "phone": "555-5555", "department": "Engineering"},
            ],
            "salary_table": [
                {"id": 1, "name": "Alice", "salary": 100000, "bonus": 10000},
                {"id": 2, "name": "Bob", "salary": 80000, "bonus": 8000},
                {"id": 3, "name": "Charlie", "salary": 90000, "bonus": 9000},
            ],
            "product_table": [
                {"id": 1, "product_name": "Widget A", "price": 19.99, "stock": 100},
                {"id": 2, "product_name": "Widget B", "price": 29.99, "stock": 50},
                {"id": 3, "product_name": "Widget C", "price": 39.99, "stock": 25},
            ],
        }

        self._mock_documents = {
            "report_doc": {
                "title": "Annual Report 2025",
                "content": "This is the annual report content...",
                "author": "Alice",
                "created_at": "2025-01-15T10:00:00Z",
            },
            "policy_doc": {
                "title": "Security Policy",
                "content": "Security policy document content...",
                "author": "Security Team",
                "created_at": "2025-02-01T08:00:00Z",
            },
        }

        self._mock_bitables = {
            "app_xxx:tbl_sales": [
                {"product_name": "Widget A", "sales_amount": 5000, "date": "2025-01-01", "region": "North"},
                {"product_name": "Widget B", "sales_amount": 3000, "date": "2025-01-02", "region": "South"},
                {"product_name": "Widget C", "sales_amount": 4000, "date": "2025-01-03", "region": "East"},
                {"product_name": "Widget A", "sales_amount": 6000, "date": "2025-01-04", "region": "West"},
                {"product_name": "Widget B", "sales_amount": 2000, "date": "2025-01-05", "region": "North"},
            ],
        }

    async def execute(
        self,
        action: str,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Execute a resource operation with attenuation parameters applied.

        Args:
            action: Action to perform (e.g., "read_database")
            resource: Resource identifier (e.g., "user_table")
            params: Additional parameters for the operation
            attenuations: Effective attenuation parameters to apply

        Returns:
            Tuple of (result_data, applied_attenuations)
        """
        # Check time window constraint first
        allowed, time_error = check_time_window_constraint(attenuations)
        if not allowed:
            raise ExecutionError(
                ErrorCode.PERMISSION_DENIED,
                time_error,
                {"attenuations": attenuations}
            )

        # Route to appropriate handler
        if action == "read_database":
            return await self._read_database(resource, params, attenuations)
        elif action == "write_database":
            return await self._write_database(resource, params, attenuations)
        elif action == "delete_database":
            return await self._delete_database(resource, params, attenuations)
        elif action == "read_document":
            return await self._read_document(resource, params, attenuations)
        elif action == "write_document":
            return await self._write_document(resource, params, attenuations)
        elif action == "delete_document":
            return await self._delete_document(resource, params, attenuations)
        elif action == "send_message":
            return await self._send_message(resource, params, attenuations)
        elif action == "read_bitable":
            return await self._read_bitable(resource, params, attenuations)
        elif action == "write_bitable":
            return await self._write_bitable(resource, params, attenuations)
        elif action == "read_doc":
            return await self._read_doc(resource, params, attenuations)
        elif action == "write_doc":
            return await self._write_doc(resource, params, attenuations)
        elif action == "read_calendar":
            return await self._read_calendar(resource, params, attenuations)
        elif action == "create_meeting":
            return await self._create_meeting(resource, params, attenuations)
        elif action == "manage_agents":
            return await self._manage_agents(resource, params, attenuations)
        else:
            raise ExecutionError(
                ErrorCode.INVALID_CAPABILITY,
                f"Unknown action: {action}",
                {"action": action}
            )

    async def _read_database(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate reading from a database table."""
        # Get mock data
        data = self._mock_databases.get(resource, self._generate_mock_data(resource))

        # Apply attenuations
        filtered_data, applied = apply_attenuations_to_data(data, attenuations)

        return {
            "action": "read_database",
            "resource": resource,
            "data": filtered_data,
            "rows_returned": len(filtered_data),
        }, applied

    async def _write_database(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate writing to a database table."""
        if not params or "data" not in params:
            raise ExecutionError(
                ErrorCode.INVALID_REQUEST,
                "write_database requires 'data' in params",
                {"params": params}
            )

        # Simulate write
        return {
            "action": "write_database",
            "resource": resource,
            "rows_affected": len(params["data"]) if isinstance(params["data"], list) else 1,
            "status": "success",
        }, {}

    async def _delete_database(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate deleting from a database table."""
        return {
            "action": "delete_database",
            "resource": resource,
            "rows_affected": params.get("count", 1) if params else 1,
            "status": "success",
        }, {}

    async def _read_document(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate reading a document."""
        doc = self._mock_documents.get(resource, {
            "title": f"Document: {resource}",
            "content": "Mock document content",
            "author": "Unknown",
            "created_at": datetime.utcnow().isoformat() + "Z",
        })

        # Apply field attenuation if specified
        if "fields" in attenuations and attenuations["fields"] != ["*"]:
            fields = attenuations["fields"]
            doc = {k: v for k, v in doc.items() if k in fields}

        return {
            "action": "read_document",
            "resource": resource,
            "document": doc,
        }, {"fields": attenuations.get("fields", ["*"])}

    async def _write_document(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate writing a document."""
        return {
            "action": "write_document",
            "resource": resource,
            "status": "success",
            "bytes_written": len(str(params).encode()) if params else 0,
        }, {}

    async def _delete_document(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate deleting a document."""
        return {
            "action": "delete_document",
            "resource": resource,
            "status": "success",
        }, {}

    async def _send_message(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate sending a message."""
        if not params:
            raise ExecutionError(
                ErrorCode.INVALID_REQUEST,
                "send_message requires params",
                {}
            )

        return {
            "action": "send_message",
            "resource": resource,
            "message_id": f"msg-{random.randint(1000, 9999)}",
            "status": "sent",
            "recipient": params.get("receive_id", "unknown"),
        }, {}

    async def _read_bitable(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate reading a Feishu bitable (multi-dimensional table)."""
        # Parse resource format: app_token:table_id
        data = self._mock_bitables.get(resource, self._generate_mock_bitable(resource))

        # Apply attenuations
        filtered_data, applied = apply_attenuations_to_data(data, attenuations)

        return {
            "action": "read_bitable",
            "resource": resource,
            "data": filtered_data,
            "rows_returned": len(filtered_data),
        }, applied

    async def _write_bitable(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate writing to a Feishu bitable."""
        return {
            "action": "write_bitable",
            "resource": resource,
            "rows_affected": len(params.get("records", [])) if params else 0,
            "status": "success",
        }, {}

    async def _read_doc(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate reading a Feishu doc."""
        return {
            "action": "read_doc",
            "resource": resource,
            "content": f"Mock content for Feishu doc: {resource}",
            "sections": 3,
        }, {}

    async def _write_doc(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate writing to a Feishu doc."""
        return {
            "action": "write_doc",
            "resource": resource,
            "status": "success",
        }, {}

    async def _read_calendar(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate reading calendar events."""
        events = [
            {"id": "evt-1", "title": "Team Meeting", "time": "2025-01-20T10:00:00Z"},
            {"id": "evt-2", "title": "Project Review", "time": "2025-01-21T14:00:00Z"},
        ]

        # Apply attenuations
        filtered_data, applied = apply_attenuations_to_data(events, attenuations)

        return {
            "action": "read_calendar",
            "resource": resource,
            "events": filtered_data,
        }, applied

    async def _create_meeting(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate creating a meeting."""
        return {
            "action": "create_meeting",
            "resource": resource,
            "meeting_id": f"mtg-{random.randint(1000, 9999)}",
            "status": "created",
            "topic": params.get("topic", "Untitled Meeting") if params else "Untitled Meeting",
        }, {}

    async def _manage_agents(
        self,
        resource: str,
        params: Optional[Dict[str, Any]],
        attenuations: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Simulate agent management operation."""
        return {
            "action": "manage_agents",
            "resource": resource,
            "status": "success",
            "operation": params.get("operation", "unknown") if params else "unknown",
        }, {}

    def _generate_mock_data(self, resource: str) -> List[Dict[str, Any]]:
        """Generate generic mock data for unknown resources."""
        return [
            {"id": i, "field1": f"value{i}a", "field2": f"value{i}b", "field3": f"value{i}c"}
            for i in range(1, 11)
        ]

    def _generate_mock_bitable(self, resource: str) -> List[Dict[str, Any]]:
        """Generate mock bitable data for unknown resources."""
        return [
            {"col1": f"data{i}a", "col2": f"data{i}b", "col3": i * 100}
            for i in range(1, 6)
        ]
