# ABOUTME: Re-scores stocks from latest screening session using cached metrics when algorithm settings change
# ABOUTME: Handles batch processing and database updates for screening_results table

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class StockRescorer:
    def __init__(self, db, criteria):
        self.db = db
        self.criteria = criteria

    def rescore_saved_stocks(self, algorithm: str = 'weighted', progress_callback=None) -> Dict[str, Any]:
        """
        Re-score all stocks from the latest screening session.

        Args:
            algorithm: Scoring algorithm to use (default: 'weighted')
            progress_callback: Optional callback function(current, total) to report progress

        Returns:
            Summary dict with counts and any errors
        """
        logger.info("Starting re-scoring of stocks from latest screening session...")

        # Get latest session
        latest_session = self.db.get_latest_session()
        if not latest_session:
            logger.info("No screening sessions found")
            return {
                'total': 0,
                'success': 0,
                'failed': 0,
                'errors': []
            }

        session_id = latest_session['session_id']
        symbols_to_rescore = self.db.get_screening_symbols(session_id)

        if not symbols_to_rescore:
            logger.info("No stocks in latest screening session")
            return {
                'total': 0,
                'success': 0,
                'failed': 0,
                'errors': []
            }

        logger.info(f"Re-scoring {len(symbols_to_rescore)} stocks from session {session_id}...")

        # Re-score in parallel (fast since using cached data)
        results = self._rescore_batch(symbols_to_rescore, algorithm, progress_callback)

        # Update database
        self._update_database(results)

        # Build summary
        summary = {
            'total': len(symbols_to_rescore),
            'success': len([r for r in results if r['success']]),
            'failed': len([r for r in results if not r['success']]),
            'errors': [r['error'] for r in results if not r['success']]
        }

        logger.info(f"✓ Re-scoring complete: {summary['success']}/{summary['total']} successful")
        return summary

    def _rescore_batch(self, symbols: List[str], algorithm: str, progress_callback=None) -> List[Dict[str, Any]]:
        """Re-score a batch of symbols in parallel."""
        results = []
        total = len(symbols)
        completed = 0

        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_symbol = {
                executor.submit(self._rescore_single, symbol, algorithm): symbol
                for symbol in symbols
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error re-scoring {symbol}: {e}")
                    results.append({
                        'symbol': symbol,
                        'success': False,
                        'error': str(e)
                    })
                
                # Report progress
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        return results

    def _rescore_single(self, symbol: str, algorithm: str) -> Dict[str, Any]:
        """Re-score a single stock using cached data."""
        try:
            # Get cached metrics (no API calls)
            metrics = self.db.get_stock_metrics(symbol)
            if not metrics:
                return {
                    'symbol': symbol,
                    'success': False,
                    'error': 'No cached metrics available'
                }

            # Calculate growth data from cached earnings history
            growth_data = self.criteria.analyzer.calculate_earnings_growth(symbol)

            # Extract growth metrics
            earnings_cagr = growth_data['earnings_cagr'] if growth_data else None
            revenue_cagr = growth_data['revenue_cagr'] if growth_data else None

            # Normalize consistency score (same logic as in lynch_criteria.py)
            raw_consistency = growth_data['consistency_score'] if growth_data else None
            if raw_consistency is not None:
                consistency_score = max(0.0, 100.0 - (raw_consistency * 2.0))
            else:
                consistency_score = None

            pe_ratio = metrics.get('pe_ratio')
            peg_ratio = self.criteria.calculate_peg_ratio(pe_ratio, earnings_cagr) if pe_ratio and earnings_cagr else None
            debt_to_equity = metrics.get('debt_to_equity')
            institutional_ownership = metrics.get('institutional_ownership')

            # Calculate individual metric scores (same as in lynch_criteria._get_base_metrics)
            if peg_ratio is None:
                peg_status = "FAIL"
                peg_score = 0.0
            else:
                peg_status = self.criteria.evaluate_peg(peg_ratio)
                peg_score = self.criteria.calculate_peg_score(peg_ratio)

            debt_status = self.criteria.evaluate_debt(debt_to_equity)
            debt_score = self.criteria.calculate_debt_score(debt_to_equity)

            inst_ownership_status = self.criteria.evaluate_institutional_ownership(institutional_ownership)
            inst_ownership_score = self.criteria.calculate_institutional_ownership_score(institutional_ownership)

            revenue_growth_score = self.criteria.calculate_revenue_growth_score(revenue_cagr)
            income_growth_score = self.criteria.calculate_income_growth_score(earnings_cagr)

            # Build custom_metrics dict with all required fields
            custom_metrics = {
                'metrics': metrics,
                'symbol': symbol,
                'company_name': metrics.get('company_name'),
                'country': metrics.get('country'),
                'market_cap': metrics.get('market_cap'),
                'sector': metrics.get('sector'),
                'ipo_year': metrics.get('ipo_year'),
                'price': metrics.get('price'),
                'pe_ratio': pe_ratio,
                'peg_ratio': peg_ratio,
                'debt_to_equity': debt_to_equity,
                'institutional_ownership': institutional_ownership,
                'dividend_yield': metrics.get('dividend_yield'),
                'earnings_cagr': earnings_cagr,
                'revenue_cagr': revenue_cagr,
                'consistency_score': consistency_score,
                'peg_status': peg_status,
                'peg_score': peg_score,
                'debt_status': debt_status,
                'debt_score': debt_score,
                'institutional_ownership_status': inst_ownership_status,
                'institutional_ownership_score': inst_ownership_score,
                'revenue_growth_score': revenue_growth_score,
                'income_growth_score': income_growth_score,
            }

            # Re-evaluate with new settings
            evaluation = self.criteria.evaluate_stock(
                symbol,
                algorithm=algorithm,
                custom_metrics=custom_metrics
            )

            if not evaluation:
                return {
                    'symbol': symbol,
                    'success': False,
                    'error': 'Evaluation returned None'
                }

            return {
                'symbol': symbol,
                'success': True,
                'evaluation': evaluation,
                'scored_at': datetime.now()
            }

        except Exception as e:
            logger.error(f"Failed to re-score {symbol}: {e}")
            return {
                'symbol': symbol,
                'success': False,
                'error': str(e)
            }

    def _update_database(self, results: List[Dict[str, Any]]):
        """Update screening_results table with new scores."""
        successful_results = [r for r in results if r['success']]

        for result in successful_results:
            symbol = result['symbol']
            evaluation = result['evaluation']
            scored_at = result['scored_at']

            # Update all screening_results rows for this symbol
            self.db.update_screening_result_scores(
                symbol=symbol,
                overall_score=evaluation.get('overall_score'),
                overall_status=evaluation.get('overall_status'),
                peg_score=evaluation.get('peg_score'),
                debt_score=evaluation.get('debt_score'),
                institutional_ownership_score=evaluation.get('institutional_ownership_score'),
                scored_at=scored_at
            )
