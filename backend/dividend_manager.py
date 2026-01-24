
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import yfinance as yf
from database import Database

logger = logging.getLogger(__name__)

class DividendManager:
    def __init__(self, db: Database):
        self.db = db

    def fetch_upcoming_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Fetch upcoming and historical dividends for a symbol using yfinance.
        Updates the dividend_payouts cache table.
        """
        try:
            ticker = yf.Ticker(symbol)
            calendar = ticker.calendar
            
            payouts = []
            
            # Check calendar for upcoming dividend
            if calendar and 'Dividend Date' in calendar:
                div_date = calendar['Dividend Date']
                # Sometimes it's a list or None
                if isinstance(div_date, list) and div_date:
                    div_date = div_date[0]
                
                if div_date and isinstance(div_date, (date, datetime)):
                    # yfinance calendar doesn't always have the amount directly in 'Dividend Date'
                    # but we can try to find it in the dividends series
                    amount = self._get_dividend_amount_for_date(ticker, div_date)
                    if amount:
                        payouts.append({
                            'symbol': symbol,
                            'amount': amount,
                            'payment_date': div_date,
                            'ex_dividend_date': calendar.get('Ex-Dividend Date')
                        })

            # Also check recent dividends series for missed ones (e.g. paid today)
            recent_divs = ticker.dividends
            if not recent_divs.empty:
                # Look at last 2 entries
                for dt, amount in recent_divs.tail(2).items():
                    # dt is Timestamp (timezone-aware usually)
                    p_date = dt.date()
                    payouts.append({
                        'symbol': symbol,
                        'amount': float(amount),
                        'payment_date': p_date,
                        'ex_dividend_date': None # ex-date not easily found in series
                    })

            # Save to cache
            conn = self.db.get_connection()
            try:
                cursor = conn.cursor()
                for p in payouts:
                    cursor.execute("""
                        INSERT INTO dividend_payouts (symbol, amount, payment_date, ex_dividend_date)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (symbol, payment_date) DO UPDATE SET
                            amount = EXCLUDED.amount,
                            ex_dividend_date = COALESCE(EXCLUDED.ex_dividend_date, dividend_payouts.ex_dividend_date)
                    """, (p['symbol'], p['amount'], p['payment_date'], p['ex_dividend_date']))
                conn.commit()
            finally:
                self.db.return_connection(conn)
                
            return payouts
        except Exception as e:
            logger.error(f"[DividendManager] Error fetching dividends for {symbol}: {e}")
            return []

    def _get_dividend_amount_for_date(self, ticker: yf.Ticker, div_date: date) -> Optional[float]:
        """Try to find the dividend amount in the series matching a date."""
        try:
            divs = ticker.dividends
            if divs.empty:
                return None
            
            # Match by date (ignoring time/timezone)
            for dt, amount in divs.items():
                if dt.date() == div_date:
                    return float(amount)
            
            # Fallback: if not found exactly, but calendar says there is one,
            # yfinance info might have 'dividendRate' (annual) or we just use the most recent
            if not divs.empty:
                return float(divs.iloc[-1])
                
            return None
        except:
            return None

    def process_all_portfolios(self, target_date: date = None):
        """
        Main entry point for daily dividend processing.
        1. Identifies symbols held in any portfolio.
        2. Refreshes dividend cache for those symbols.
        3. Processes payouts for the target date (defaults to today).
        """
        if target_date is None:
            target_date = date.today()
            
        logger.info(f"[DividendManager] Starting dividend processing for {target_date}")
        
        # 1. Get all unique symbols in all portfolios
        symbols = self._get_all_portfolio_symbols()
        logger.info(f"[DividendManager] Found {len(symbols)} active symbols to check")
        
        # 2. Update cache and find payouts due
        for symbol in symbols:
            self.fetch_upcoming_dividends(symbol)
            
        # 3. Process payouts
        payouts_due = self._get_payouts_for_date(target_date)
        logger.info(f"[DividendManager] Found {len(payouts_due)} payouts due on {target_date}")
        
        for payout in payouts_due:
            self._apply_payout_to_portfolios(payout)

    def _get_all_portfolio_symbols(self) -> List[str]:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT symbol 
                FROM portfolio_transactions 
                -- We only care about symbols currently held, but it's safer to just check all
                -- symbols that have ever been in a portfolio for now, or filter by active holdings
            """)
            # Better: only get symbols with active holdings
            cursor.execute("""
                SELECT DISTINCT symbol 
                FROM (
                    SELECT symbol, SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE -quantity END) as qty
                    FROM portfolio_transactions
                    GROUP BY portfolio_id, symbol
                    HAVING SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE -quantity END) > 0
                ) as active_holdings
            """)
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.db.return_connection(conn)

    def _get_payouts_for_date(self, target_date: date) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, amount, payment_date
                FROM dividend_payouts
                WHERE payment_date = %s
            """, (target_date,))
            return [{'symbol': r[0], 'amount': r[1], 'date': r[2]} for r in cursor.fetchall()]
        finally:
            self.db.return_connection(conn)

    def _apply_payout_to_portfolios(self, payout: Dict[str, Any]):
        symbol = payout['symbol']
        amount_per_share = payout['amount']
        
        # Find all portfolios holding this symbol
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT portfolio_id, SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE -quantity END) as qty
                FROM portfolio_transactions
                WHERE symbol = %s
                GROUP BY portfolio_id
                HAVING SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE -quantity END) > 0
            """, (symbol,))
            
            affected = cursor.fetchall()
            for portfolio_id, qty in affected:
                self._process_single_payout(portfolio_id, symbol, int(qty), amount_per_share)
        finally:
            self.db.return_connection(conn)

    def _process_single_payout(self, portfolio_id: int, symbol: str, quantity: int, amount_per_share: float):
        # 1. Record DIVIDEND transaction
        total_payout = quantity * amount_per_share
        logger.info(f"[DividendManager] Processing payout for portfolio {portfolio_id}: {quantity} {symbol} @ {amount_per_share} = ${total_payout:.2f}")
        
        # Check if already processed (idempotency)
        if self._is_dividend_already_recorded(portfolio_id, symbol, date.today()):
            logger.info(f"[DividendManager] Dividend already recorded for {symbol} in portfolio {portfolio_id}, skipping")
            return

        tx_id = self.db.record_transaction(
            portfolio_id=portfolio_id,
            symbol=symbol,
            transaction_type='DIVIDEND',
            quantity=quantity,
            price_per_share=amount_per_share,
            note=f"Dividend Payout: ${amount_per_share}/share"
        )
        
        # 2. Handle DRIP
        pref = self._get_portfolio_dividend_preference(portfolio_id)
        if pref == 'reinvest':
            self._handle_reinvestment(portfolio_id, symbol, total_payout)

    def _is_dividend_already_recorded(self, portfolio_id: int, symbol: str, check_date: date) -> bool:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM portfolio_transactions
                WHERE portfolio_id = %s 
                AND symbol = %s 
                AND transaction_type = 'DIVIDEND'
                AND executed_at::date = %s
            """, (portfolio_id, symbol, check_date))
            return cursor.fetchone() is not None
        finally:
            self.db.return_connection(conn)

    def _get_portfolio_dividend_preference(self, portfolio_id: int) -> str:
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT dividend_preference FROM portfolios WHERE id = %s", (portfolio_id,))
            row = cursor.fetchone()
            return row[0] if row else 'cash'
        finally:
            self.db.return_connection(conn)

    def _handle_reinvestment(self, portfolio_id: int, symbol: str, total_value: float):
        """Buy as many shares as possible with the dividend amount."""
        from portfolio_service import fetch_current_price
        price = fetch_current_price(symbol, db=self.db)
        
        if not price or price <= 0:
            logger.warning(f"[DividendManager] Unable to reinvest: price unavailable for {symbol}")
            return

        # Simplified reinvestment: buy integer shares, leave remainder in cash?
        # Or support fractional? The current schema uses quantity INTEGER.
        # Let's buy integer shares and leave the rest as cash.
        qty_to_buy = int(total_value // price)
        
        if qty_to_buy > 0:
            logger.info(f"[DividendManager] Reinvesting ${total_value:.2f} into {qty_to_buy} shares of {symbol} @ ${price:.2f}")
            self.db.record_transaction(
                portfolio_id=portfolio_id,
                symbol=symbol,
                transaction_type='BUY',
                quantity=qty_to_buy,
                price_per_share=price,
                note=f"Dividend Reinvestment (DRIP) from ${total_value:.2f}"
            )
        else:
            logger.info(f"[DividendManager] Reinvestment amount ${total_value:.2f} insufficient for 1 share of {symbol} @ ${price:.2f}")

