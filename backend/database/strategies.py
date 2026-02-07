# ABOUTME: Trading strategy persistence including runs, decisions, and performance tracking
# ABOUTME: Manages strategy CRUD, benchmark snapshots, and strategy execution logs

import logging
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any, List
import json

import psycopg.rows

logger = logging.getLogger(__name__)


class StrategiesMixin:

    def create_strategy(
        self,
        user_id: int,
        portfolio_id: int,
        name: str,
        conditions: Dict[str, Any],
        consensus_mode: str = 'both_agree',
        consensus_threshold: float = 70.0,
        position_sizing: Dict[str, Any] = None,
        exit_conditions: Dict[str, Any] = None,
        schedule_cron: str = '0 9 * * 1-5',
        description: str = None
    ) -> int:
        """Create a new investment strategy."""
        if position_sizing is None:
            position_sizing = {'method': 'equal_weight', 'max_position_pct': 5.0}
        if exit_conditions is None:
            exit_conditions = {}

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO investment_strategies
                (user_id, portfolio_id, name, description, conditions, consensus_mode,
                 consensus_threshold, position_sizing, exit_conditions, schedule_cron)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                user_id, portfolio_id, name, description,
                json.dumps(conditions), consensus_mode, consensus_threshold,
                json.dumps(position_sizing), json.dumps(exit_conditions), schedule_cron
            ))
            strategy_id = cursor.fetchone()[0]
            conn.commit()
            return strategy_id
        finally:
            self.return_connection(conn)

    def update_strategy(
        self,
        user_id: int,
        strategy_id: int,
        name: str = None,
        description: str = None,
        conditions: Dict[str, Any] = None,
        consensus_mode: str = None,
        consensus_threshold: float = None,
        position_sizing: Dict[str, Any] = None,
        exit_conditions: Dict[str, Any] = None,
        schedule_cron: str = None,
        portfolio_id: int = None,
        enabled: bool = None
    ) -> bool:
        """Update an existing investment strategy."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            updates = []
            params = []

            if name is not None:
                updates.append("name = %s")
                params.append(name)



            if description is not None:
                updates.append("description = %s")
                params.append(description)
            if conditions is not None:
                updates.append("conditions = %s")
                params.append(json.dumps(conditions))
            if consensus_mode is not None:
                updates.append("consensus_mode = %s")
                params.append(consensus_mode)
            if consensus_threshold is not None:
                updates.append("consensus_threshold = %s")
                params.append(consensus_threshold)
            if position_sizing is not None:
                updates.append("position_sizing = %s")
                params.append(json.dumps(position_sizing))
            if exit_conditions is not None:
                updates.append("exit_conditions = %s")
                params.append(json.dumps(exit_conditions))
            if schedule_cron is not None:
                updates.append("schedule_cron = %s")
                params.append(schedule_cron)
            if portfolio_id is not None:
                updates.append("portfolio_id = %s")
                params.append(portfolio_id)
            if enabled is not None:
                updates.append("enabled = %s")
                params.append(enabled)

            if not updates:
                return False

            updates.append("updated_at = CURRENT_TIMESTAMP")

            query = f"UPDATE investment_strategies SET {', '.join(updates)} WHERE id = %s AND user_id = %s"
            params.append(strategy_id)
            params.append(user_id)

            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            self.return_connection(conn)

    def get_strategy(self, strategy_id: int) -> Optional[Dict[str, Any]]:
        """Get a strategy by ID."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, user_id, portfolio_id, name, description, conditions,
                       consensus_mode, consensus_threshold, position_sizing,
                       exit_conditions, schedule_cron, enabled, created_at, updated_at
                FROM investment_strategies
                WHERE id = %s
            """, (strategy_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def get_user_strategies(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all strategies for a user with performance summary."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT s.id, s.user_id, s.portfolio_id, s.name, s.description,
                       s.conditions, s.consensus_mode, s.consensus_threshold,
                       s.position_sizing, s.exit_conditions, s.schedule_cron,
                       s.enabled, s.created_at, s.updated_at,
                       p.name as portfolio_name,
                       sp.alpha, sp.portfolio_return_pct, sp.spy_return_pct,
                       sr.last_run_date, sr.last_run_status
                FROM investment_strategies s
                JOIN portfolios p ON s.portfolio_id = p.id
                LEFT JOIN (
                    SELECT DISTINCT ON (strategy_id) strategy_id, alpha, portfolio_return_pct, spy_return_pct
                    FROM strategy_performance
                    ORDER BY strategy_id, snapshot_date DESC
                ) sp ON s.id = sp.strategy_id
                LEFT JOIN (
                    SELECT DISTINCT ON (strategy_id) strategy_id, started_at as last_run_date, status as last_run_status
                    FROM strategy_runs
                    ORDER BY strategy_id, started_at DESC
                ) sr ON s.id = sr.strategy_id
                WHERE s.user_id = %s
                ORDER BY s.created_at DESC
            """, (user_id,))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def get_enabled_strategies(self) -> List[Dict[str, Any]]:
        """Get all enabled strategies (for scheduled execution)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, user_id, portfolio_id, name, conditions,
                       consensus_mode, consensus_threshold, position_sizing,
                       exit_conditions, schedule_cron
                FROM investment_strategies
                WHERE enabled = true
            """)
            return cursor.fetchall()
        finally:
            self.return_connection(conn)



    def delete_strategy(self, strategy_id: int, user_id: int) -> bool:
        """Delete a strategy (verifies ownership). Returns True if deleted."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM investment_strategies
                WHERE id = %s AND user_id = %s
            """, (strategy_id, user_id))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self.return_connection(conn)

    # ============================================================
    # Strategy Run Methods
    # ============================================================

    def create_strategy_run(self, strategy_id: int) -> int:
        """Create a new strategy run record."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO strategy_runs (strategy_id)
                VALUES (%s)
                RETURNING id
            """, (strategy_id,))
            run_id = cursor.fetchone()[0]
            conn.commit()
            return run_id
        finally:
            self.return_connection(conn)

    def get_strategy_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get a strategy run by ID."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, strategy_id, started_at, completed_at, status,
                       stocks_screened, stocks_scored, theses_generated,
                       trades_executed, spy_price, portfolio_value,
                       error_message, run_log
                FROM strategy_runs
                WHERE id = %s
            """, (run_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def get_strategy_runs(self, strategy_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent runs for a strategy."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, strategy_id, started_at, completed_at, status,
                       stocks_screened, stocks_scored, theses_generated,
                       trades_executed, spy_price, portfolio_value, error_message
                FROM strategy_runs
                WHERE strategy_id = %s
                ORDER BY started_at DESC
                LIMIT %s
            """, (strategy_id, limit))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def update_strategy_run(self, run_id: int, **kwargs) -> bool:
        """Update strategy run fields."""
        allowed_fields = {
            'status', 'completed_at', 'stocks_screened', 'stocks_scored',
            'theses_generated', 'trades_executed', 'spy_price',
            'portfolio_value', 'error_message', 'run_log'
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        # JSON-encode run_log if it's a list
        if 'run_log' in updates and isinstance(updates['run_log'], list):
            updates['run_log'] = json.dumps(updates['run_log'])

        set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
        values = list(updates.values()) + [run_id]

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE strategy_runs
                SET {set_clause}
                WHERE id = %s
            """, values)
            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            self.return_connection(conn)

    def append_to_run_log(self, run_id: int, event: Dict[str, Any]) -> bool:
        """Append an event to the run log."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE strategy_runs
                SET run_log = run_log || %s::jsonb
                WHERE id = %s
            """, (json.dumps([event]), run_id))
            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            self.return_connection(conn)

    # ============================================================
    # Strategy Decision Methods
    # ============================================================

    def create_strategy_decision(
        self,
        run_id: int,
        symbol: str,
        lynch_score: float = None,
        lynch_status: str = None,
        buffett_score: float = None,
        buffett_status: str = None,
        consensus_score: float = None,
        consensus_verdict: str = None,
        thesis_verdict: str = None,
        thesis_summary: str = None,
        thesis_full: str = None,
        dcf_fair_value: float = None,
        dcf_upside_pct: float = None,
        final_decision: str = None,
        decision_reasoning: str = None,
        transaction_id: int = None,
        shares_traded: int = None,
        trade_price: float = None,
        position_value: float = None
    ) -> int:
        """Create a strategy decision record."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO strategy_decisions
                (run_id, symbol, lynch_score, lynch_status, buffett_score, buffett_status,
                 consensus_score, consensus_verdict, thesis_verdict, thesis_summary,
                 thesis_full, dcf_fair_value, dcf_upside_pct, final_decision,
                 decision_reasoning, transaction_id, shares_traded, trade_price, position_value)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                run_id, symbol, lynch_score, lynch_status, buffett_score, buffett_status,
                consensus_score, consensus_verdict, thesis_verdict, thesis_summary,
                thesis_full, dcf_fair_value, dcf_upside_pct, final_decision,
                decision_reasoning, transaction_id, shares_traded, trade_price, position_value
            ))
            decision_id = cursor.fetchone()[0]
            conn.commit()
            return decision_id
        finally:
            self.return_connection(conn)

    def update_strategy_decision(self, decision_id: int, **kwargs) -> bool:
        """Update strategy decision fields."""
        allowed_fields = {
            'lynch_score', 'lynch_status', 'buffett_score', 'buffett_status',
            'consensus_score', 'consensus_verdict', 'thesis_verdict',
            'thesis_summary', 'thesis_full', 'dcf_fair_value', 'dcf_upside_pct',
            'final_decision', 'decision_reasoning', 'transaction_id',
            'shares_traded', 'trade_price', 'position_value'
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
        values = list(updates.values()) + [decision_id]

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE strategy_decisions
                SET {set_clause}
                WHERE id = %s
            """, values)
            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            self.return_connection(conn)

    def get_run_decisions(self, run_id: int) -> List[Dict[str, Any]]:
        """Get all decisions for a strategy run."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, run_id, symbol, lynch_score, lynch_status,
                       buffett_score, buffett_status, consensus_score,
                       consensus_verdict, thesis_verdict, thesis_summary,
                       thesis_full, dcf_fair_value, dcf_upside_pct, final_decision,
                       decision_reasoning, transaction_id, shares_traded,
                       trade_price, position_value, created_at
                FROM strategy_decisions
                WHERE run_id = %s
                ORDER BY created_at ASC
            """, (run_id,))
            results = cursor.fetchall()

            # Sanitize NaN values for JSON compatibility
            sanitized_results = []
            for row in results:
                # Convert Row to dict to allow modification
                item = dict(row)
                for key, value in item.items():
                    if isinstance(value, float) and (value != value): # Check for NaN
                        item[key] = None
                sanitized_results.append(item)

            return sanitized_results
        finally:
            self.return_connection(conn)

    # ============================================================
    # Benchmark & Performance Methods
    # ============================================================

    def save_benchmark_snapshot(self, snapshot_date: date, spy_price: float) -> int:
        """Save or update daily SPY benchmark price."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO benchmark_snapshots (snapshot_date, spy_price)
                VALUES (%s, %s)
                ON CONFLICT (snapshot_date) DO UPDATE SET spy_price = EXCLUDED.spy_price
                RETURNING id
            """, (snapshot_date, spy_price))
            snapshot_id = cursor.fetchone()[0]
            conn.commit()
            return snapshot_id
        finally:
            self.return_connection(conn)

    def get_benchmark_snapshot(self, snapshot_date: date) -> Optional[Dict[str, Any]]:
        """Get benchmark snapshot for a specific date."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, snapshot_date, spy_price, created_at
                FROM benchmark_snapshots
                WHERE snapshot_date = %s
            """, (snapshot_date,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def get_benchmark_range(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Get benchmark snapshots for a date range."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT snapshot_date, spy_price
                FROM benchmark_snapshots
                WHERE snapshot_date BETWEEN %s AND %s
                ORDER BY snapshot_date ASC
            """, (start_date, end_date))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def save_strategy_performance(
        self,
        strategy_id: int,
        snapshot_date: date,
        portfolio_value: float,
        portfolio_return_pct: float = None,
        spy_return_pct: float = None,
        alpha: float = None
    ) -> int:
        """Save or update strategy performance snapshot."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO strategy_performance
                (strategy_id, snapshot_date, portfolio_value, portfolio_return_pct, spy_return_pct, alpha)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (strategy_id, snapshot_date) DO UPDATE SET
                    portfolio_value = EXCLUDED.portfolio_value,
                    portfolio_return_pct = EXCLUDED.portfolio_return_pct,
                    spy_return_pct = EXCLUDED.spy_return_pct,
                    alpha = EXCLUDED.alpha
                RETURNING id
            """, (strategy_id, snapshot_date, portfolio_value, portfolio_return_pct, spy_return_pct, alpha))
            perf_id = cursor.fetchone()[0]
            conn.commit()
            return perf_id
        finally:
            self.return_connection(conn)

    def get_strategy_performance(
        self,
        strategy_id: int,
        start_date: date = None,
        end_date: date = None
    ) -> List[Dict[str, Any]]:
        """Get strategy performance history."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            query = """
                SELECT strategy_id, snapshot_date, portfolio_value,
                       portfolio_return_pct, spy_return_pct, alpha
                FROM strategy_performance
                WHERE strategy_id = %s
            """
            params = [strategy_id]

            if start_date:
                query += " AND snapshot_date >= %s"
                params.append(start_date)
            if end_date:
                query += " AND snapshot_date <= %s"
                params.append(end_date)

            query += " ORDER BY snapshot_date ASC"
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def get_strategy_inception_data(self, strategy_id: int) -> Optional[Dict[str, Any]]:
        """Get the first performance record (inception) for a strategy."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT sp.snapshot_date, sp.portfolio_value, bs.spy_price
                FROM strategy_performance sp
                JOIN benchmark_snapshots bs ON sp.snapshot_date = bs.snapshot_date
                WHERE sp.strategy_id = %s
                ORDER BY sp.snapshot_date ASC
                LIMIT 1
            """, (strategy_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)
