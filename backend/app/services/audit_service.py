"""
Audit Service - Business logic for audit logging and querying.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils import now_iso, parse_iso

logger = logging.getLogger(__name__)

# Alert configuration
ALERT_THRESHOLD = 10  # Max denials in window before alert
ALERT_WINDOW_MINUTES = 5


class AuditServiceError(Exception):
    """Audit service error."""
    def __init__(self, code: str, message: str, details: Optional[Dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AuditService:
    """Audit service for querying audit logs and managing alerts."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def query_audit_logs(
        self,
        agent_id_filter: Optional[str] = None,
        action_filter: Optional[str] = None,
        result_filter: Optional[str] = None,
        task_id_filter: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        requester_agent_id: Optional[str] = None,
        requester_has_manage_agents: bool = False,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Query audit logs with filtering and pagination.

        Args:
            agent_id_filter: Filter by agent ID
            action_filter: Filter by action
            result_filter: Filter by result (ALLOWED/DENIED/ERROR)
            start_time: Start of time range (ISO8601)
            end_time: End of time range (ISO8601)
            page: Page number (1-indexed)
            page_size: Number of items per page
            requester_agent_id: Agent ID making the request
            requester_has_manage_agents: Whether requester has manage_agents capability

        Returns:
            Tuple of (total_count, logs)
        """
        # Build WHERE clause
        conditions = []
        params: Dict[str, Any] = {}

        # Non-manage_agents agents can only see their own logs
        if agent_id_filter:
            conditions.append("agent_id = :agent_id_filter")
            params["agent_id_filter"] = agent_id_filter
        elif not requester_has_manage_agents and requester_agent_id:
            conditions.append("agent_id = :requester_agent_id")
            params["requester_agent_id"] = requester_agent_id

        if action_filter:
            conditions.append("action = :action_filter")
            params["action_filter"] = action_filter

        if result_filter:
            conditions.append("result = :result_filter")
            params["result_filter"] = result_filter

        if task_id_filter:
            conditions.append("task_id = :task_id_filter")
            params["task_id_filter"] = task_id_filter

        if start_time:
            conditions.append("created_at >= :start_time")
            params["start_time"] = start_time

        if end_time:
            conditions.append("created_at <= :end_time")
            params["end_time"] = end_time

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Count total
        count_query = f"""
            SELECT COUNT(*) as total
            FROM audit_logs
            WHERE {where_clause}
        """
        result = await self.session.execute(text(count_query), params)
        total = result.fetchone()[0]

        # Get paginated results
        offset = (page - 1) * page_size
        query = f"""
            SELECT log_id, agent_id, parent_agent_id, task_id, action, resource, result,
                   delegation_chain_summary, created_at
            FROM audit_logs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :page_size OFFSET :offset
        """
        params["page_size"] = page_size
        params["offset"] = offset

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        logs = [
            {
                "log_id": row[0],
                "agent_id": row[1],
                "parent_agent_id": row[2],
                "task_id": row[3],
                "action": row[4],
                "resource": row[5],
                "result": row[6],
                "delegation_chain_summary": row[7],
                "created_at": row[8],
            }
            for row in rows
        ]

        return total, logs

    async def get_audit_log_detail(
        self,
        log_id: str,
        requester_agent_id: Optional[str] = None,
        requester_has_manage_agents: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed audit log by ID.

        Args:
            log_id: Audit log ID
            requester_agent_id: Agent ID making the request
            requester_has_manage_agents: Whether requester has manage_agents capability

        Returns:
            Audit log detail or None if not found
        """
        query = """
            SELECT log_id, agent_id, parent_agent_id, task_id, action, resource, result,
                   token_chain, request_context, task_context, delegation_chain_summary,
                   error_detail, created_at
            FROM audit_logs
            WHERE log_id = :log_id
        """
        result = await self.session.execute(text(query), {"log_id": log_id})
        row = result.fetchone()

        if not row:
            return None

        # Check authorization
        if not requester_has_manage_agents and requester_agent_id != row[1]:
            return None

        return {
            "log_id": row[0],
            "agent_id": row[1],
            "parent_agent_id": row[2],
            "task_id": row[3],
            "action": row[4],
            "resource": row[5],
            "result": row[6],
            "token_chain": json.loads(row[7]) if row[7] else [],
            "request_context": json.loads(row[8]) if row[8] else {},
            "task_context": json.loads(row[9]) if row[9] else {},
            "delegation_chain_summary": row[10],
            "error_detail": row[11],
            "created_at": row[12],
        }

    async def get_delegation_graph(
        self,
        requester_has_manage_agents: bool = False,
    ) -> Dict[str, Any]:
        """
        Get delegation graph for visualization.

        Args:
            requester_has_manage_agents: Whether requester has manage_agents capability

        Returns:
            Dict with nodes and edges
        """
        if not requester_has_manage_agents:
            raise AuditServiceError(
                "PERMISSION_DENIED",
                "manage_agents capability required to view delegation graph"
            )

        agents_query = """
            SELECT agent_id, name, trust_level, status
            FROM agents
            WHERE status = 'active'
        """
        result = await self.session.execute(text(agents_query))
        agent_rows = result.fetchall()

        nodes = [
            {
                "id": row[0],
                "name": row[1],
                "trust_level": row[2],
                "status": row[3],
            }
            for row in agent_rows
        ]

        delegation_query = """
            SELECT delegation_id, from_agent_id, to_agent_id, capability,
                   attenuations, status, expires_at
            FROM delegation_tokens
            WHERE status = 'active' AND expires_at > :now
        """
        result = await self.session.execute(
            text(delegation_query),
            {"now": now_iso()}
        )
        delegation_rows = result.fetchall()

        edges = [
            {
                "from_agent": row[1],
                "to_agent": row[2],
                "delegation_id": row[0],
                "capability": row[3],
                "attenuations": json.loads(row[4]) if row[4] else {},
                "status": row[5],
                "expires_at": row[6],
            }
            for row in delegation_rows
        ]

        return {
            "nodes": nodes,
            "edges": edges,
        }

    async def get_task_trace(
        self,
        task_id: str,
        requester_agent_id: Optional[str] = None,
        requester_has_manage_agents: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get full trace of all audit logs for a specific task ID.
        
        Args:
            task_id: Task ID to trace
            requester_agent_id: Agent ID making the request
            requester_has_manage_agents: Whether requester has manage_agents capability
            
        Returns:
            List of audit logs in chronological order
        """
        query = """
            SELECT log_id, agent_id, parent_agent_id, task_id, action, resource, 
                   result, request_context, task_context, error_detail, created_at
            FROM audit_logs
            WHERE task_id = :task_id
            ORDER BY created_at ASC
        """
        
        result = await self.session.execute(text(query), {"task_id": task_id})
        rows = result.fetchall()
        
        logs = []
        for row in rows:
            # 权限校验：非管理员只能查看自己参与的任务
            if not requester_has_manage_agents and requester_agent_id:
                if row[1] != requester_agent_id and row[2] != requester_agent_id:
                    continue
            
            logs.append({
                "log_id": row[0],
                "agent_id": row[1],
                "parent_agent_id": row[2],
                "task_id": row[3],
                "action": row[4],
                "resource": row[5],
                "result": row[6],
                "request_context": json.loads(row[7]) if row[7] else {},
                "task_context": json.loads(row[8]) if row[8] else {},
                "error_detail": row[9],
                "created_at": row[10],
            })
        
        return logs

    async def list_recent_tasks(
        self,
        limit: int = 50,
        requester_agent_id: Optional[str] = None,
        requester_has_manage_agents: bool = False,
    ) -> List[Dict[str, Any]]:
        """Recent distinct task_ids for dashboard picker (newest first)."""
        limit = min(max(limit, 1), 100)
        if requester_has_manage_agents:
            query = """
                SELECT task_id, COUNT(*) AS step_count, MAX(created_at) AS last_at
                FROM audit_logs
                WHERE task_id IS NOT NULL AND TRIM(task_id) != ''
                GROUP BY task_id
                ORDER BY last_at DESC
                LIMIT :limit
            """
            result = await self.session.execute(text(query), {"limit": limit})
        else:
            if not requester_agent_id:
                return []
            query = """
                SELECT task_id, COUNT(*) AS step_count, MAX(created_at) AS last_at
                FROM audit_logs
                WHERE task_id IS NOT NULL AND TRIM(task_id) != ''
                  AND task_id IN (
                      SELECT DISTINCT task_id FROM audit_logs
                      WHERE task_id IS NOT NULL AND TRIM(task_id) != ''
                        AND (agent_id = :aid OR parent_agent_id = :aid)
                  )
                GROUP BY task_id
                ORDER BY last_at DESC
                LIMIT :limit
            """
            result = await self.session.execute(
                text(query),
                {"limit": limit, "aid": requester_agent_id},
            )
        rows = result.fetchall()
        return [
            {
                "task_id": row[0],
                "step_count": row[1],
                "last_at": row[2],
            }
            for row in rows
        ]

    async def get_alert_status(
        self,
        requester_has_manage_agents: bool = False,
    ) -> Dict[str, Any]:
        """
        Get current alert status.

        Args:
            requester_has_manage_agents: Whether requester has manage_agents capability

        Returns:
            Alert status information
        """
        if not requester_has_manage_agents:
            raise AuditServiceError(
                "PERMISSION_DENIED",
                "manage_agents capability required to view alert status"
            )

        # Count recent denials
        cutoff_time = (datetime.utcnow() - timedelta(minutes=ALERT_WINDOW_MINUTES)).isoformat() + "Z"
        query = """
            SELECT COUNT(*) as denial_count
            FROM audit_logs
            WHERE result = 'DENIED' AND created_at >= :cutoff_time
        """
        result = await self.session.execute(text(query), {"cutoff_time": cutoff_time})
        denial_count = result.fetchone()[0]

        return {
            "enabled": True,
            "threshold": ALERT_THRESHOLD,
            "window_minutes": ALERT_WINDOW_MINUTES,
            "recent_denial_count": denial_count,
            "is_above_threshold": denial_count > ALERT_THRESHOLD,
            "last_checked_at": now_iso(),
        }

    async def check_and_log_alert(
        self,
        agent_id: str,
        action: str,
        resource: str,
        error_detail: str,
    ) -> bool:
        """
        Check if denial rate is above threshold and log alert if so.

        Args:
            agent_id: Agent that was denied
            action: Action that was denied
            resource: Resource that was denied
            error_detail: Error detail

        Returns:
            True if alert was triggered
        """
        # Count recent denials for this agent
        cutoff_time = (datetime.utcnow() - timedelta(minutes=ALERT_WINDOW_MINUTES)).isoformat() + "Z"
        query = """
            SELECT COUNT(*) as denial_count
            FROM audit_logs
            WHERE agent_id = :agent_id
              AND result = 'DENIED'
              AND created_at >= :cutoff_time
        """
        result = await self.session.execute(
            text(query),
            {"agent_id": agent_id, "cutoff_time": cutoff_time}
        )
        denial_count = result.fetchone()[0]

        if denial_count > ALERT_THRESHOLD:
            logger.warning(
                f"HIGH DENIAL RATE ALERT: Agent {agent_id} has {denial_count} "
                f"denials in the last {ALERT_WINDOW_MINUTES} minutes "
                f"(threshold: {ALERT_THRESHOLD}). "
                f"Last denial: {action} on {resource} - {error_detail}"
            )
            return True

        return False
