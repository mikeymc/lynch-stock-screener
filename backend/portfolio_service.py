# ABOUTME: Paper trading service for executing buy/sell trades
# ABOUTME: Handles market hours validation, price fetching, and trade execution

"""
Portfolio Service

Handles paper trading trade execution with:
- Extended market hours validation (4 AM - 8 PM ET)
- Price fetching via yfinance with fallback to database
- Trade validation (cash/holdings checks)
- Transaction recording
"""

import logging
from datetime import datetime, time
from typing import Dict, Any, Optional
from zoneinfo import ZoneInfo

import yfinance as yf

logger = logging.getLogger(__name__)

# Extended market hours: 4 AM - 8 PM ET
MARKET_OPEN = time(4, 0)   # 4:00 AM
MARKET_CLOSE = time(20, 0)  # 8:00 PM
ET_TIMEZONE = ZoneInfo("America/New_York")


def is_market_open(check_time: datetime = None) -> bool:
    """
    Check if the market is open for trading.

    Extended hours: 4 AM - 8 PM ET, weekdays only.

    Args:
        check_time: Time to check (defaults to now). Must be timezone-aware.

    Returns:
        True if market is open, False otherwise.
    """
    if check_time is None:
        check_time = datetime.now(ET_TIMEZONE)
    elif check_time.tzinfo is None:
        # Convert naive datetime to ET
        check_time = check_time.replace(tzinfo=ET_TIMEZONE)
    else:
        # Convert to ET for comparison
        check_time = check_time.astimezone(ET_TIMEZONE)

    # Check if weekday (Monday=0, Sunday=6)
    if check_time.weekday() >= 5:  # Saturday or Sunday
        return False

    # Check time is within extended hours
    current_time = check_time.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def fetch_current_price(symbol: str, db=None) -> Optional[float]:
    """
    Fetch the current price for a stock.

    Tries yfinance first, falls back to database stock_metrics.

    Args:
        symbol: Stock ticker symbol
        db: Database instance for fallback

    Returns:
        Current price as float, or None if unavailable
    """
    # Try yfinance first
    try:
        ticker = yf.Ticker(symbol)
        fast_info = ticker.fast_info
        if fast_info and 'lastPrice' in fast_info:
            price = fast_info['lastPrice']
            if price is not None and price > 0:
                logger.info(f"[PortfolioService] Fetched price for {symbol} from yfinance: ${price:.2f}")
                return float(price)
    except Exception as e:
        logger.warning(f"[PortfolioService] yfinance error for {symbol}: {e}")

    # Fallback to database
    if db is not None:
        try:
            conn = db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT price FROM stock_metrics WHERE symbol = %s", (symbol,))
                row = cursor.fetchone()
                if row and row[0]:
                    price = float(row[0])
                    logger.info(f"[PortfolioService] Using fallback price for {symbol} from database: ${price:.2f}")
                    return price
            finally:
                db.return_connection(conn)
        except Exception as e:
            logger.error(f"[PortfolioService] Database error fetching price for {symbol}: {e}")

    logger.warning(f"[PortfolioService] No price available for {symbol}")
    return None


def validate_trade(
    db,
    portfolio_id: int,
    symbol: str,
    transaction_type: str,
    quantity: int,
    price_per_share: float
) -> Dict[str, Any]:
    """
    Validate a trade before execution.

    Checks:
    - Quantity is positive
    - BUY: sufficient cash
    - SELL: sufficient holdings

    Args:
        db: Database instance
        portfolio_id: Portfolio to trade in
        symbol: Stock ticker symbol
        transaction_type: 'BUY' or 'SELL'
        quantity: Number of shares
        price_per_share: Price per share

    Returns:
        Dict with 'valid' (bool) and optional 'error' (str)
    """
    # Check quantity
    if quantity <= 0:
        return {'valid': False, 'error': 'Quantity must be positive'}

    total_value = quantity * price_per_share

    if transaction_type == 'BUY':
        # Check sufficient cash
        cash = db.get_portfolio_cash(portfolio_id)
        if cash < total_value:
            return {
                'valid': False,
                'error': f'Insufficient cash. Need ${total_value:,.2f}, have ${cash:,.2f}'
            }
    elif transaction_type == 'SELL':
        # Check sufficient holdings
        holdings = db.get_portfolio_holdings(portfolio_id)
        current_qty = holdings.get(symbol, 0)
        if current_qty < quantity:
            return {
                'valid': False,
                'error': f'Insufficient holdings. Want to sell {quantity}, have {current_qty}'
            }
    else:
        return {'valid': False, 'error': f'Invalid transaction type: {transaction_type}'}

    return {'valid': True}


