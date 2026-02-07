# ABOUTME: Screening session management and result persistence
# ABOUTME: Handles screening workflows, result scoring, and backtesting data

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import json

logger = logging.getLogger(__name__)


class ScreeningMixin:

    def create_session(self, algorithm: str, total_count: int, total_analyzed: int = 0, pass_count: int = 0, close_count: int = 0, fail_count: int = 0) -> int:
        """Create a new screening session with initial status"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO screening_sessions (
                    created_at, algorithm, total_count, processed_count,
                    total_analyzed, pass_count, close_count, fail_count, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (datetime.now(), algorithm, total_count, 0, total_analyzed, pass_count, close_count, fail_count, 'running'))
            session_id = cursor.fetchone()[0]
            conn.commit()
            return session_id
        finally:
            self.return_connection(conn)

    def update_session_progress(self, session_id: int, processed_count: int, current_symbol: str = None):
        """Update screening session progress"""
        sql = """
            UPDATE screening_sessions
            SET processed_count = %s, current_symbol = %s
            WHERE id = %s
        """
        args = (processed_count, current_symbol, session_id)
        self.write_queue.put((sql, args))

    def update_session_total_count(self, session_id: int, total_count: int):
        """Update session total count"""
        sql = "UPDATE screening_sessions SET total_count = %s WHERE id = %s"
        args = (total_count, session_id)
        self.write_queue.put((sql, args))

    def complete_session(self, session_id: int, total_analyzed: int, pass_count: int, close_count: int, fail_count: int):
        """Mark session as complete with final counts"""
        sql = """
            UPDATE screening_sessions
            SET status = 'complete',
                total_analyzed = %s,
                pass_count = %s,
                close_count = %s,
                fail_count = %s,
                processed_count = total_count
            WHERE id = %s
        """
        args = (total_analyzed, pass_count, close_count, fail_count, session_id)
        self.write_queue.put((sql, args))

    def cancel_session(self, session_id: int):
        """Mark session as cancelled"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE screening_sessions
                SET status = 'cancelled'
                WHERE id = %s
            """, (session_id,))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_session_progress(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get current progress of a screening session"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_at, algorithm, status, processed_count, total_count,
                       current_symbol, total_analyzed, pass_count, close_count, fail_count
                FROM screening_sessions
                WHERE id = %s
            """, (session_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'id': row[0],
                'created_at': row[1],
                'algorithm': row[2],
                'status': row[3],
                'processed_count': row[4],
                'total_count': row[5],
                'current_symbol': row[6],
                'total_analyzed': row[7],
                'pass_count': row[8],
                'close_count': row[9],
                'fail_count': row[10]
            }
        finally:
            self.return_connection(conn)

    # DEPRECATED: def get_session_results(self, session_id: int) -> List[Dict[str, Any]]:
        # """Get all results for a screening session"""
        # conn = self.get_connection()
        # try:
            # cursor = conn.cursor()
            # cursor.execute("""
                # SELECT symbol, company_name, country, market_cap, sector, ipo_year,
                       # price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership,
                       # dividend_yield, earnings_cagr, revenue_cagr, consistency_score,
                       # peg_status, debt_status, institutional_ownership_status, overall_status,
                       # overall_score, scored_at
                # FROM screening_results
                # WHERE session_id = %s
                # ORDER BY id ASC
            # """, (session_id,))
            # rows = cursor.fetchall()

            # results = []
            # for row in rows:
                # results.append({
                    # 'symbol': row[0],
                    # 'company_name': row[1],
                    # 'country': row[2],
                    # 'market_cap': row[3],
                    # 'sector': row[4],
                    # 'ipo_year': row[5],
                    # 'price': row[6],
                    # 'pe_ratio': row[7],
                    # 'peg_ratio': row[8],
                    # 'debt_to_equity': row[9],
                    # 'institutional_ownership': row[10],
                    # 'dividend_yield': row[11],
                    # 'earnings_cagr': row[12],
                    # 'revenue_cagr': row[13],
                    # 'consistency_score': row[14],
                    # 'peg_status': row[15],
                    # 'debt_status': row[16],
                    # 'institutional_ownership_status': row[17],
                    # 'overall_status': row[18],
                    # 'overall_score': row[19],
                    # 'scored_at': row[20]
                # })

            # return results
        # finally:
            # self.return_connection(conn)

    def save_screening_result(self, session_id: int, result_data: Dict[str, Any]):
        sql_delete = """
            DELETE FROM screening_results
            WHERE session_id = %s AND symbol = %s
        """
        args_delete = (session_id, result_data.get('symbol'))
        self.write_queue.put((sql_delete, args_delete))

        sql_insert = """
            INSERT INTO screening_results
            (session_id, symbol, company_name, country, market_cap, sector, ipo_year,
             price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership, dividend_yield,
             earnings_cagr, revenue_cagr, consistency_score,
             peg_status, peg_score, debt_status, debt_score,
             institutional_ownership_status, institutional_ownership_score,
             overall_status, overall_score, scored_at,
             roe, owner_earnings, debt_to_earnings, gross_margin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        args_insert = (
            session_id,
            result_data.get('symbol'),
            result_data.get('company_name'),
            result_data.get('country'),
            result_data.get('market_cap'),
            result_data.get('sector'),
            result_data.get('ipo_year'),
            result_data.get('price'),
            result_data.get('pe_ratio'),
            result_data.get('peg_ratio'),
            result_data.get('debt_to_equity'),
            result_data.get('institutional_ownership'),
            result_data.get('dividend_yield'),
            result_data.get('earnings_cagr'),
            result_data.get('revenue_cagr'),
            result_data.get('consistency_score'),
            result_data.get('peg_status'),
            result_data.get('peg_score'),
            result_data.get('debt_status'),
            result_data.get('debt_score'),
            result_data.get('institutional_ownership_status'),
            result_data.get('institutional_ownership_score'),
            result_data.get('overall_status'),
            result_data.get('overall_score'),
            datetime.now(),
            result_data.get('roe'),
            result_data.get('owner_earnings'),
            result_data.get('debt_to_earnings'),
            result_data.get('gross_margin')
        )
        self.write_queue.put((sql_insert, args_insert))

    def get_latest_session(self, search: str = None, page: int = 1, limit: int = 100,
                           sort_by: str = 'overall_status', sort_dir: str = 'asc',
                           country_filter: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the most recent screening session with paginated, sorted results.

        Args:
            search: Optional search filter for symbol/company name
            page: Page number for pagination (1-indexed)
            limit: Results per page
            sort_by: Column to sort by
            sort_dir: Sort direction ('asc' or 'desc')
            country_filter: Optional country code to filter by (e.g., 'US')
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, created_at, total_analyzed, pass_count, close_count, fail_count
                FROM screening_sessions
                ORDER BY created_at DESC
                LIMIT 1
            """)
            session_row = cursor.fetchone()

            if not session_row:
                return None

            session_id = session_row[0]

            # Whitelist of allowed sort columns to prevent SQL injection
            allowed_sort_columns = {
                'symbol', 'company_name', 'market_cap', 'price', 'pe_ratio', 'peg_ratio',
                'debt_to_equity', 'institutional_ownership', 'dividend_yield',
                'earnings_cagr', 'revenue_cagr', 'consistency_score', 'overall_status',
                'overall_score', 'peg_score', 'debt_score', 'institutional_ownership_score',
                'roe', 'owner_earnings', 'debt_to_earnings', 'gross_margin'
            }

            # Validate sort parameters
            if sort_by not in allowed_sort_columns:
                sort_by = 'overall_score'
            if sort_dir.lower() not in ('asc', 'desc'):
                sort_dir = 'desc'

            # Build base query
            base_query = """
                SELECT symbol, company_name, country, market_cap, sector, ipo_year,
                       price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership, dividend_yield,
                       earnings_cagr, revenue_cagr, consistency_score,
                       peg_status, peg_score, debt_status, debt_score,
                       institutional_ownership_status, institutional_ownership_score, overall_status,
                       overall_score,
                       roe, owner_earnings, debt_to_earnings, gross_margin
                FROM screening_results
                WHERE session_id = %s
            """
            params = [session_id]

            # Apply country filter if provided
            if country_filter:
                base_query += " AND country = %s"
                params.append(country_filter)

            if search:
                base_query += " AND (symbol ILIKE %s OR company_name ILIKE %s)"
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])

            # Get total count for pagination
            count_query = f"SELECT COUNT(*) FROM ({base_query}) AS filtered"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

            # Add ordering and pagination
            # Special handling for overall_status - use CASE to rank properly
            # Also use status ranking as fallback when overall_score is NULL
            status_rank_expr = """CASE overall_status
                WHEN 'STRONG_BUY' THEN 1
                WHEN 'PASS' THEN 1
                WHEN 'BUY' THEN 2
                WHEN 'CLOSE' THEN 2
                WHEN 'HOLD' THEN 3
                WHEN 'CAUTION' THEN 4
                WHEN 'AVOID' THEN 5
                WHEN 'FAIL' THEN 5
                ELSE 6
            END"""

            if sort_by == 'overall_status':
                # Use status ranking for text-based status sorting
                # Secondary sort by overall_score for deterministic ordering within status groups
                order_expr = f"{status_rank_expr} {sort_dir.upper()}, COALESCE(overall_score, 0) DESC"
            elif sort_by == 'overall_score':
                # For overall_score, fall back to status ranking when score is NULL
                order_expr = f"COALESCE(overall_score, 0) {sort_dir.upper()}, {status_rank_expr} ASC"
            else:
                # Handle NULL values in sorting - always put them last (IS NULL ASC = false first, true last)
                order_expr = f"{sort_by} IS NULL ASC, {sort_by} {sort_dir.upper()}"

            query = base_query + f" ORDER BY {order_expr}"

            # Add pagination
            offset = (page - 1) * limit
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, params)
            result_rows = cursor.fetchall()

            results = []
            for row in result_rows:
                results.append({
                    'symbol': row[0],
                    'company_name': row[1],
                    'country': row[2],
                    'market_cap': row[3],
                    'sector': row[4],
                    'ipo_year': row[5],
                    'price': row[6],
                    'pe_ratio': row[7],
                    'peg_ratio': row[8],
                    'debt_to_equity': row[9],
                    'institutional_ownership': row[10],
                    'dividend_yield': row[11],
                    'earnings_cagr': row[12],
                    'revenue_cagr': row[13],
                    'consistency_score': row[14],
                    'peg_status': row[15],
                    'peg_score': row[16],
                    'debt_status': row[17],
                    'debt_score': row[18],
                    'institutional_ownership_status': row[19],
                    'institutional_ownership_score': row[20],
                    'overall_status': row[21],
                    'overall_score': row[22],
                    'roe': row[23],
                    'owner_earnings': row[24],
                    'debt_to_earnings': row[25],
                    'gross_margin': row[26]
                })

            # Get status counts for full session (respects country filter, not search/pagination)
            status_count_query = """
                SELECT overall_status, COUNT(*) as count
                FROM screening_results
                WHERE session_id = %s
            """
            status_count_params = [session_id]

            if country_filter:
                status_count_query += " AND country = %s"
                status_count_params.append(country_filter)

            status_count_query += " GROUP BY overall_status"

            cursor.execute(status_count_query, status_count_params)
            status_rows = cursor.fetchall()
            status_counts = {row[0]: row[1] for row in status_rows if row[0]}

            return {
                'session_id': session_id,
                'created_at': session_row[1],
                'total_analyzed': session_row[2],
                'pass_count': session_row[3],
                'close_count': session_row[4],
                'fail_count': session_row[5],
                'results': results,
                'total_count': total_count,
                'page': page,
                'limit': limit,
                'total_pages': (total_count + limit - 1) // limit,  # Ceiling division
                'status_counts': status_counts  # e.g. {'STRONG_BUY': 50, 'BUY': 100, ...}
            }
        finally:
            self.return_connection(conn)

    # DEPRECATED: def cleanup_old_sessions(self, keep_count: int = 2):
        # conn = self.get_connection()
        # try:
            # cursor = conn.cursor()

            # cursor.execute("""
                # SELECT id FROM screening_sessions
                # ORDER BY created_at DESC
                # OFFSET %s
            # """, (keep_count,))
            # old_session_ids = [row[0] for row in cursor.fetchall()]

            # for session_id in old_session_ids:
                # cursor.execute("DELETE FROM screening_sessions WHERE id = %s", (session_id,))

            # conn.commit()
        # finally:
            # self.return_connection(conn)

    def get_screening_symbols(self, session_id: int) -> List[str]:
        """Get all symbols from a specific screening session."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT symbol FROM screening_results WHERE session_id = %s",
                (session_id,)
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.return_connection(conn)

    def update_screening_result_scores(
        self,
        symbol: str,
        overall_score: float = None,
        overall_status: str = None,
        peg_score: float = None,
        debt_score: float = None,
        institutional_ownership_score: float = None,
        scored_at: datetime = None
    ):
        """Update scores for all screening_results rows matching a symbol."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE screening_results
                SET overall_score = %s,
                    overall_status = %s,
                    peg_score = %s,
                    debt_score = %s,
                    institutional_ownership_score = %s,
                    scored_at = %s
                WHERE symbol = %s
            """, (
                overall_score,
                overall_status,
                peg_score,
                debt_score,
                institutional_ownership_score,
                scored_at or datetime.now(),
                symbol
            ))

            conn.commit()
            logger.info(f"Updated scores for {symbol} ({cursor.rowcount} rows affected)")

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update scores for {symbol}: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_latest_session_id(self) -> Optional[int]:
        """Get the ID of the most recent screening session."""
        session = self.get_latest_session()
        return session['id'] if session else None

    def get_stocks_ordered_by_score(self, limit: Optional[int] = None, country: Optional[str] = None) -> List[str]:
        """
        Get stock symbols ordered alphabetically.

        Note: Scoring is now done on-demand via /api/sessions/latest,
        so we no longer have pre-computed scores in the database.

        Args:
            limit: Optional max number of symbols to return
            country: Optional country filter (e.g., 'United States')

        Returns:
            List of stock symbols ordered alphabetically
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # Get all stocks, optionally filtered by country
            if country:
                cursor.execute("SELECT symbol FROM stocks WHERE country = %s ORDER BY symbol", (country,))
            else:
                cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")

            symbols = [row[0] for row in cursor.fetchall()]
            return symbols[:limit] if limit else symbols
        finally:
            self.return_connection(conn)

    def save_backtest_result(self, result: Dict[str, Any]):
        """Save a backtest result"""
        sql = """
            INSERT INTO backtest_results
             (symbol, backtest_date, years_back, start_price, end_price, total_return,
              historical_score, historical_rating, peg_score, debt_score, ownership_score,
              consistency_score, peg_ratio, earnings_cagr, revenue_cagr, debt_to_equity,
              institutional_ownership, roe, debt_to_earnings, gross_margin)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
             ON CONFLICT (symbol, years_back) DO UPDATE SET
                 backtest_date = EXCLUDED.backtest_date,
                 start_price = EXCLUDED.start_price,
                 end_price = EXCLUDED.end_price,
                 total_return = EXCLUDED.total_return,
                 historical_score = EXCLUDED.historical_score,
                 historical_rating = EXCLUDED.historical_rating,
                 peg_score = EXCLUDED.peg_score,
                 debt_score = EXCLUDED.debt_score,
                 ownership_score = EXCLUDED.ownership_score,
                 consistency_score = EXCLUDED.consistency_score,
                 peg_ratio = EXCLUDED.peg_ratio,
                 earnings_cagr = EXCLUDED.earnings_cagr,
                 revenue_cagr = EXCLUDED.revenue_cagr,
                 debt_to_equity = EXCLUDED.debt_to_equity,
                 institutional_ownership = EXCLUDED.institutional_ownership,
                 roe = EXCLUDED.roe,
                 debt_to_earnings = EXCLUDED.debt_to_earnings,
                 gross_margin = EXCLUDED.gross_margin
        """
        hist_data = result.get('historical_data', {})
        args = (
            result['symbol'],
            result['backtest_date'],
            result.get('years_back', 1),
            result['start_price'],
            result['end_price'],
            result['total_return'],
            result['historical_score'],
            result['historical_rating'],
            hist_data.get('peg_score'),
            hist_data.get('debt_score'),
            hist_data.get('institutional_ownership_score'),
            hist_data.get('consistency_score'),
            hist_data.get('peg_ratio'),
            hist_data.get('earnings_cagr'),
            hist_data.get('revenue_cagr'),
            hist_data.get('debt_to_equity'),
            hist_data.get('institutional_ownership'),
            hist_data.get('roe'),
            hist_data.get('debt_to_earnings'),
            hist_data.get('gross_margin')
        )
        self.write_queue.put((sql, args))

    def get_backtest_results(self, years_back: int = None) -> List[Dict[str, Any]]:
        """Get backtest results, optionally filtered by years_back"""
        conn = self.get_connection()
    def get_backtest_results(self, years_back: int = None, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch saved backtest results from database"""
        conn = self.get_connection()
        cursor = conn.cursor()

        columns = [
            'id', 'symbol', 'backtest_date', 'years_back', 'start_price', 'end_price',
            'total_return', 'historical_score', 'historical_rating', 'peg_score',
            'debt_score', 'ownership_score', 'consistency_score', 'peg_ratio',
            'earnings_cagr', 'revenue_cagr', 'debt_to_equity', 'institutional_ownership',
            'roe', 'debt_to_earnings', 'created_at', 'gross_margin'
        ]

        query_cols = ", ".join(columns)

        if years_back and symbol:
            query = f"SELECT {query_cols} FROM backtest_results WHERE years_back = %s AND symbol = %s"
            cursor.execute(query, (years_back, symbol))
        elif years_back:
            query = f"SELECT {query_cols} FROM backtest_results WHERE years_back = %s ORDER BY symbol"
            cursor.execute(query, (years_back,))
        elif symbol:
            query = f"SELECT {query_cols} FROM backtest_results WHERE symbol = %s ORDER BY years_back DESC"
            cursor.execute(query, (symbol,))
        else:
            query = f"SELECT {query_cols} FROM backtest_results ORDER BY years_back, symbol"
            cursor.execute(query)

        rows = cursor.fetchall()
        self.return_connection(conn)

        return [dict(zip(columns, row)) for row in rows]
