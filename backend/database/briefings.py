# ABOUTME: Strategy briefing persistence for post-run summaries
# ABOUTME: Saves and retrieves hybrid template+AI briefings per strategy run

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import psycopg.rows

logger = logging.getLogger(__name__)


class BriefingsMixin:

    def save_briefing(self, briefing_data: Dict[str, Any]) -> int:
        """Save a strategy run briefing. Returns the briefing ID."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO strategy_briefings
                (run_id, strategy_id, portfolio_id, stocks_screened, stocks_scored,
                 theses_generated, trades_executed, portfolio_value, portfolio_return_pct,
                 spy_return_pct, alpha, buys_json, sells_json, holds_json, watchlist_json,
                 executive_summary, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                briefing_data['run_id'],
                briefing_data.get('strategy_id'),
                briefing_data.get('portfolio_id'),
                briefing_data.get('stocks_screened', 0),
                briefing_data.get('stocks_scored', 0),
                briefing_data.get('theses_generated', 0),
                briefing_data.get('trades_executed', 0),
                briefing_data.get('portfolio_value'),
                briefing_data.get('portfolio_return_pct'),
                briefing_data.get('spy_return_pct'),
                briefing_data.get('alpha'),
                briefing_data.get('buys_json', '[]'),
                briefing_data.get('sells_json', '[]'),
                briefing_data.get('holds_json', '[]'),
                briefing_data.get('watchlist_json', '[]'),
                briefing_data.get('executive_summary'),
                datetime.now(timezone.utc),
            ))
            briefing_id = cursor.fetchone()[0]
            conn.commit()
            return briefing_id
        finally:
            self.return_connection(conn)

    def get_briefings_for_portfolio(self, portfolio_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get briefings for a portfolio, most recent first."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, run_id, strategy_id, portfolio_id, stocks_screened, stocks_scored,
                       theses_generated, trades_executed, portfolio_value, portfolio_return_pct,
                       spy_return_pct, alpha, buys_json, sells_json, holds_json, watchlist_json,
                       executive_summary, generated_at
                FROM strategy_briefings
                WHERE portfolio_id = %s
                ORDER BY generated_at DESC
                LIMIT %s
            """, (portfolio_id, limit))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def get_briefing_by_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get a briefing by its strategy run ID."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, run_id, strategy_id, portfolio_id, stocks_screened, stocks_scored,
                       theses_generated, trades_executed, portfolio_value, portfolio_return_pct,
                       spy_return_pct, alpha, buys_json, sells_json, holds_json, watchlist_json,
                       executive_summary, generated_at
                FROM strategy_briefings
                WHERE run_id = %s
            """, (run_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)
