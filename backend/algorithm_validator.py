import yfinance as yf
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import time

from database import Database
from backtester import Backtester

logger = logging.getLogger(__name__)

class AlgorithmValidator:
    def __init__(self, db: Database):
        self.db = db
        self.backtester = Backtester(db)
        self.price_cache = {}  # Cache price history between runs
        
    def get_sp500_symbols(self) -> List[str]:
        """Fetch S&P 500 stock symbols from Wikipedia"""
        try:
            # Read S&P 500 table from Wikipedia with User-Agent to avoid 403
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'

            # pandas read_html can accept storage_options for headers
            import urllib.request
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

            with urllib.request.urlopen(req) as response:
                tables = pd.read_html(response.read())
                # S&P 500 table is the second table (index 1), first is a warning
                sp500_table = tables[1]
                symbols = sp500_table['Symbol'].tolist()

                # Clean symbols (remove dots for BRK.B -> BRK-B format)
                symbols = [s.replace('.', '-') for s in symbols]

                logger.info(f"Fetched {len(symbols)} S&P 500 symbols from Wikipedia")
                return symbols
        except Exception as e:
            logger.error(f"Error fetching S&P 500 symbols: {e}")
            # Fallback to a static list of major stocks if fetch fails
            logger.warning("Using fallback list of 36 major stocks")
            return [
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'BRK-B',
                'UNH', 'JNJ', 'JPM', 'V', 'XOM', 'PG', 'MA', 'HD', 'CVX', 'LLY',
                'ABBV', 'MRK', 'PEP', 'KO', 'COST', 'AVGO', 'WMT', 'ADBE', 'MCD',
                'NKE', 'DIS', 'CRM', 'CSCO', 'ACN', 'TMO', 'VZ', 'ABT', 'NFLX'
            ]
    
    def run_sp500_backtests(self, years_back: int, max_workers: int = 5, limit: int = None, force_rerun: bool = False, overrides: Dict[str, float] = None) -> Dict[str, Any]:
        """
        Run backtests on all S&P 500 stocks
        
        Args:
            years_back: Number of years to backtest
            max_workers: Number of parallel threads
            limit: Optional limit on number of stocks to process (for testing)
        
        Returns:
            Dict with results summary
        """
        symbols = self.get_sp500_symbols()
        if limit:
            symbols = symbols[:limit]
        
        total_symbols = len(symbols)
        results = []
        errors = []
        
        logger.info(f"Starting backtest validation for {total_symbols} stocks, {years_back} years back")
        
        # Reload settings to ensure we use the latest configuration
        self.backtester.criteria.reload_settings()
        logger.info("Reloaded algorithm settings")
        
        start_time = time.time()
        processed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_symbol = {
                executor.submit(self._backtest_with_cache, symbol, years_back, force_rerun, overrides): symbol  
                for symbol in symbols
            }
            
            # Process completed tasks
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                processed += 1
                
                try:
                    result = future.result()
                    if result and 'error' not in result:
                        results.append(result)
                        self.db.save_backtest_result(result)
                        logger.info(f"[{processed}/{total_symbols}] {symbol}: {result['total_return']:.2f}% return, score {result['historical_score']}")
                    else:
                        error_msg = result.get('error', 'Unknown error') if result else 'No result'
                        errors.append({'symbol': symbol, 'error': error_msg})
                        logger.warning(f"[{processed}/{total_symbols}] {symbol}: {error_msg}")
                except Exception as e:
                    errors.append({'symbol': symbol, 'error': str(e)})
                    logger.error(f"[{processed}/{total_symbols}] {symbol}: Exception - {e}")
                
                # Progress update every 10 stocks
                if processed % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = processed / elapsed
                    eta = (total_symbols - processed) / rate if rate > 0 else 0
                    logger.info(f"Progress: {processed}/{total_symbols} ({processed/total_symbols*100:.1f}%), ETA: {eta/60:.1f} minutes")
        
        # Ensure all writes are flushed
        self.db.flush()
        
        elapsed_time = time.time() - start_time
        
        summary = {
            'total_processed': processed,
            'successful': len(results),
            'errors': len(errors),
            'years_back': years_back,
            'elapsed_time': elapsed_time,
            'error_list': errors[:10]  # First 10 errors for debugging
        }
        
        logger.info(f"Validation complete: {len(results)} successful, {len(errors)} errors in {elapsed_time/60:.1f} minutes")
        
        return summary
    
    def _backtest_with_cache(self, symbol: str, years_back: int, force_rerun: bool = False, overrides: Dict[str, float] = None) -> Optional[Dict[str, Any]]:
        """
        Run backtest with price caching
        
        Reuses price data if already fetched for this symbol
        """
        try:
            if not force_rerun:
                # Check if we already have the result
                existing_results = self.db.get_backtest_results(years_back=years_back)
                for result in existing_results:
                    if result['symbol'] == symbol:
                        logger.debug(f"{symbol}: Using cached result")
                        return None  # Already have this result
            
            # Run backtest - backtester handles its own price caching
            result = self.backtester.run_backtest(symbol, years_back=years_back, overrides=overrides)
            
            # Add years_back to result for database storage
            if 'error' not in result:
                result['years_back'] = years_back
            
            return result
        except Exception as e:
            logger.error(f"Error backtesting {symbol}: {e}")
            return {'error': str(e)}
