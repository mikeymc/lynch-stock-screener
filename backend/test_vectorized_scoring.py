# ABOUTME: Tests for vectorized scoring parity with scalar evaluate_stock
# ABOUTME: Ensures evaluate_batch produces identical scores to the existing single-stock evaluation

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from earnings_analyzer import EarningsAnalyzer
from lynch_criteria import LynchCriteria
from stock_vectors import StockVectors, DEFAULT_ALGORITHM_CONFIG


class TestVectorizedScoring:
    """Test suite for vectorized scoring parity."""
    
    @pytest.fixture
    def setup(self):
        """Set up database and services."""
        db = Database()
        analyzer = EarningsAnalyzer(db)
        criteria = LynchCriteria(db, analyzer)
        vectors = StockVectors(db)
        return db, analyzer, criteria, vectors
    
    def test_load_vectors(self, setup):
        """Test that vectors load successfully with expected columns."""
        db, analyzer, criteria, vectors = setup
        
        df = vectors.load_vectors(country_filter='US')
        
        # Check required columns exist
        required_columns = [
            'symbol', 'price', 'market_cap', 'pe_ratio', 'debt_to_equity',
            'institutional_ownership', 'sector', 'company_name',
            'earnings_cagr', 'revenue_cagr', 'peg_ratio',
            'income_consistency_score', 'revenue_consistency_score'
        ]
        for col in required_columns:
            assert col in df.columns, f"Missing column: {col}"
        
        # Should have some stocks
        assert len(df) > 0, "No stocks loaded"
        print(f"Loaded {len(df)} stocks")
    
    def test_evaluate_batch_output_shape(self, setup):
        """Test that evaluate_batch returns expected columns."""
        db, analyzer, criteria, vectors = setup
        
        df = vectors.load_vectors(country_filter='US')
        result = criteria.evaluate_batch(df, DEFAULT_ALGORITHM_CONFIG)
        
        # Check output columns
        required_columns = [
            'symbol', 'overall_score', 'overall_status',
            'peg_score', 'peg_status',
            'debt_score', 'debt_status',
            'institutional_ownership_score', 'institutional_ownership_status'
        ]
        for col in required_columns:
            assert col in result.columns, f"Missing output column: {col}"
        
        # Should have same number of rows as input
        assert len(result) == len(df)
        
        # Should be sorted by overall_score descending
        scores = result['overall_score'].tolist()
        assert scores == sorted(scores, reverse=True), "Results not sorted by score"
    
    def test_score_parity_sample(self, setup):
        """Test that vectorized scores match scalar scores for sample stocks."""
        db, analyzer, criteria, vectors = setup
        
        # Load vectors
        df = vectors.load_vectors(country_filter='US')
        batch_result = criteria.evaluate_batch(df, DEFAULT_ALGORITHM_CONFIG)
        
        # Sample 10 stocks (or fewer if less available)
        sample_size = min(10, len(batch_result))
        sample_symbols = batch_result['symbol'].head(sample_size).tolist()
        
        mismatches = []
        
        for symbol in sample_symbols:
            # Get batch score
            batch_row = batch_result[batch_result['symbol'] == symbol].iloc[0]
            batch_score = batch_row['overall_score']
            batch_status = batch_row['overall_status']
            
            # Get scalar score
            scalar_result = criteria.evaluate_stock(symbol, algorithm='weighted')
            if scalar_result is None:
                continue
            
            scalar_score = scalar_result.get('overall_score', 0)
            scalar_status = scalar_result.get('overall_status', '')
            
            # Check parity (allow small floating point tolerance)
            score_diff = abs(batch_score - scalar_score)
            if score_diff > 1.0:  # Allow 1 point tolerance
                mismatches.append({
                    'symbol': symbol,
                    'batch_score': batch_score,
                    'scalar_score': scalar_score,
                    'diff': score_diff
                })
            
            if batch_status != scalar_status:
                mismatches.append({
                    'symbol': symbol,
                    'batch_status': batch_status,
                    'scalar_status': scalar_status
                })
        
        if mismatches:
            print("Score mismatches found:")
            for m in mismatches:
                print(f"  {m}")
        
        assert len(mismatches) == 0, f"Found {len(mismatches)} score mismatches"
    
    def test_performance(self, setup):
        """Test that vectorized scoring completes quickly."""
        import time
        
        db, analyzer, criteria, vectors = setup
        
        start = time.time()
        df = vectors.load_vectors(country_filter='US')
        load_time = time.time() - start
        
        start = time.time()
        result = criteria.evaluate_batch(df, DEFAULT_ALGORITHM_CONFIG)
        score_time = time.time() - start
        
        total_time = load_time + score_time
        
        print(f"Load time: {load_time*1000:.0f}ms")
        print(f"Score time: {score_time*1000:.0f}ms")
        print(f"Total time: {total_time*1000:.0f}ms")
        print(f"Stocks processed: {len(result)}")
        
        # Should complete in under 500ms for reasonable stock counts
        assert total_time < 0.5, f"Vectorized scoring too slow: {total_time*1000:.0f}ms"


if __name__ == '__main__':
    # Run with: python test_vectorized_scoring.py
    pytest.main([__file__, '-v', '-s'])
