"""
Feishu (Lark) API wrappers for Agentrust SDK.

Provides high-level methods for Feishu operations:
- read_bitable(): Read Feishu multi-dimensional table
- send_message(): Send Feishu messages
- read_doc(): Read Feishu documents
- write_doc(): Write to Feishu documents
- read_calendar(): Read calendar events
- create_meeting(): Create meetings
"""

from typing import Dict, List, Optional, Any

from .client import AgentClient


class FeishuClient:
    """
    High-level wrapper for Feishu API operations.

    This class provides convenient methods for common Feishu operations
    that map to Agentrust capabilities.

    Usage:
        client = AgentClient("http://localhost:8000/api/v1", wallet)
        client.authenticate("agent-analyst", "cert-001")

        feishu = FeishuClient(client)

        # Read a bitable
        records = feishu.read_bitable("app_xxx", "tbl_xxx")

        # Send a message
        feishu.send_message("ou_xxx", "Hello!")

        # Read with attenuation
        records = feishu.read_bitable(
            "app_xxx", "tbl_xxx",
            fields=["name", "email"],
            page_size=50
        )
    """

    def __init__(self, client: AgentClient):
        """
        Initialize Feishu client.

        Args:
            client: AgentClient instance.
        """
        self.client = client

    def read_bitable(
        self,
        app_token: str,
        table_id: str,
        fields: List[str] = None,
        page_size: int = None,
        filter: str = None,
    ) -> Dict[str, Any]:
        """
        Read data from a Feishu multi-dimensional table.

        Args:
            app_token: Feishu app token.
            table_id: Table ID within the app.
            fields: List of fields to return (applies fields attenuation).
            page_size: Maximum number of records to return (applies rows_limit attenuation).
            filter: Optional filter condition.

        Returns:
            Record data from the table.
        """
        params = {
            "app_token": app_token,
            "table_id": table_id,
        }
        if fields:
            params["fields"] = ",".join(fields)
        if page_size:
            params["page_size"] = page_size
        if filter:
            params["filter"] = filter

        resource = f"{app_token}:{table_id}"
        return self.client.execute("read_bitable", resource, params=params)

    def write_bitable(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Write records to a Feishu multi-dimensional table.

        Args:
            app_token: Feishu app token.
            table_id: Table ID within the app.
            records: List of records to write.

        Returns:
            Write operation result.
        """
        params = {
            "app_token": app_token,
            "table_id": table_id,
            "records": records,
        }

        resource = f"{app_token}:{table_id}"
        return self.client.execute("write_bitable", resource, params=params)

    def send_message(
        self,
        receive_id: str,
        content: str,
        msg_type: str = "text",
        receive_id_type: str = "open_id",
    ) -> Dict[str, Any]:
        """
        Send a message via Feishu.

        Args:
            receive_id: Recipient ID (open_id, user_id, email, or chat_id).
            content: Message content (JSON string for rich text).
            msg_type: Message type (text, post, image, etc.).
            receive_id_type: Type of receive_id (open_id, user_id, email, chat_id).

        Returns:
            Send operation result with message_id.
        """
        params = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "msg_type": msg_type,
            "content": content,
        }

        resource = f"chat:{receive_id}"
        return self.client.execute("send_message", resource, params=params)

    def send_text_message(
        self,
        receive_id: str,
        text: str,
        receive_id_type: str = "open_id",
    ) -> Dict[str, Any]:
        """
        Send a plain text message via Feishu.

        Args:
            receive_id: Recipient ID.
            text: Plain text content.
            receive_id_type: Type of receive_id.

        Returns:
            Send operation result.
        """
        import json
        content = json.dumps({"text": text})
        return self.send_message(receive_id, content, "text", receive_id_type)

    def read_doc(self, document_id: str) -> Dict[str, Any]:
        """
        Read a Feishu document.

        Args:
            document_id: Document ID.

        Returns:
            Document content.
        """
        return self.client.execute("read_doc", document_id)

    def write_doc(
        self,
        document_id: str,
        content: str,
        block_id: str = None,
    ) -> Dict[str, Any]:
        """
        Write to a Feishu document.

        Args:
            document_id: Document ID.
            content: Content to write.
            block_id: Optional block ID to write to.

        Returns:
            Write operation result.
        """
        params = {
            "content": content,
        }
        if block_id:
            params["block_id"] = block_id

        return self.client.execute("write_doc", document_id, params=params)

    def read_calendar(
        self,
        calendar_id: str = "primary",
        start_time: str = None,
        end_time: str = None,
    ) -> Dict[str, Any]:
        """
        Read calendar events.

        Args:
            calendar_id: Calendar ID (default: "primary").
            start_time: Start time filter (ISO8601).
            end_time: End time filter (ISO8601).

        Returns:
            Calendar events data.
        """
        params = {}
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        return self.client.execute("read_calendar", calendar_id, params=params)

    def create_meeting(
        self,
        topic: str,
        start_time: str,
        end_time: str,
        attendees: List[str] = None,
        description: str = None,
    ) -> Dict[str, Any]:
        """
        Create a meeting.

        Args:
            topic: Meeting topic/title.
            start_time: Meeting start time (ISO8601).
            end_time: Meeting end time (ISO8601).
            attendees: Optional list of attendee IDs.
            description: Optional meeting description.

        Returns:
            Created meeting data with meeting_id.
        """
        params = {
            "topic": topic,
            "start_time": start_time,
            "end_time": end_time,
        }
        if attendees:
            params["attendees"] = attendees
        if description:
            params["description"] = description

        return self.client.execute("create_meeting", "calendar", params=params)

    def read_database(
        self,
        table_name: str,
        fields: List[str] = None,
        rows_limit: int = None,
        filter: str = None,
    ) -> Dict[str, Any]:
        """
        Read from a database table.

        Args:
            table_name: Name of the database table.
            fields: List of fields to return.
            rows_limit: Maximum number of rows to return.
            filter: Optional filter condition.

        Returns:
            Query result data.
        """
        params = {}
        if fields:
            params["fields"] = fields
        if rows_limit:
            params["rows_limit"] = rows_limit
        if filter:
            params["filter"] = filter

        return self.client.execute("read_database", table_name, params=params)

    def write_database(
        self,
        table_name: str,
        data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Write to a database table.

        Args:
            table_name: Name of the database table.
            data: List of records to write.

        Returns:
            Write operation result.
        """
        params = {"data": data}
        return self.client.execute("write_database", table_name, params=params)
