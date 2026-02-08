# ABOUTME: Stock data persistence for basic info, metrics, earnings, and price history
# ABOUTME: Handles CRUD for stock records, insider trades, and cache management

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import json

logger = logging.getLogger(__name__)


class StocksMixin:

    def save_stock_basic(self, symbol: str, company_name: str, exchange: str, sector: str = None,
                        country: str = None, ipo_year: int = None):
        sql = """
            INSERT INTO stocks (symbol, company_name, exchange, sector, country, ipo_year, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                exchange = EXCLUDED.exchange,
                sector = EXCLUDED.sector,
                country = EXCLUDED.country,
                ipo_year = EXCLUDED.ipo_year,
                last_updated = EXCLUDED.last_updated
        """
        args = (symbol, company_name, exchange, sector, country, ipo_year, datetime.now())
        self.write_queue.put((sql, args))

    def ensure_stocks_exist_batch(self, market_data_cache: Dict[str, Dict[str, Any]]):
        """
        Ensure stocks exist in the database before caching related data.

        This prevents FK violations when caching jobs run in parallel with screening.
        Uses batch upsert for efficiency - inserts minimal stock records if missing,
        leaves existing records untouched (DO NOTHING).

        Args:
            market_data_cache: Dict from TradingView {symbol: {name, price, market_cap, ...}}
        """
        if not market_data_cache:
            return

        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # Batch upsert - insert if not exists, do nothing if already present
            # This is lighter than save_stock_basic since we don't update existing
            for symbol, data in market_data_cache.items():
                cursor.execute("""
                    INSERT INTO stocks (symbol, company_name, last_updated)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (symbol) DO NOTHING
                """, (symbol, data.get('name', symbol), datetime.now()))

            conn.commit()
        finally:
            self.return_connection(conn)

    def save_stock_metrics(self, symbol: str, metrics: Dict[str, Any]):
        """
        Save or update stock metrics.
        Supports partial updates - only keys present in metrics dict will be updated.
        """
        # Always update last_updated
        metrics['last_updated'] = datetime.now(timezone.utc)
        if 'price' in metrics:
            metrics['last_price_updated'] = datetime.now(timezone.utc)

        # Valid columns map to ensure we only try to update valid fields
        valid_columns = {
            'price', 'pe_ratio', 'market_cap', 'debt_to_equity',
            'institutional_ownership', 'revenue', 'dividend_yield',
            'beta', 'total_debt', 'interest_expense', 'effective_tax_rate',
            'gross_margin',  # For Buffett scoring
            'forward_pe', 'forward_peg_ratio', 'forward_eps',
            'insider_net_buying_6m', 'last_updated', 'last_price_updated',
            'analyst_rating', 'analyst_rating_score', 'analyst_count',
            'price_target_high', 'price_target_low', 'price_target_mean',
            'short_ratio', 'short_percent_float', 'next_earnings_date',
            'prev_close', 'price_change', 'price_change_pct'
        }

        # Filter metrics to only valid columns
        update_data = {k: v for k, v in metrics.items() if k in valid_columns}

        if not update_data:
            return

        # Build dynamic SQL
        columns = ['symbol'] + list(update_data.keys())
        placeholders = ['%s'] * len(columns)

        # Build SET clause for ON CONFLICT DO UPDATE
        # updates = [f"{col} = EXCLUDED.{col}" for col in update_data.keys()]
        # better: use explicit value passing to avoid issues with EXCLUDED if safe
        # actually EXCLUDED is standard for upsert.
        updates = [f"{col} = EXCLUDED.{col}" for col in update_data.keys()]

        sql = f"""
            INSERT INTO stock_metrics ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT (symbol) DO UPDATE SET
                {', '.join(updates)}
        """

        args = [symbol] + list(update_data.values())

        self.write_queue.put((sql, tuple(args)))

    def save_insider_trades(self, symbol: str, trades: List[Dict[str, Any]]):
        """
        Batch save insider trades with Form 4 enrichment data.
        Supports both legacy fields and new Form 4 fields.
        """
        if not trades:
            return

        sql = """
            INSERT INTO insider_trades
            (symbol, name, position, transaction_date, transaction_type, shares, value, filing_url,
             transaction_code, is_10b51_plan, direct_indirect, transaction_type_label, price_per_share,
             is_derivative, accession_number, footnotes, shares_owned_after, ownership_change_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, name, transaction_date, transaction_type, shares)
            DO UPDATE SET
                transaction_code = EXCLUDED.transaction_code,
                is_10b51_plan = EXCLUDED.is_10b51_plan,
                direct_indirect = EXCLUDED.direct_indirect,
                transaction_type_label = EXCLUDED.transaction_type_label,
                price_per_share = EXCLUDED.price_per_share,
                is_derivative = EXCLUDED.is_derivative,
                accession_number = EXCLUDED.accession_number,
                footnotes = EXCLUDED.footnotes,
                shares_owned_after = EXCLUDED.shares_owned_after,
                ownership_change_pct = EXCLUDED.ownership_change_pct
        """

        for trade in trades:
            # Convert footnotes list to PostgreSQL array format
            footnotes = trade.get('footnotes', [])
            pg_footnotes = footnotes if footnotes else None

            args = (
                symbol,
                trade.get('name'),
                trade.get('position'),
                trade.get('transaction_date'),
                trade.get('transaction_type'),
                trade.get('shares'),
                trade.get('value'),
                trade.get('filing_url'),
                trade.get('transaction_code'),
                trade.get('is_10b51_plan', False),
                trade.get('direct_indirect', 'D'),
                trade.get('transaction_type_label'),
                trade.get('price_per_share'),
                trade.get('is_derivative', False),
                trade.get('accession_number'),
                pg_footnotes,
                trade.get('shares_owned_after'),
                trade.get('ownership_change_pct')
            )
            self.write_queue.put((sql, args))

    def get_insider_trades(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, position, transaction_date, transaction_type, shares, value, filing_url,
                       transaction_code, is_10b51_plan, direct_indirect, transaction_type_label,
                       price_per_share, is_derivative, accession_number, footnotes,
                       shares_owned_after, ownership_change_pct
                FROM insider_trades
                WHERE symbol = %s
                ORDER BY transaction_date DESC
                LIMIT %s
            """, (symbol, limit))

            rows = cursor.fetchall()
            return [{
                'name': row[0],
                'position': row[1],
                'transaction_date': row[2].isoformat() if row[2] else None,
                'transaction_type': row[3],
                'shares': row[4],
                'value': row[5],
                'filing_url': row[6],
                'transaction_code': row[7],
                'is_10b51_plan': row[8] if row[8] is not None else False,
                'direct_indirect': row[9] or 'D',
                'transaction_type_label': row[10],
                'price_per_share': row[11],
                'is_derivative': row[12] if row[12] is not None else False,
                'accession_number': row[13],
                'footnotes': list(row[14]) if row[14] else [],
                'shares_owned_after': row[15],
                'ownership_change_pct': row[16]
            } for row in rows]
        finally:
            self.return_connection(conn)

    def has_recent_insider_trades(self, symbol: str, since_date: str) -> bool:
        """
        Check if we have insider trades (Form 4 data) for a symbol since a given date.

        Used by Form 4 cache job to skip already-processed symbols.

        Args:
            symbol: Stock symbol
            since_date: Date string (YYYY-MM-DD) - returns True if we have trades on or after this date

        Returns:
            True if we have at least one insider trade since since_date
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM insider_trades
                WHERE symbol = %s AND transaction_date >= %s
                LIMIT 1
            """, (symbol, since_date))
            return cursor.fetchone() is not None
        finally:
            self.return_connection(conn)

    # ==================== Cache Check Methods ====================

    def record_cache_check(self, symbol: str, cache_type: str,
                           last_data_date: Optional[str] = None) -> None:
        """
        Record that a symbol was checked for a specific cache type.

        Call this after processing a symbol, even if no data was found.
        This prevents redundant API calls on subsequent cache runs.

        Args:
            symbol: Stock symbol
            cache_type: Type of cache ('form4', '10k', '8k', 'prices', 'transcripts', 'news')
            last_data_date: Optional date of most recent data found (for incremental fetches)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cache_checks (symbol, cache_type, last_checked, last_data_date)
                VALUES (%s, %s, CURRENT_DATE, %s)
                ON CONFLICT (symbol, cache_type) DO UPDATE SET
                    last_checked = CURRENT_DATE,
                    last_data_date = COALESCE(EXCLUDED.last_data_date, cache_checks.last_data_date)
            """, (symbol, cache_type, last_data_date))
            conn.commit()
        finally:
            self.return_connection(conn)

    def was_cache_checked_since(self, symbol: str, cache_type: str, since_date: str) -> bool:
        """
        Check if a symbol was already checked for a cache type since a given date.

        Used by cache jobs to skip symbols that have already been processed.

        Args:
            symbol: Stock symbol
            cache_type: Type of cache ('form4', '10k', '8k', 'prices', 'transcripts', 'news')
            since_date: Date string (YYYY-MM-DD) - returns True if checked on or after this date

        Returns:
            True if the symbol was checked since since_date
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM cache_checks
                WHERE symbol = %s AND cache_type = %s AND last_checked >= %s
                LIMIT 1
            """, (symbol, cache_type, since_date))
            return cursor.fetchone() is not None
        finally:
            self.return_connection(conn)

    def get_cache_check(self, symbol: str, cache_type: str) -> Optional[Dict[str, Any]]:
        """
        Get cache check info for a symbol and cache type.

        Returns:
            Dict with last_checked and last_data_date, or None if not found
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_checked, last_data_date FROM cache_checks
                WHERE symbol = %s AND cache_type = %s
            """, (symbol, cache_type))
            row = cursor.fetchone()
            if row:
                return {
                    'last_checked': row[0].isoformat() if row[0] else None,
                    'last_data_date': row[1].isoformat() if row[1] else None
                }
            return None
        finally:
            self.return_connection(conn)

    def clear_cache_checks(self, cache_type: Optional[str] = None,
                           symbol: Optional[str] = None) -> int:
        """
        Clear cache check records.

        Args:
            cache_type: Optional - clear only this cache type
            symbol: Optional - clear only this symbol

        Returns:
            Number of rows deleted
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if symbol and cache_type:
                cursor.execute(
                    "DELETE FROM cache_checks WHERE symbol = %s AND cache_type = %s",
                    (symbol, cache_type)
                )
            elif cache_type:
                cursor.execute(
                    "DELETE FROM cache_checks WHERE cache_type = %s",
                    (cache_type,)
                )
            elif symbol:
                cursor.execute(
                    "DELETE FROM cache_checks WHERE symbol = %s",
                    (symbol,)
                )
            else:
                cursor.execute("DELETE FROM cache_checks")
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            self.return_connection(conn)

    def save_earnings_history(self, symbol: str, year: int, eps: Optional[float], revenue: Optional[float], fiscal_end: str = None, debt_to_equity: float = None, period: str = 'annual', net_income: float = None, dividend_amount: float = None, operating_cash_flow: float = None, capital_expenditures: float = None, free_cash_flow: float = None, shareholder_equity: float = None, shares_outstanding: float = None, cash_and_cash_equivalents: float = None, total_debt: float = None):
        """Save earnings history for a single year/period."""
        sql = """
            INSERT INTO earnings_history (
                symbol, year, earnings_per_share, revenue, fiscal_end, debt_to_equity, period,
                net_income, dividend_amount, operating_cash_flow, capital_expenditures, free_cash_flow, shareholder_equity, shares_outstanding, cash_and_cash_equivalents, total_debt, last_updated
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (symbol, year, period) DO UPDATE SET
                earnings_per_share = EXCLUDED.earnings_per_share,
                revenue = EXCLUDED.revenue,
                fiscal_end = COALESCE(EXCLUDED.fiscal_end, earnings_history.fiscal_end),
                debt_to_equity = COALESCE(EXCLUDED.debt_to_equity, earnings_history.debt_to_equity),
                net_income = COALESCE(EXCLUDED.net_income, earnings_history.net_income),
                dividend_amount = COALESCE(EXCLUDED.dividend_amount, earnings_history.dividend_amount),
                operating_cash_flow = COALESCE(EXCLUDED.operating_cash_flow, earnings_history.operating_cash_flow),
                capital_expenditures = COALESCE(EXCLUDED.capital_expenditures, earnings_history.capital_expenditures),
                free_cash_flow = COALESCE(EXCLUDED.free_cash_flow, earnings_history.free_cash_flow),
                shareholder_equity = COALESCE(EXCLUDED.shareholder_equity, earnings_history.shareholder_equity),
                shares_outstanding = COALESCE(EXCLUDED.shares_outstanding, earnings_history.shares_outstanding),
                cash_and_cash_equivalents = COALESCE(EXCLUDED.cash_and_cash_equivalents, earnings_history.cash_and_cash_equivalents),
                total_debt = COALESCE(EXCLUDED.total_debt, earnings_history.total_debt),
                last_updated = CURRENT_TIMESTAMP
        """
        args = (symbol, year, eps, revenue, fiscal_end, debt_to_equity, period, net_income, dividend_amount, operating_cash_flow, capital_expenditures, free_cash_flow, shareholder_equity, shares_outstanding, cash_and_cash_equivalents, total_debt)
        self.write_queue.put((sql, args))

    def clear_quarterly_earnings(self, symbol: str) -> int:
        """
        Delete all quarterly earnings records for a symbol.

        Used before force-refresh to ensure stale quarterly data is removed
        before inserting fresh data from EDGAR.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Number of rows deleted
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM earnings_history
                WHERE symbol = %s AND period IN ('Q1', 'Q2', 'Q3', 'Q4')
            """, (symbol,))
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"[{symbol}] Cleared {deleted} quarterly earnings records for force refresh")
            return deleted
        finally:
            self.return_connection(conn)

    def stock_exists(self, symbol: str) -> bool:
        """Check if a stock exists in the stocks table."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM stocks WHERE symbol = %s", (symbol,))
            return cursor.fetchone() is not None
        finally:
            self.return_connection(conn)

    def get_stock_metrics(self, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sm.*, s.company_name, s.exchange,
                       s.sector,
                       s.country, s.ipo_year
                 FROM stock_metrics sm
                 JOIN stocks s ON sm.symbol = s.symbol
                 WHERE sm.symbol = %s
            """, (symbol,))
            row = cursor.fetchone()

            if not row:
                return None

            # Use cursor.description to dynamically map column names to values
            # This automatically handles columns added via migrations (price_target_*, analyst_*, short_*, etc.)
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        finally:
            self.return_connection(conn)

    def get_recently_updated_stocks(self, since_timestamp: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get stocks that have been updated since the given timestamp.
        Used for real-time UI updates.

        Args:
            since_timestamp: ISO format timestamp string
            limit: Max number of updates to return

        Returns:
            List of dictionaries with updated fields (price, change, etc.)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                WITH recent_earnings AS (
                    SELECT
                        symbol,
                        net_income,
                        year,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY year DESC) as rn,
                        COUNT(*) OVER (PARTITION BY symbol) as total_years
                    FROM earnings_history
                    -- Optimization: We could filter by symbol if we had the list upfront,
                    -- but here we filter by joining with the results of the main query.
                    -- Actually, simpler to do it in one query.
                ),
                growth_calc AS (
                    SELECT
                        t1.symbol,
                        t1.net_income as end_ni,
                        t2.net_income as start_ni,
                        (t1.year - t2.year) as years_diff
                    FROM recent_earnings t1
                    JOIN recent_earnings t2 ON t1.symbol = t2.symbol
                    WHERE t1.rn = 1  -- Most recent
                      AND t2.rn = LEAST(5, t1.total_years) -- 5th most recent (or oldest if < 5)
                      AND t1.year > t2.year -- Ensure strictly newer
                      AND t2.net_income != 0 -- Avoid div by zero
                      AND t2.net_income IS NOT NULL
                      AND t1.net_income IS NOT NULL
                ),
                calculated_metrics AS (
                    SELECT
                        g.symbol,
                        -- Linear Growth Rate Formula: ((End - Start) / |Start|) / Years * 100
                        (((g.end_ni - g.start_ni) / ABS(g.start_ni)) / NULLIF(g.years_diff, 0)) * 100 as earnings_cagr
                    FROM growth_calc g
                )
                SELECT
                    sm.symbol, sm.price, sm.pe_ratio, sm.market_cap,
                    sm.forward_pe, sm.forward_peg_ratio,
                    sm.dividend_yield, sm.beta,
                    cm.earnings_cagr,
                    sm.last_price_updated as last_updated
                FROM stock_metrics sm
                LEFT JOIN calculated_metrics cm ON sm.symbol = cm.symbol
                WHERE sm.last_price_updated > %s
                ORDER BY sm.last_price_updated DESC
                LIMIT %s
            """, (since_timestamp, limit))

            updates = []
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                for row in cursor.fetchall():
                    # Handle datetime serialization for last_updated
                    row_dict = dict(zip(columns, row))
                    if isinstance(row_dict.get('last_updated'), datetime):
                        row_dict['last_updated'] = row_dict['last_updated'].isoformat()

                    # Calculate PEG Ratio on the fly (Lynch Style: PE / Growth)
                    pe = row_dict.get('pe_ratio')
                    growth = row_dict.get('earnings_cagr')

                    # Ensure minimal growth for valid PEG (Lynch preferred > 0, usually > 5-10)
                    if pe and growth and growth > 0:
                        row_dict['peg_ratio'] = round(pe / growth, 2)
                    else:
                        row_dict['peg_ratio'] = None

                    updates.append(row_dict)

            return updates
        except Exception as e:
            # Handle invalid timestamp format gracefully
            print(f"Error fetching recently updated stocks: {e}")
            return []
        finally:
            self.return_connection(conn)

    def get_earnings_history(self, symbol: str, period_type: str = 'annual') -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            if period_type == 'quarterly':
                where_clause = "WHERE symbol = %s AND period IN ('Q1', 'Q2', 'Q3', 'Q4')"
            else:
                where_clause = "WHERE symbol = %s AND period = 'annual'"

            cursor.execute(f"""
                SELECT year, earnings_per_share, revenue, fiscal_end, debt_to_equity, period,
                       net_income, dividend_amount, operating_cash_flow, capital_expenditures,
                       free_cash_flow, shareholder_equity, shares_outstanding, cash_and_cash_equivalents, last_updated
                FROM earnings_history
                {where_clause}
                ORDER BY year DESC, period
            """, (symbol,))
            rows = cursor.fetchall()

            return [
                {
                    'year': row[0],
                    'eps': row[1],
                    'revenue': row[2],
                    'fiscal_end': row[3],
                    'debt_to_equity': row[4],
                    'period': row[5],
                    'net_income': row[6],
                    'dividend_amount': row[7],
                    'operating_cash_flow': row[8],
                    'capital_expenditures': row[9],
                    'free_cash_flow': row[10],
                    'shareholder_equity': row[11],
                    'shares_outstanding': row[12],
                    'cash_and_cash_equivalents': row[13],
                    'last_updated': row[14]
                }
                for row in rows
            ]
        finally:
            self.return_connection(conn)

    def get_earnings_refresh_metadata(self) -> Dict[str, Dict[str, Any]]:
        """
        Get metadata for determining if transcripts need refresh.
        Returns: {
            symbol: {
                'next_earnings_date': date,
                'last_transcript_date': date
            }
        }
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT ON (m.symbol)
                    m.symbol,
                    m.next_earnings_date,
                    t.earnings_date as last_transcript_date,
                    t.transcript_text
                FROM stock_metrics m
                LEFT JOIN earnings_transcripts t ON m.symbol = t.symbol
                ORDER BY m.symbol, t.earnings_date DESC NULLS LAST
            """)

            result = {}
            for row in cursor.fetchall():
                symbol = row[0]
                transcript_text = row[3]
                is_placeholder = (transcript_text == 'NO_TRANSCRIPT_AVAILABLE')
                
                result[symbol] = {
                    'next_earnings_date': row[1],
                    'last_transcript_date': row[2],
                    'latest_is_placeholder': is_placeholder
                }
            return result
        finally:
            self.return_connection(conn)


    def save_weekly_prices(self, symbol: str, weekly_data: Dict[str, Any]):
        """
        Save weekly price data.
        weekly_data dict with: 'dates' list and 'prices' list
        """
        if not weekly_data or not weekly_data.get('dates') or not weekly_data.get('prices'):
            return

        sql = """
            INSERT INTO weekly_prices
            (symbol, week_ending, price, last_updated)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol, week_ending) DO UPDATE SET
                price = EXCLUDED.price,
                last_updated = EXCLUDED.last_updated
        """

        # Batch write
        for date_str, price in zip(weekly_data['dates'], weekly_data['prices']):
            args = (symbol, date_str, price, datetime.now())
            self.write_queue.put((sql, args))

    def get_weekly_prices(self, symbol: str, start_year: int = None) -> Dict[str, Any]:
        """
        Get weekly price data for a symbol.

        Args:
            symbol: Stock symbol
            start_year: Optional start year filter

        Returns:
            Dict with 'dates' and 'prices' lists
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            query = "SELECT week_ending, price FROM weekly_prices WHERE symbol = %s"
            params = [symbol]

            if start_year:
                query += " AND EXTRACT(YEAR FROM week_ending) >= %s"
                params.append(start_year)

            query += " ORDER BY week_ending ASC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return {
                'dates': [row[0].strftime('%Y-%m-%d') for row in rows],
                'prices': [float(row[1]) for row in rows]
            }
        finally:
            self.return_connection(conn)

    # DEPRECATED: Use save_weekly_prices() instead
    # def save_price_point(self, symbol: str, date: str, price: float):
    #     """
    #     Save a single price point (e.g., fiscal year-end price).
    #
    #     Args:
    #         symbol: Stock symbol
    #         date: Date in YYYY-MM-DD format
    #         price: Closing price
    #     """
    #     sql = """
    #         INSERT INTO price_history
    #         (symbol, date, close, adjusted_close, volume)
    #         VALUES (%s, %s, %s, %s, %s)
    #         ON CONFLICT (symbol, date) DO UPDATE SET
    #             close = EXCLUDED.close
    #     """
    #     args = (symbol, date, price, price, None)
    #     self.write_queue.put((sql, args))

    def is_cache_valid(self, symbol: str, max_age_hours: int = 24) -> bool:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_updated FROM stock_metrics WHERE symbol = %s
            """, (symbol,))
            row = cursor.fetchone()

            if not row:
                return False

            last_updated = row[0]
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            return age_hours < max_age_hours
        finally:
            self.return_connection(conn)


    def search_stocks(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search stocks by symbol or company name.

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of dictionaries with 'symbol' and 'company_name'
        """
        if not query or len(query.strip()) == 0:
            return []

        search_term = f"%{query.strip()}%"

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, company_name
                FROM stocks
                WHERE symbol ILIKE %s OR company_name ILIKE %s
                ORDER BY
                    CASE
                        WHEN symbol ILIKE %s THEN 0  -- Exact symbol match priority
                        WHEN symbol ILIKE %s THEN 1  -- Starts with symbol priority
                        ELSE 2
                    END,
                    symbol
                LIMIT %s
            """, (search_term, search_term, query, f"{query}%", limit))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'symbol': row[0],
                    'company_name': row[1]
                })

            return results
        except Exception as e:
            logger.error(f"Error searching stocks: {e}")
            return []
        finally:
            self.return_connection(conn)

    def get_all_cached_stocks(self) -> List[str]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        finally:
            self.return_connection(conn)
