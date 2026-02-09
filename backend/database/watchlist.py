# ABOUTME: Watchlist management for users
# ABOUTME: Handles adding, removing, and retrieving symbols from user watchlists

import logging
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)

class WatchlistMixin:
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
