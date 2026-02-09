# ABOUTME: User account management and preferences storage
# ABOUTME: Handles authentication, watchlists, and user settings like theme and character

import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import psycopg.rows

logger = logging.getLogger(__name__)


class UsersMixin:

    def create_user(self, google_id: str, email: str, name: str = None, picture: str = None) -> int:
        """Create a new user and return their user_id"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (google_id, email, name, picture, created_at, last_login, theme)
                VALUES (%s, %s, %s, %s, %s, %s, 'midnight')
                ON CONFLICT (google_id) DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    picture = EXCLUDED.picture,
                    last_login = EXCLUDED.last_login
                RETURNING id
            """, (google_id, email, name, picture, datetime.now(), datetime.now()))
            user_id = cursor.fetchone()[0]
            conn.commit()
            return user_id
        finally:
            self.return_connection(conn)

    def create_user_with_password(self, email: str, password_hash: str, name: str = None, verification_code: str = None, code_expires_at: datetime = None) -> int:
        """Create a new user with email/password and return their user_id"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # is_verified defaults to False for password users (if code provided), True otherwise
            is_verified = False if verification_code else True

            cursor.execute("""
                INSERT INTO users (email, password_hash, name, created_at, last_login, is_verified, verification_code, code_expires_at, theme)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'midnight')
                RETURNING id
            """, (email, password_hash, name, datetime.now(), datetime.now(), is_verified, verification_code, code_expires_at))
            user_id = cursor.fetchone()[0]
            conn.commit()
            return user_id
        finally:
            self.return_connection(conn)

    def verify_user_otp(self, email: str, code: str) -> bool:
        """Verify a user by email and OTP code"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # Debug: Check what's in the DB for this email
            cursor.execute("""
                SELECT verification_code, code_expires_at, is_verified, NOW()
                FROM users WHERE email = %s
            """, (email,))
            debug_row = cursor.fetchone()
            if debug_row:
                logger.info(f"OTP DEBUG: Email={email}, StoredCode={debug_row[0]}, Expires={debug_row[1]}, Verified={debug_row[2]}, DB_NOW={debug_row[3]}")
                logger.info(f"OTP DEBUG: InputCode={code}")
            else:
                logger.info(f"OTP DEBUG: Email={email} NOT FOUND")

            # Check if code matches and is not expired
            cursor.execute("""
                SELECT id FROM users
                WHERE email = %s
                AND verification_code = %s
                AND code_expires_at > NOW()
                AND is_verified = FALSE
            """, (email, code))

            user = cursor.fetchone()

            if user:
                # Mark as verified and clear code
                cursor.execute("""
                    UPDATE users
                    SET is_verified = TRUE, verification_code = NULL, code_expires_at = NULL
                    WHERE id = %s
                """, (user[0],))
                conn.commit()
                return True

            return False
        finally:
            self.return_connection(conn)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def get_user_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """Get user by Google ID"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("SELECT * FROM users WHERE google_id = %s", (google_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by user_id"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def update_last_login(self, user_id: int):
        """Update user's last login timestamp"""
        sql = "UPDATE users SET last_login = %s WHERE id = %s"
        args = (datetime.now(), user_id)
        self.write_queue.put((sql, args))

    def get_user_character(self, user_id: int) -> str:
        """Get user's active investment character"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT active_character FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else 'lynch'
        finally:
            self.return_connection(conn)

    def set_user_character(self, user_id: int, character_id: str):
        """Set user's active investment character"""
        sql = "UPDATE users SET active_character = %s WHERE id = %s"
        args = (character_id, user_id)
        self.write_queue.put((sql, args))

    def get_user_expertise_level(self, user_id: int) -> str:
        """Get user's expertise level"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT expertise_level FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else 'practicing'
        finally:
            self.return_connection(conn)

    def set_user_expertise_level(self, user_id: int, expertise_level: str):
        """Set user's expertise level"""
        sql = "UPDATE users SET expertise_level = %s WHERE id = %s"
        args = (expertise_level, user_id)
        self.write_queue.put((sql, args))

    def get_user_theme(self, user_id: int) -> str:
        """Get user's active theme"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT theme FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else 'light'
        finally:
            self.return_connection(conn)

    def set_user_theme(self, user_id: int, theme: str):
        """Set user's active theme"""
        sql = "UPDATE users SET theme = %s WHERE id = %s"
        args = (theme, user_id)
        self.write_queue.put((sql, args))

    def mark_onboarding_complete(self, user_id: int):
        """Mark user as having completed the onboarding flow"""
        sql = "UPDATE users SET has_completed_onboarding = TRUE WHERE id = %s"
        args = (user_id,)
        self.write_queue.put((sql, args))
        self.flush()

    def add_to_watchlist(self, user_id: int, symbol: str):
        sql = """
            INSERT INTO watchlist (user_id, symbol, added_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, symbol) DO NOTHING
        """
        args = (user_id, symbol, datetime.now())
        self.write_queue.put((sql, args))

    def remove_from_watchlist(self, user_id: int, symbol: str):
        sql = "DELETE FROM watchlist WHERE user_id = %s AND symbol = %s"
        args = (user_id, symbol)
        self.write_queue.put((sql, args))

    def get_watchlist(self, user_id: int) -> List[str]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM watchlist WHERE user_id = %s ORDER BY added_at DESC", (user_id,))
            symbols = [row[0] for row in cursor.fetchall()]
            return symbols
        finally:
            self.return_connection(conn)

    def log_user_event(self, user_id: Optional[int], event_type: str, path: str, method: str,
                       query_params: Optional[Dict[str, Any]] = None,
                       request_body: Optional[Dict[str, Any]] = None,
                       ip_address: Optional[str] = None,
                       user_agent: Optional[str] = None,
                       status_code: Optional[int] = None,
                       duration_ms: Optional[int] = None):
        """Log a user interaction event to the database asynchronously"""
        sql = """
            INSERT INTO user_events (
                user_id, event_type, path, method, query_params,
                request_body, ip_address, user_agent, status_code, duration_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        # Convert Dict to JSON string for Postgres JSONB columns
        # psycopg3 handles dict -> jsonb automatically if we use standard dumpers,
        # but here we're using raw SQL with parameters.
        # Actually, psycopg3 handles dicts as JSON by default if the column is JSONB.
        # But we'll be safe and ensure they are JSON strings or None.

        args = (
            user_id,
            event_type,
            path,
            method,
            json.dumps(query_params) if query_params else None,
            json.dumps(request_body) if request_body else None,
            ip_address,
            user_agent,
            status_code,
            duration_ms
        )

        self.write_queue.put((sql, args))
