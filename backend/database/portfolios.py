# ABOUTME: Portfolio management for paper trading with transaction tracking
# ABOUTME: Handles holdings, cash positions, dividends, and performance attribution

import logging
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any, List
import json
import psycopg.rows

logger = logging.getLogger(__name__)


class PortfoliosMixin:
    def create_portfolio(self, user_id: int, name: str, initial_cash: float = 100000.0) -> int:
        """Create a new paper trading portfolio for a user"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolios (user_id, name, initial_cash)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (user_id, name, initial_cash))
            portfolio_id = cursor.fetchone()[0]
            conn.commit()
            return portfolio_id
        finally:
            self.return_connection(conn)

    def get_portfolio(self, portfolio_id: int) -> Optional[Dict[str, Any]]:
        """Get a portfolio by ID"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT p.id, p.user_id, p.name, p.initial_cash, p.created_at,
                       s.id as strategy_id, s.name as strategy_name
                FROM portfolios p
                LEFT JOIN investment_strategies s ON p.id = s.portfolio_id
                WHERE p.id = %s
            """, (portfolio_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def get_user_portfolios(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all portfolios for a user"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT p.*, s.id as strategy_id, s.name as strategy_name
                FROM portfolios p
                LEFT JOIN investment_strategies s ON p.id = s.portfolio_id
                WHERE p.user_id = %s
                ORDER BY p.created_at DESC
            """, (user_id,))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def rename_portfolio(self, portfolio_id: int, new_name: str):
        """Rename a portfolio"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE portfolios SET name = %s WHERE id = %s
            """, (new_name, portfolio_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def delete_portfolio(self, portfolio_id: int, user_id: int) -> bool:
        """Delete a portfolio (verifies ownership). Returns True if deleted."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM portfolios
                WHERE id = %s AND user_id = %s
            """, (portfolio_id, user_id))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self.return_connection(conn)

    def record_transaction(
        self,
        portfolio_id: int,
        symbol: str,
        transaction_type: str,
        quantity: int,
        price_per_share: float,
        note: str = None,
        position_type: str = None,
        dividend_payment_date: date = None
    ) -> int:
        """Record a buy or sell transaction

        Args:
            portfolio_id: Portfolio ID
            symbol: Stock symbol
            transaction_type: 'BUY', 'SELL', or 'DIVIDEND'
            quantity: Number of shares
            price_per_share: Price per share
            note: Optional note
            position_type: Optional 'new', 'addition', or 'exit' for tracking
            dividend_payment_date: Optional specific payment date for DIVIDEND (for idempotency)
        """
        from datetime import date
        total_value = quantity * price_per_share
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_transactions
                (portfolio_id, symbol, transaction_type, quantity, price_per_share, total_value, note, position_type, dividend_payment_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (portfolio_id, symbol, transaction_type, quantity, price_per_share, total_value, note, position_type, dividend_payment_date))
            tx_id = cursor.fetchone()[0]

            # Track position entry for BUY transactions
            if transaction_type == 'BUY':
                cursor.execute("""
                    INSERT INTO position_entry_tracking (portfolio_id, symbol, first_buy_date, last_evaluated_date)
                    VALUES (%s, %s, %s, NULL)
                    ON CONFLICT (portfolio_id, symbol) DO NOTHING
                """, (portfolio_id, symbol, date.today()))

            conn.commit()
            return tx_id
        finally:
            self.return_connection(conn)

    def get_portfolio_transactions(self, portfolio_id: int) -> List[Dict[str, Any]]:
        """Get all transactions for a portfolio"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, portfolio_id, symbol, transaction_type, quantity,
                       price_per_share, total_value, executed_at, note
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                ORDER BY executed_at DESC
            """, (portfolio_id,))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def get_portfolio_holdings(self, portfolio_id: int) -> Dict[str, int]:
        """Compute current holdings from transactions.

        Returns a dict mapping symbol -> quantity for positions > 0.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol,
                       SUM(CASE
                           WHEN transaction_type = 'BUY' THEN quantity
                           WHEN transaction_type = 'SELL' THEN -quantity
                           ELSE 0
                       END) as net_qty
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                GROUP BY symbol
                HAVING SUM(CASE
                           WHEN transaction_type = 'BUY' THEN quantity
                           WHEN transaction_type = 'SELL' THEN -quantity
                           ELSE 0
                       END) > 0
            """, (portfolio_id,))
            rows = cursor.fetchall()
            # Return dict mapping symbol -> quantity (not list of dicts!)
            return {symbol: int(qty) for symbol, qty in rows}
        finally:
            self.return_connection(conn)

    def get_portfolio_by_name(self, user_id: int, name: str) -> Optional[Dict[str, Any]]:
        """Find a portfolio by name for a specific user (case-insensitive)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, name, initial_cash, created_at, dividend_preference
                FROM portfolios
                WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                LIMIT 1
            """, (user_id, name))
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
        finally:
            self.return_connection(conn)

    def get_portfolio_holdings_detailed(self, portfolio_id: int, use_live_prices: bool = True, prices_map: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
        """Get detailed holdings information including purchase prices and current values.

        Args:
            portfolio_id: Portfolio to get holdings for
            use_live_prices: If True, fetch live prices from yfinance. If False, use cached prices.
            prices_map: Optional pre-fetched map of symbol -> price. If provided, used regardless of use_live_prices.

        Returns:
            List of dicts with keys: symbol, quantity, avg_purchase_price, current_price,
                                     total_cost, current_value, gain_loss, gain_loss_percent
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Calculate average purchase price using weighted average of BUY transactions
            # This uses FIFO-like logic: we calculate the weighted average cost basis
            cursor.execute("""
                SELECT
                    symbol,
                    SUM(CASE
                        WHEN transaction_type = 'BUY' THEN quantity
                        WHEN transaction_type = 'SELL' THEN -quantity
                        ELSE 0
                    END) as net_qty,
                    SUM(CASE WHEN transaction_type = 'BUY' THEN quantity * price_per_share ELSE 0 END) /
                        NULLIF(SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE 0 END), 0) as avg_purchase_price
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                GROUP BY symbol
                HAVING SUM(CASE
                        WHEN transaction_type = 'BUY' THEN quantity
                        WHEN transaction_type = 'SELL' THEN -quantity
                        ELSE 0
                    END) > 0
            """, (portfolio_id,))

            holdings_data = cursor.fetchall()

            # Fetch current prices
            detailed_holdings = []

            if prices_map:
                symbols = [row[0] for row in holdings_data]
                # Use provided map
                for symbol, quantity, avg_purchase_price in holdings_data:
                    current_price = prices_map.get(symbol)

                    if current_price and avg_purchase_price:
                        total_cost = quantity * avg_purchase_price
                        current_value = quantity * current_price
                        gain_loss = current_value - total_cost
                        gain_loss_percent = (gain_loss / total_cost * 100) if total_cost > 0 else 0.0

                        detailed_holdings.append({
                            'symbol': symbol,
                            'quantity': quantity,
                            'avg_purchase_price': avg_purchase_price,
                            'current_price': current_price,
                            'total_cost': total_cost,
                            'current_value': current_value,
                            'gain_loss': gain_loss,
                            'gain_loss_percent': gain_loss_percent
                        })
            elif use_live_prices:
                from portfolio_service import fetch_current_prices_batch

                # Get all symbols that need prices
                symbols = [row[0] for row in holdings_data]
                prices_map = fetch_current_prices_batch(symbols, db=self)

                for symbol, quantity, avg_purchase_price in holdings_data:
                    current_price = prices_map.get(symbol)

                    if current_price and avg_purchase_price:
                        total_cost = quantity * avg_purchase_price
                        current_value = quantity * current_price
                        gain_loss = current_value - total_cost
                        gain_loss_percent = (gain_loss / total_cost * 100) if total_cost > 0 else 0.0

                        detailed_holdings.append({
                            'symbol': symbol,
                            'quantity': quantity,
                            'avg_purchase_price': avg_purchase_price,
                            'current_price': current_price,
                            'total_cost': total_cost,
                            'current_value': current_value,
                            'gain_loss': gain_loss,
                            'gain_loss_percent': gain_loss_percent
                        })
            else:
                # Use cached prices from stock_metrics
                for symbol, quantity, avg_purchase_price in holdings_data:
                    cursor.execute("SELECT price FROM stock_metrics WHERE symbol = %s", (symbol,))
                    row = cursor.fetchone()
                    if row and row[0] and avg_purchase_price:
                        current_price = row[0]
                        total_cost = quantity * avg_purchase_price
                        current_value = quantity * current_price
                        gain_loss = current_value - total_cost
                        gain_loss_percent = (gain_loss / total_cost * 100) if total_cost > 0 else 0.0

                        detailed_holdings.append({
                            'symbol': symbol,
                            'quantity': quantity,
                            'avg_purchase_price': avg_purchase_price,
                            'current_price': current_price,
                            'total_cost': total_cost,
                            'current_value': current_value,
                            'gain_loss': gain_loss,
                            'gain_loss_percent': gain_loss_percent
                        })

            return detailed_holdings
        finally:
            self.return_connection(conn)

    def get_portfolio_cash(self, portfolio_id: int) -> float:
        """Compute current cash balance from initial cash and transactions.

        cash = initial_cash - sum(BUY totals) + sum(SELL totals) + sum(DIVIDEND totals)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Get initial cash
            cursor.execute("SELECT initial_cash FROM portfolios WHERE id = %s", (portfolio_id,))
            row = cursor.fetchone()
            if not row:
                return 0.0
            initial_cash = row[0]

            # Get transaction totals
            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN transaction_type = 'BUY' THEN total_value ELSE 0 END), 0) as buys,
                    COALESCE(SUM(CASE WHEN transaction_type = 'SELL' THEN total_value ELSE 0 END), 0) as sells,
                    COALESCE(SUM(CASE WHEN transaction_type = 'DIVIDEND' THEN total_value ELSE 0 END), 0) as dividends
                FROM portfolio_transactions
                WHERE portfolio_id = %s
            """, (portfolio_id,))
            buys, sells, dividends = cursor.fetchone()

            return initial_cash - buys + sells + dividends
        finally:
            self.return_connection(conn)

    def get_portfolio_dividend_summary(self, portfolio_id: int) -> Dict[str, Any]:
        """Get dividend income summary for a portfolio.

        Returns total dividends received, YTD dividends, and breakdown by symbol.
        """
        from datetime import date
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # Total dividends all-time
            cursor.execute("""
                SELECT COALESCE(SUM(total_value), 0) as total_dividends
                FROM portfolio_transactions
                WHERE portfolio_id = %s AND transaction_type = 'DIVIDEND'
            """, (portfolio_id,))
            total_dividends = cursor.fetchone()[0]

            # Year-to-date dividends
            ytd_start = date(date.today().year, 1, 1)
            cursor.execute("""
                SELECT COALESCE(SUM(total_value), 0) as ytd_dividends
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                AND transaction_type = 'DIVIDEND'
                AND executed_at >= %s
            """, (portfolio_id, ytd_start))
            ytd_dividends = cursor.fetchone()[0]

            # Breakdown by symbol
            cursor.execute("""
                SELECT
                    symbol,
                    COUNT(*) as payment_count,
                    SUM(total_value) as total_received,
                    MAX(executed_at) as last_payment
                FROM portfolio_transactions
                WHERE portfolio_id = %s AND transaction_type = 'DIVIDEND'
                GROUP BY symbol
                ORDER BY total_received DESC
            """, (portfolio_id,))

            breakdown = []
            for row in cursor.fetchall():
                breakdown.append({
                    'symbol': row[0],
                    'payment_count': row[1],
                    'total_received': float(row[2]),
                    'last_payment': row[3]
                })

            return {
                'total_dividends': float(total_dividends),
                'ytd_dividends': float(ytd_dividends),
                'breakdown': breakdown
            }
        finally:
            self.return_connection(conn)

    def track_position_entry(self, portfolio_id: int, symbol: str, buy_date: date = None):
        """Track when a position was first entered (for re-evaluation grace periods)."""
        if buy_date is None:
            buy_date = date.today()

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO position_entry_tracking (portfolio_id, symbol, first_buy_date, last_evaluated_date)
                VALUES (%s, %s, %s, NULL)
                ON CONFLICT (portfolio_id, symbol) DO NOTHING
            """, (portfolio_id, symbol, buy_date))
            conn.commit()
        finally:
            self.return_connection(conn)

    def update_position_evaluation_date(self, portfolio_id: int, symbol: str):
        """Update when a position was last evaluated for re-evaluation tracking."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE position_entry_tracking
                SET last_evaluated_date = %s
                WHERE portfolio_id = %s AND symbol = %s
            """, (date.today(), portfolio_id, symbol))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_position_entry_dates(self, portfolio_id: int) -> Dict[str, Dict[str, Any]]:
        """Get entry dates for all positions in portfolio.

        Returns dict mapping symbol -> {first_buy_date, last_evaluated_date, days_held}
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, first_buy_date, last_evaluated_date
                FROM position_entry_tracking
                WHERE portfolio_id = %s
            """, (portfolio_id,))

            result = {}
            today = date.today()
            for symbol, first_buy, last_eval in cursor.fetchall():
                days_held = (today - first_buy).days if first_buy else 0
                result[symbol] = {
                    'first_buy_date': first_buy,
                    'last_evaluated_date': last_eval,
                    'days_held': days_held
                }
            return result
        finally:
            self.return_connection(conn)

    def get_portfolio_performance_with_attribution(
        self,
        portfolio_id: int,
        holdings_value: float = None,
        cash: float = None,
        initial_cash: float = None
    ) -> Dict[str, Any]:
        """Calculate portfolio performance with dividend attribution.

        Separates total return into:
        - Capital gains/losses from price changes
        - Dividend income
        - Realized gains from sells

        Args:
            portfolio_id: Portfolio ID
            holdings_value: Pre-computed holdings value (optional, computed if not provided)
            cash: Pre-computed cash balance (optional, computed if not provided)
            initial_cash: Pre-computed initial cash (optional, computed if not provided)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # Get initial cash if not provided
            if initial_cash is None:
                cursor.execute("SELECT initial_cash FROM portfolios WHERE id = %s", (portfolio_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                initial_cash = row[0]

            # Get transaction breakdown
            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN transaction_type = 'BUY' THEN total_value ELSE 0 END), 0) as total_bought,
                    COALESCE(SUM(CASE WHEN transaction_type = 'SELL' THEN total_value ELSE 0 END), 0) as total_sold,
                    COALESCE(SUM(CASE WHEN transaction_type = 'DIVIDEND' THEN total_value ELSE 0 END), 0) as dividend_income
                FROM portfolio_transactions
                WHERE portfolio_id = %s
            """, (portfolio_id,))
            total_bought, total_sold, dividend_income = cursor.fetchone()

            # Use pre-computed values or calculate if not provided
            if cash is None:
                cash = self.get_portfolio_cash(portfolio_id)
            if holdings_value is None:
                holdings_detailed = self.get_portfolio_holdings_detailed(portfolio_id, use_live_prices=False)
                holdings_value = sum(h['current_value'] for h in holdings_detailed)

            current_value = cash + holdings_value

            # Calculate realized gains (money from sells minus cost basis)
            # This is approximate - true realized gains need FIFO/LIFO tracking
            cursor.execute("""
                SELECT
                    symbol,
                    SUM(CASE WHEN transaction_type = 'BUY' THEN quantity * price_per_share ELSE 0 END) as cost_basis,
                    SUM(CASE WHEN transaction_type = 'SELL' THEN quantity * price_per_share ELSE 0 END) as sell_proceeds
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                GROUP BY symbol
                HAVING SUM(CASE WHEN transaction_type = 'SELL' THEN quantity ELSE 0 END) > 0
            """, (portfolio_id,))

            realized_gains = 0.0
            for symbol, cost, proceeds in cursor.fetchall():
                if cost and proceeds:
                    realized_gains += (proceeds - cost)

            # Unrealized gains (current holdings value minus cost basis)
            holdings_cost_basis = total_bought - total_sold
            unrealized_gains = holdings_value - holdings_cost_basis

            # Total return = (current_value - initial_cash) / initial_cash
            total_return = current_value - initial_cash
            total_return_pct = (total_return / initial_cash * 100) if initial_cash > 0 else 0

            # Attribution
            capital_gains = unrealized_gains + realized_gains
            dividend_yield_pct = (dividend_income / initial_cash * 100) if initial_cash > 0 else 0

            return {
                'total_return': float(total_return),
                'total_return_pct': float(total_return_pct),
                'capital_gains': float(capital_gains),
                'dividend_income': float(dividend_income),
                'dividend_yield_pct': float(dividend_yield_pct),
                'realized_gains': float(realized_gains),
                'unrealized_gains': float(unrealized_gains)
            }
        finally:
            self.return_connection(conn)

    def save_portfolio_snapshot(
        self,
        portfolio_id: int,
        total_value: float,
        cash_value: float,
        holdings_value: float
    ) -> int:
        """Save a portfolio value snapshot for historical tracking"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_value_snapshots
                (portfolio_id, total_value, cash_value, holdings_value)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (portfolio_id, total_value, cash_value, holdings_value))
            snapshot_id = cursor.fetchone()[0]
            conn.commit()
            return snapshot_id
        finally:
            self.return_connection(conn)

    def get_portfolio_snapshots(self, portfolio_id: int, limit: int = None) -> List[Dict[str, Any]]:
        """Get portfolio value history snapshots enriched with benchmark performance."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            
            # 1. Get portfolio info (inception values)
            cursor.execute("SELECT initial_cash, created_at FROM portfolios WHERE id = %s", (portfolio_id,))
            portfolio_info = cursor.fetchone()
            if not portfolio_info:
                return []
                
            initial_cash = float(portfolio_info['initial_cash'])
            creation_date = portfolio_info['created_at'].date()
            
            # 2. Get inception benchmark price (closest to creation date)
            cursor.execute("""
                SELECT spy_price FROM benchmark_snapshots 
                ORDER BY ABS(snapshot_date - %s) ASC 
                LIMIT 1
            """, (creation_date,))
            inception_benchmark = cursor.fetchone()
            inception_spy = float(inception_benchmark['spy_price']) if inception_benchmark else None

            # 3. Get snapshots joined with benchmarks
            query = """
                SELECT 
                    s.id, s.portfolio_id, s.total_value, s.cash_value, s.holdings_value, s.snapshot_at,
                    b.spy_price as current_spy
                FROM portfolio_value_snapshots s
                LEFT JOIN benchmark_snapshots b ON s.snapshot_at::date = b.snapshot_date
                WHERE s.portfolio_id = %s
                ORDER BY s.snapshot_at ASC
            """
            if limit:
                query += f" LIMIT {limit}"
                
            cursor.execute(query, (portfolio_id,))
            snapshots = cursor.fetchall()
            
            # 4. Calculate returns
            results = []
            for s in snapshots:
                # Portfolio return %
                total_value = float(s['total_value'])
                portfolio_return_pct = ((total_value - initial_cash) / initial_cash * 100) if initial_cash > 0 else 0
                
                # Benchmark return %
                current_spy = float(s['current_spy']) if s['current_spy'] else None
                spy_return_pct = 0
                if inception_spy and current_spy:
                    spy_return_pct = ((current_spy - inception_spy) / inception_spy * 100)
                
                alpha = portfolio_return_pct - spy_return_pct
                
                results.append({
                    'id': s['id'],
                    'portfolio_id': s['portfolio_id'],
                    'total_value': total_value,
                    'cash_value': float(s['cash_value']),
                    'holdings_value': float(s['holdings_value']),
                    'snapshot_at': s['snapshot_at'],
                    'portfolio_return_pct': float(portfolio_return_pct),
                    'spy_return_pct': float(spy_return_pct),
                    'alpha': float(alpha),
                    'spy_price': current_spy
                })
                
            return results
        finally:
            self.return_connection(conn)

    def get_portfolio_summary(self, portfolio_id: int, use_live_prices: bool = True, prices_map: Optional[Dict[str, float]] = None) -> Optional[Dict[str, Any]]:
        """Get portfolio with computed cash, holdings value, and performance.

        Args:
            portfolio_id: Portfolio to summarize
            use_live_prices: If True, fetch live prices from yfinance for accuracy.
                             If False, use cached prices from stock_metrics (faster, for snapshots).
            prices_map: Optional pre-fetched map of symbol -> price.
        """
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        cash = self.get_portfolio_cash(portfolio_id)
        holdings = self.get_portfolio_holdings(portfolio_id)
        holdings_detailed = self.get_portfolio_holdings_detailed(portfolio_id, use_live_prices, prices_map)

        # Calculate holdings value from detailed holdings
        holdings_value = sum(h['current_value'] for h in holdings_detailed)

        total_value = cash + holdings_value
        initial_cash = portfolio['initial_cash']
        gain_loss = total_value - initial_cash
        gain_loss_percent = (gain_loss / initial_cash * 100) if initial_cash > 0 else 0.0

        # Get dividend metrics
        dividend_summary = self.get_portfolio_dividend_summary(portfolio_id)

        # Pass pre-computed values to avoid redundant calculations
        performance_attribution = self.get_portfolio_performance_with_attribution(
            portfolio_id,
            holdings_value=holdings_value,
            cash=cash,
            initial_cash=initial_cash
        )

        return {
            'id': portfolio['id'],
            'user_id': portfolio['user_id'],
            'name': portfolio['name'],
            'initial_cash': initial_cash,
            'created_at': portfolio['created_at'],
            'cash': cash,
            'holdings': holdings,  # Keep simple dict for backward compatibility
            'holdings_detailed': holdings_detailed,  # New detailed holdings list
            'holdings_value': holdings_value,
            'total_value': total_value,
            'gain_loss': gain_loss,
            'gain_loss_percent': gain_loss_percent,
            'strategy_id': portfolio.get('strategy_id'),
            'strategy_name': portfolio.get('strategy_name'),
            # Dividend tracking
            'total_dividends': dividend_summary.get('total_dividends', 0),
            'ytd_dividends': dividend_summary.get('ytd_dividends', 0),
            'dividend_breakdown': dividend_summary.get('breakdown', []),
            # Performance attribution
            'capital_gains': performance_attribution.get('capital_gains', 0) if performance_attribution else 0,
            'dividend_income': performance_attribution.get('dividend_income', 0) if performance_attribution else 0,
            'dividend_yield_pct': performance_attribution.get('dividend_yield_pct', 0) if performance_attribution else 0
        }

    def get_all_portfolios(self) -> List[Dict[str, Any]]:
        """Get all portfolios (for batch snapshot operations)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, user_id, name, initial_cash, created_at
                FROM portfolios
            """)
            return cursor.fetchall()
        finally:
            self.return_connection(conn)