def execute_trade(
    db,
    portfolio_id: int,
    symbol: str,
    transaction_type: str,
    quantity: int,
    note: str = None,
    position_type: str = None
) -> Dict[str, Any]:
    """
    Execute a paper trade.

    Full flow:
    1. Check market hours
    2. Fetch current price
    3. Validate trade
    4. Record transaction

    Args:
        db: Database instance
        portfolio_id: Portfolio to trade in
        symbol: Stock ticker symbol
        transaction_type: 'BUY' or 'SELL'
        quantity: Number of shares
        note: Optional note for the transaction
        position_type: Optional 'new', 'addition', or 'exit' for tracking

    Returns:
        Dict with:
        - success: bool
        - transaction_id: int (if successful)
        - price_per_share: float
        - total_value: float
        - error: str (if failed)
    """
    # Check market hours
    # Check market hours
    if not is_market_open():
        # Diagnostic info for production issues
        now_et = datetime.now(ET_TIMEZONE)
        return {
            'success': False,
            'error': f'Market is closed. Extended hours: 4 AM - 8 PM ET, weekdays only. (Server Time: {now_et.strftime("%Y-%m-%d %H:%M:%S %Z")}, Weekday: {now_et.strftime("%A")})'
        }

    # Fetch price
    price = fetch_current_price(symbol, db)
    if price is None:
        return {
            'success': False,
            'error': f'Unable to fetch price for {symbol}'
        }

    # Validate trade
    validation = validate_trade(db, portfolio_id, symbol, transaction_type, quantity, price)
    if not validation['valid']:
        return {
            'success': False,
            'error': validation['error']
        }

    # Execute trade
    total_value = quantity * price
    transaction_id = db.record_transaction(
        portfolio_id=portfolio_id,
        symbol=symbol,
        transaction_type=transaction_type,
        quantity=quantity,
        price_per_share=price,
        note=note,
        position_type=position_type
    )

    logger.info(
        f"[PortfolioService] Executed {transaction_type} {quantity} {symbol} @ ${price:.2f} "
        f"(total: ${total_value:,.2f}) in portfolio {portfolio_id}"
    )

    return {
        'success': True,
        'transaction_id': transaction_id,
        'price_per_share': price,
        'total_value': total_value
    }


def fetch_current_prices_batch(symbols: list[str], db=None) -> Dict[str, float]:
    """
    Fetch current prices for multiple stocks in a single batch request.
    
    Args:
        symbols: List of stock symbols
        db: Database instance for fallback (optional)
        
    Returns:
        Dictionary mapping symbol -> price
    """
    import pandas as pd
    
    if not symbols:
        return {}
        
    # Remove duplicates and empty strings
    unique_symbols = [s.upper() for s in set(symbols) if s]
    if not unique_symbols:
        return {}
        
    prices = {}
    
    # Try batch download first
    try:
        # threads=False to avoid resource contention/deadlocks on some systems
        # period="1d" gets the latest data
        data = yf.download(unique_symbols, period="1d", progress=False, threads=False)
        
        # Handle different return formats from yfinance
        if not data.empty:
            # Check if we have MultiIndex columns (multiple symbols) or single level (single symbol)
            if isinstance(data.columns, pd.MultiIndex):
                # Multiple symbols: data['Close'] or data['Adj Close'] is a DataFrame with symbols as columns
                # Note: yfinance recently changed behavior, 'Close' might be top level or second level depending on version
                # Usually it is (Attribute, Ticker)
                
                # We try to get 'Close'
                if 'Close' in data.columns.get_level_values(0):
                    closes = data['Close'] # This should be a DataFrame with tickers as columns
                    # Get the last row (latest date)
                    last_prices = closes.iloc[-1]
                    # Convert to dict, dropping NaNs
                    prices = last_prices.dropna().to_dict()
                elif 'Adj Close' in data.columns.get_level_values(0):
                    closes = data['Adj Close']
                    last_prices = closes.iloc[-1]
                    prices = last_prices.dropna().to_dict()
            else:
                # Single symbol or flat index (if only one symbol was requested or returned)
                # If single symbol passed to download, columns are ['Open', 'High', 'Low', 'Close', ...]
                if 'Close' in data.columns:
                    price = data['Close'].iloc[-1]
                    # Check if price is scalar or series
                    if pd.notna(price):
                        # If unique_symbols had 1 element, that's the key
                        if len(unique_symbols) == 1:
                            prices[unique_symbols[0]] = float(price)
                        else:
                            # This case matches if yfinance returns single level despite multiple symbols (unlikely but possible)
                            pass
                            
    except Exception as e:
        logger.warning(f"[PortfolioService] Batch fetch error: {e}")
        
    # Fill in missing symbols individually (fallback)
    # This ensures we don't return empty for symbols that failed batching but might work individually (or via DB)
    missing = [s for s in unique_symbols if s not in prices]
    if missing:
        # Only log if we missed more than expected (e.g. if batch failed completely)
        if len(missing) == len(unique_symbols):
             logger.warning(f"[PortfolioService] Batch failed completely, falling back to individual fetch")
        
        for sym in missing:
            p = fetch_current_price(sym, db)
            if p is not None:
                prices[sym] = p
                
    return prices
