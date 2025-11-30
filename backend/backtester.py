import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict, Any, Optional
import logging
from database import Database
from lynch_criteria import LynchCriteria
from earnings_analyzer import EarningsAnalyzer

logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self, db: Database):
        self.db = db
        self.analyzer = EarningsAnalyzer(db)
        self.criteria = LynchCriteria(db, self.analyzer)

    def fetch_historical_prices(self, symbol: str, start_date: str, end_date: str):
        """
        Fetch historical prices from yfinance and save to database.
        """
        try:
            # Add buffer to start date to ensure we have coverage
            start_dt = datetime.fromisoformat(start_date)
            buffer_start = (start_dt - timedelta(days=10)).strftime('%Y-%m-%d')
            
            ticker = yf.Ticker(symbol)
            history = ticker.history(start=buffer_start, end=end_date)
            
            if history.empty:
                logger.warning(f"No price history found for {symbol}")
                return

            price_data = []
            for date, row in history.iterrows():
                price_data.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'close': float(row['Close']),
                    'adjusted_close': float(row['Close']), # yfinance 'Close' is adjusted by default usually, but let's be safe
                    'volume': int(row['Volume'])
                })
            
            self.db.save_price_history(symbol, price_data)
            self.db.flush()
            
            logger.info(f"Saved {len(price_data)} price points for {symbol}")
            
        except Exception as e:
            logger.error(f"Error fetching history for {symbol}: {e}")

    def get_historical_score(self, symbol: str, date: str, overrides: Dict[str, float] = None) -> Optional[Dict[str, Any]]:
        """
        Reconstruct the Lynch Score for a stock as it would have appeared on a specific date.
        """
        # 1. Get Price on that date
        price_history = self.db.get_price_history(symbol, start_date=date, end_date=date)
        if not price_history:
            # Try to find the closest previous trading day
            start_dt = datetime.fromisoformat(date)
            lookback_start = (start_dt - timedelta(days=5)).strftime('%Y-%m-%d')
            price_history = self.db.get_price_history(symbol, start_date=lookback_start, end_date=date)
            
            if not price_history:
                logger.warning(f"No price data for {symbol} on or before {date}")
                return None
            
            # Use the last available price
            current_price = price_history[-1]['close']
        else:
            current_price = price_history[0]['close']

        # 2. Get Earnings History known BEFORE that date
        # We need to filter earnings reports that were released before the target date.
        # Since our earnings_history table doesn't have a 'release_date' column for every row (it has fiscal_end),
        # we have to approximate.
        # Usually annual reports are out within 3 months of fiscal end.
        # For this implementation, we will use the 'year' and assume data is available by April of next year.
        # OR better: We use the data available in the DB but we need to be careful not to use future years.

        all_earnings = self.db.get_earnings_history(symbol)
        target_year = datetime.fromisoformat(date).year

        # Filter out earnings from future years relative to the backtest date
        # If date is Nov 2023, we can see 2022 annual report.
        # We might see 2023 Q1, Q2, Q3 if we had quarterly data.
        # For annual data: if date is > April 2023, we assume 2022 data is known.

        known_earnings = []
        for earnings in all_earnings:
            # Simple logic: If earnings year < target_year, it's definitely known.
            # If earnings year == target_year, it's NOT known yet (usually).
            if earnings['year'] < target_year:
                known_earnings.append(earnings)

        if not known_earnings:
            return None

        # Deduplicate by year+period (database has duplicate entries)
        unique_earnings = {}
        for e in known_earnings:
            key = (e['year'], e.get('period', 'annual'))
            if key not in unique_earnings:
                unique_earnings[key] = e

        known_earnings = list(unique_earnings.values())

        # Sort by year desc
        known_earnings.sort(key=lambda x: x['year'], reverse=True)
        latest_earnings = known_earnings[0]
        logger.debug(f"{symbol}: Found {len(known_earnings)} unique years of known earnings before {date}")
        
        # 3. Reconstruct Metrics using Net Income (immune to stock splits)
        # Get current metrics to estimate shares outstanding
        current_metrics = self.db.get_stock_metrics(symbol)
        
        # Use net income for growth calculations (more stable than EPS)
        net_income = latest_earnings.get('net_income')
        
        # Calculate synthetic EPS using estimated shares
        # Estimate shares: current_market_cap / current_price
        if current_metrics and current_metrics.get('price') and current_metrics.get('market_cap'):
            shares_outstanding = current_metrics['market_cap'] / current_metrics['price']
            if net_income and shares_outstanding > 0:
                eps = net_income / shares_outstanding
                pe_ratio = current_price / eps if eps > 0 else None
            else:
                eps = latest_earnings.get('eps')  # Fallback to stored EPS
                pe_ratio = current_price / eps if eps and eps > 0 else None
        else:
            eps = latest_earnings.get('eps')  # Fallback
            pe_ratio = current_price / eps if eps and eps > 0 else None
            
        # Calculate Earnings Growth (CAGR) using net income (split-resistant)
        # We need at least 3 years of history for a valid CAGR
        earnings_cagr = None
        if len(known_earnings) >= 3:
            oldest = known_earnings[min(len(known_earnings)-1, 4)] # Max 5 years back
            years = latest_earnings['year'] - oldest['year']
            
            latest_ni = latest_earnings.get('net_income')
            oldest_ni = oldest.get('net_income')
            
            if years > 0 and oldest_ni and oldest_ni > 0 and latest_ni and latest_ni > 0:
                earnings_cagr = ((latest_ni / oldest_ni) ** (1/years) - 1) * 100
        
        # Calculate Revenue Growth (CAGR)
        revenue_cagr = None
        if len(known_earnings) >= 3:
            oldest = known_earnings[min(len(known_earnings)-1, 4)] # Max 5 years back
            years = latest_earnings['year'] - oldest['year']
            
            latest_rev = latest_earnings.get('revenue')
            oldest_rev = oldest.get('revenue')
            
            if years > 0 and oldest_rev and oldest_rev > 0 and latest_rev and latest_rev > 0:
                revenue_cagr = ((latest_rev / oldest_rev) ** (1/years) - 1) * 100

        # Calculate market cap using estimated shares
        if current_metrics and current_metrics.get('price') and current_metrics.get('market_cap'):
            shares_outstanding = current_metrics['market_cap'] / current_metrics['price']
            market_cap = current_price * shares_outstanding
        else:
            market_cap = None

        base_data = {
            'symbol': symbol,
            'price': current_price,
            'pe_ratio': pe_ratio,
            'peg_ratio': None, # Calculated by criteria
            'earnings_cagr': earnings_cagr,
            'revenue_cagr': revenue_cagr,
            'debt_to_equity': latest_earnings.get('debt_to_equity'), # Use historical D/E if available
            'institutional_ownership': current_metrics.get('institutional_ownership'), # Limitation: We don't have historical ownership
            'dividend_yield': (latest_earnings.get('dividend_amount', 0) / current_price * 100) if latest_earnings.get('dividend_amount') else 0,
            'market_cap': market_cap,
            'sector': current_metrics.get('sector'),
            'country': current_metrics.get('country'),
            'consistency_score': 50, # Placeholder
            'institutional_ownership_score': 50, # Placeholder
            'debt_score': 50, # Placeholder
            'peg_score': 0 # Placeholder
        }
        
        # Recalculate derived scores using LynchCriteria logic
        # We need to manually call the scoring methods because evaluate_stock fetches fresh data
        
        # PEG
        base_data['peg_ratio'] = self.criteria.calculate_peg_ratio(pe_ratio, earnings_cagr)
        base_data['peg_status'] = self.criteria.evaluate_peg(base_data['peg_ratio'])
        base_data['peg_score'] = self.criteria.calculate_peg_score(base_data['peg_ratio'])
        logger.debug(f"{symbol}: PEG Ratio={base_data['peg_ratio']}, Score={base_data['peg_score']}, CAGR={earnings_cagr}")
        
        # Debt
        base_data['debt_status'] = self.criteria.evaluate_debt(base_data['debt_to_equity'])
        base_data['debt_score'] = self.criteria.calculate_debt_score(base_data['debt_to_equity'])
        
        # Ownership (using current as proxy, known limitation)
        base_data['institutional_ownership_status'] = self.criteria.evaluate_institutional_ownership(base_data['institutional_ownership'])
        base_data['institutional_ownership_score'] = self.criteria.calculate_institutional_ownership_score(base_data['institutional_ownership'])

        # 4. Calculate Score using historical data
        # We pass the reconstructed historical data as custom_metrics to avoid fetching current data
        score_result = self.criteria.evaluate_stock(
            symbol, 
            algorithm='weighted', 
            overrides=overrides,
            custom_metrics=base_data
        )
        return score_result

    def run_backtest(self, symbol: str, years_back: int = 1, overrides: Dict[str, float] = None) -> Dict[str, Any]:
        """
        Run a backtest for a single stock.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years_back)
        start_date_str = start_date.strftime('%Y-%m-%d')
        
        # 1. Ensure we have price history
        self.fetch_historical_prices(symbol, start_date_str, end_date.strftime('%Y-%m-%d'))
        
        # 3. Calculate Historical Score (at start date)
        # This returns the full scoring result including the score
        historical_analysis = self.get_historical_score(symbol, start_date_str, overrides=overrides)
        
        if not historical_analysis:
            return {'error': 'Insufficient historical data'}
            
        # 3. Calculate Return
        start_price = historical_analysis['price']
        
        # Get current price (or end of backtest period price)
        current_price_data = self.db.get_price_history(symbol, start_date=end_date.strftime('%Y-%m-%d'))
        if current_price_data:
            end_price = current_price_data[-1]['close']
        else:
            # Fallback to current metrics if today's price history isn't saved yet
            metrics = self.db.get_stock_metrics(symbol)
            end_price = metrics['price'] if metrics else None
            
        if not start_price or not end_price:
             return {'error': 'Could not determine start or end price'}
             
        total_return = ((end_price - start_price) / start_price) * 100
        
        return {
            'symbol': symbol,
            'backtest_date': start_date_str,
            'start_price': start_price,
            'end_price': end_price,
            'total_return': total_return,
            'historical_score': historical_analysis['overall_score'],
            'historical_rating': historical_analysis['rating_label'],
            'historical_data': historical_analysis
        }
