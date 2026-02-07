# ABOUTME: Alert management operations for price and condition-based stock alerts
# ABOUTME: Handles CRUD operations for user-configured trading alerts

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class AlertsMixin:

    def create_alert(self, user_id: int, symbol: str, condition_type: str = 'custom',
                     condition_params: Optional[Dict[str, Any]] = None,
                     frequency: str = 'daily',
                     condition_description: Optional[str] = None,
                     action_type: Optional[str] = None,
                     action_payload: Optional[Dict[str, Any]] = None,
                     portfolio_id: Optional[int] = None,
                     action_note: Optional[str] = None) -> int:
        """
        Create a new user alert.

        Args:
            user_id: User ID creating the alert
            symbol: Stock symbol for the alert
            condition_type: Legacy alert type
            condition_params: Legacy condition parameters
            frequency: How often to check
            condition_description: Natural language description of the alert condition
            action_type: Optional automated trading action (e.g., 'market_buy')
            action_payload: Parameters for the action (e.g., {'quantity': 10})
            portfolio_id: Target portfolio for the trade
            action_note: Note to attach to the trade

        Returns:
            Alert ID
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # Default to empty params if not provided
            if condition_params is None:
                condition_params = {}

            if action_payload is None:
                action_payload = {}

            cursor.execute("""
                INSERT INTO alerts (
                    user_id, symbol, condition_type, condition_params, frequency, status, condition_description,
                    action_type, action_payload, portfolio_id, action_note
                )
                VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                user_id, symbol, condition_type, json.dumps(condition_params), frequency, condition_description,
                action_type, json.dumps(action_payload) if action_payload else None, portfolio_id, action_note
            ))
            alert_id = cursor.fetchone()[0]
            conn.commit()
            return alert_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating alert: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_alerts(self, user_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get alerts for a user, optionally filtered by status."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT id, symbol, condition_type, condition_params, frequency, status,
                       created_at, last_checked, triggered_at, message, condition_description
                FROM alerts
                WHERE user_id = %s
            """
            params = [user_id]

            if status:
                query += " AND status = %s"
                params.append(status)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                alert = dict(zip(columns, row))
                # Parse JSONB params if string (psycopg3 handles this automatically usually but to be safe)
                if isinstance(alert['condition_params'], str):
                    alert['condition_params'] = json.loads(alert['condition_params'])
                results.append(alert)
            return results
        finally:
            self.return_connection(conn)

    def delete_alert(self, alert_id: int, user_id: int) -> bool:
        """Delete an alert (soft delete or hard delete? let's do hard delete for now)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM alerts WHERE id = %s AND user_id = %s", (alert_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting alert: {e}")
            return False
        finally:
            self.return_connection(conn)

    def update_alert_status(self, alert_id: int, status: str, triggered_at: Optional[datetime] = None, message: str = None):
        """Update the status of an alert."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            updates = ["status = %s"]
            params = [status]

            if triggered_at:
                updates.append("triggered_at = %s")
                params.append(triggered_at)

            if message:
                updates.append("message = %s")
                params.append(message)

            # Always update last_checked
            updates.append("last_checked = CURRENT_TIMESTAMP")

            updates.append("WHERE id = %s") # This is wrong logic, WHERE should be outside

            sql = f"UPDATE alerts SET {', '.join(updates)} WHERE id = %s"
            # Now append id to params
            params.append(alert_id)

            # Correct the logic: remove the WHERE clause from updates list
            # Actually, let's rewrite for clarity

            sql = """
                UPDATE alerts
                SET status = %s,
                    last_checked = CURRENT_TIMESTAMP,
                    triggered_at = COALESCE(%s, triggered_at),
                    message = COALESCE(%s, message)
                WHERE id = %s
            """
            cursor.execute(sql, (status, triggered_at, message, alert_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating alert status: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_all_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts for processing by the worker."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, symbol, condition_type, condition_params, frequency, status, last_checked, condition_description,
                       action_type, action_payload, portfolio_id, action_note
                FROM alerts
                WHERE status = 'active'
            """)
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                alert = dict(zip(columns, row))
                if isinstance(alert['condition_params'], str):
                    alert['condition_params'] = json.loads(alert['condition_params'])
                if alert.get('action_payload') and isinstance(alert['action_payload'], str):
                    alert['action_payload'] = json.loads(alert['action_payload'])
                results.append(alert)
            return results
        finally:
            self.return_connection(conn)
