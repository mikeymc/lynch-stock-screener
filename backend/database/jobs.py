# ABOUTME: Background job queue management for async task processing
# ABOUTME: Handles job creation, claiming, progress tracking, and completion
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime, timezone, date
import json

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

class JobsMixin:

    def create_background_job(self, job_type: str, params: Dict[str, Any], tier: str = 'light') -> int:
        """Create a new background job and return its ID"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO background_jobs (job_type, params, status, tier, created_at)
                VALUES (%s, %s, 'pending', %s, NOW())
                RETURNING id
            """, (job_type, json.dumps(params, cls=DateTimeEncoder), tier))
            job_id = cursor.fetchone()[0]
            conn.commit()
            return job_id
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def create_feedback(self,
                        user_id: Optional[int],
                        email: Optional[str],
                        feedback_text: str,
                        screenshot_data: Optional[str] = None,
                        page_url: Optional[str] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> int:
        """Create a new feedback entry"""
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_feedback (
                    user_id, email, feedback_text, screenshot_data, page_url, metadata, status
                ) VALUES (%s, %s, %s, %s, %s, %s, 'new')
                RETURNING id
            """, (
                user_id,
                email,
                feedback_text,
                screenshot_data,
                page_url,
                json.dumps(metadata, cls=DateTimeEncoder) if metadata else None
            ))
            feedback_id = cursor.fetchone()[0]
            conn.commit()
            return feedback_id
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)
    def get_all_feedback(self) -> List[Dict[str, Any]]:
        """Get all feedback entries with user details"""
        conn = self.get_connection()
        try:
            from psycopg.rows import dict_row
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute("""
                SELECT 
                    f.id,
                    f.user_id,
                    f.email,
                    f.feedback_text,
                    f.screenshot_data,
                    f.page_url,
                    f.metadata,
                    f.status,
                    f.created_at,
                    u.name as user_name
                FROM app_feedback f
                LEFT JOIN users u ON f.user_id = u.id
                ORDER BY f.created_at DESC
            """)
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def get_feedback_count(self) -> int:
        """Get count of unread/new feedback"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM app_feedback WHERE status = 'new'")
            return cursor.fetchone()[0]
        finally:
            self.return_connection(conn)


    def get_background_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get a background job by ID"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, job_type, status, claimed_by, claimed_at, claim_expires_at,
                       params, progress_pct, progress_message, processed_count, total_count,
                       result, error_message, created_at, started_at, completed_at
                FROM background_jobs
                WHERE id = %s
            """, (job_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'id': row[0],
                'job_type': row[1],
                'status': row[2],
                'claimed_by': row[3],
                'claimed_at': row[4],
                'claim_expires_at': row[5],
                'params': row[6] if isinstance(row[6], dict) else json.loads(row[6]) if row[6] else {},
                'progress_pct': row[7],
                'progress_message': row[8],
                'processed_count': row[9],
                'total_count': row[10],
                'result': row[11] if isinstance(row[11], dict) else json.loads(row[11]) if row[11] else None,
                'error_message': row[12],
                'created_at': row[13],
                'started_at': row[14],
                'completed_at': row[15]
            }
        finally:
            self.return_connection(conn)

    def claim_pending_job(self, worker_id: str, tier: str = 'light', claim_minutes: int = 10) -> Optional[Dict[str, Any]]:
        """
        Atomically claim a pending job using FOR UPDATE SKIP LOCKED.
        Returns the claimed job or None if no pending jobs available.
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                WITH claimable AS (
                    SELECT id FROM background_jobs
                    WHERE status = 'pending'
                    AND tier = %s
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE background_jobs
                SET status = 'claimed',
                    claimed_by = %s,
                    claimed_at = NOW(),
                    claim_expires_at = NOW() + INTERVAL '%s minutes'
                WHERE id = (SELECT id FROM claimable)
                RETURNING id, job_type, status, claimed_by, claimed_at, claim_expires_at,
                          params, progress_pct, progress_message, processed_count, total_count,
                          result, error_message, created_at, started_at, completed_at, tier
            """, (tier, worker_id, claim_minutes))

            row = cursor.fetchone()
            conn.commit()

            if not row:
                return None

            return {
                'id': row[0],
                'job_type': row[1],
                'status': row[2],
                'claimed_by': row[3],
                'claimed_at': row[4],
                'claim_expires_at': row[5],
                'params': row[6] if isinstance(row[6], dict) else json.loads(row[6]) if row[6] else {},
                'progress_pct': row[7],
                'progress_message': row[8],
                'processed_count': row[9],
                'total_count': row[10],
                'result': row[11] if isinstance(row[11], dict) else json.loads(row[11]) if row[11] else None,
                'error_message': row[12],
                'created_at': row[13],
                'started_at': row[14],
                'completed_at': row[15],
                "tier": row[16]
            }
        finally:
            self.return_connection(conn)

    def update_job_progress(self, job_id: int, progress_pct: int = None,
                           progress_message: str = None, processed_count: int = None,
                           total_count: int = None):
        """Update job progress information"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            updates = []
            values = []

            if progress_pct is not None:
                updates.append("progress_pct = %s")
                values.append(progress_pct)
            if progress_message is not None:
                updates.append("progress_message = %s")
                values.append(progress_message)
            if processed_count is not None:
                updates.append("processed_count = %s")
                values.append(processed_count)
            if total_count is not None:
                updates.append("total_count = %s")
                values.append(total_count)

            if updates:
                values.append(job_id)
                cursor.execute(f"""
                    UPDATE background_jobs
                    SET {', '.join(updates)}
                    WHERE id = %s
                """, tuple(values))
                conn.commit()
        finally:
            self.return_connection(conn)

    def update_job_status(self, job_id: int, status: str):
        """Update job status"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET status = %s,
                    started_at = CASE WHEN %s = 'running' AND started_at IS NULL THEN NOW() ELSE started_at END
                WHERE id = %s
            """, (status, status, job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def update_job_heartbeat(self, job_id: int, extend_minutes: int = 10):
        """Extend the claim expiration time for a running job"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET claim_expires_at = NOW() + INTERVAL '%s minutes'
                WHERE id = %s
            """, (extend_minutes, job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def complete_job(self, job_id: int, result: Dict[str, Any]):
        """Mark job as completed with result"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET status = 'completed',
                    result = %s,
                    completed_at = NOW(),
                    progress_pct = 100
                WHERE id = %s
            """, (json.dumps(result, cls=DateTimeEncoder), job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def fail_job(self, job_id: int, error_message: str):
        """Mark job as failed with error message"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET status = 'failed',
                    error_message = %s,
                    completed_at = NOW()
                WHERE id = %s
            """, (error_message, job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def cancel_job(self, job_id: int):
        """Cancel a job and release its claim"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Set status to cancelled and clear the claim
            cursor.execute("""
                UPDATE background_jobs
                SET status = 'cancelled',
                    completed_at = NOW(),
                    claimed_by = NULL,
                    claimed_at = NULL
                WHERE id = %s
            """, (job_id,))
            conn.commit()
        finally:
            self.return_connection(conn)

    def extend_job_claim(self, job_id: int, minutes: int = 10):
        """Extend job claim expiry (heartbeat)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET claim_expires_at = NOW() + INTERVAL '%s minutes'
                WHERE id = %s
            """, (minutes, job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_pending_jobs_count(self) -> int:
        """Get count of pending jobs"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM background_jobs WHERE status = 'pending'")
            count = cursor.fetchone()[0]
            return count
        finally:
            self.return_connection(conn)

    def release_job(self, job_id: int):
        """Release a claimed job back to pending status"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET status = 'pending',
                    claimed_by = NULL,
                    claimed_at = NULL,
                    claim_expires_at = NULL
                WHERE id = %s
            """, (job_id,))
            conn.commit()
        finally:
            self.return_connection(conn)
