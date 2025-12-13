"""
Unit tests for Lynch scoring algorithms.
Tests all 5 algorithms (weighted, two_tier, category_based, critical_factors, classic)
to ensure they produce correct scores and ratings based on different stock scenarios.
"""

import pytest
from unittest.mock import Mock, MagicMock
from lynch_criteria import LynchCriteria, ALGORITHM_METADATA


class TestAlgorithmMetadata:
    """Test algorithm metadata is properly defined."""

    def test_all_algorithms_have_metadata(self):
        """Ensure all algorithms have complete metadata."""
        expected_algorithms = ['weighted', 'two_tier', 'category_based', 'critical_factors', 'classic']

        for algo in expected_algorithms:
            assert algo in ALGORITHM_METADATA, f"Missing metadata for {algo}"

            metadata = ALGORITHM_METADATA[algo]
            assert 'name' in metadata, f"{algo} missing 'name'"
            assert 'short_desc' in metadata, f"{algo} missing 'short_desc'"
            assert 'description' in metadata, f"{algo} missing 'description'"
            assert 'recommended' in metadata, f"{algo} missing 'recommended'"

    def test_only_one_recommended_algorithm(self):
        """Ensure only one algorithm is marked as recommended."""
        recommended_count = sum(1 for meta in ALGORITHM_METADATA.values() if meta['recommended'])
        assert recommended_count == 1, f"Expected 1 recommended algorithm, found {recommended_count}"

    def test_weighted_is_recommended(self):
        """Verify that weighted algorithm is the recommended one."""
        assert ALGORITHM_METADATA['weighted']['recommended'] is True


class TestLynchCriteriaAlgorithms:
    """Test the algorithm evaluation methods."""

    @pytest.fixture
    def mock_criteria(self):
        """Create a LynchCriteria instance with mocked dependencies."""
        mock_db = Mock()
        mock_analyzer = Mock()

        # Mock get_all_settings to return proper settings structure
        mock_db.get_all_settings.return_value = {
            'peg_excellent': {'value': 1.0},
            'peg_good': {'value': 1.5},
            'peg_fair': {'value': 2.0},
            'debt_excellent': {'value': 0.5},
            'debt_good': {'value': 1.0},
            'debt_moderate': {'value': 2.0},
            'inst_own_min': {'value': 0.4},
            'inst_own_max': {'value': 0.8},
            'revenue_growth_excellent': {'value': 15.0},
            'revenue_growth_good': {'value': 10.0},
            'revenue_growth_fair': {'value': 5.0},
            'income_growth_excellent': {'value': 15.0},
            'income_growth_good': {'value': 10.0},
            'income_growth_fair': {'value': 5.0},
            'weight_peg': {'value': 0.35},
            'weight_consistency': {'value': 0.25},
            'weight_debt': {'value': 0.20},
            'weight_ownership': {'value': 0.20}
        }

        return LynchCriteria(mock_db, mock_analyzer)

    @pytest.fixture
    def excellent_stock_data(self):
        """Base data for an excellent stock (all metrics great)."""
        return {
            'symbol': 'EXCELLENT',
            'company_name': 'Excellent Company',
            'country': 'US',
            'market_cap': 5000000000,
            'sector': 'Technology',
            'ipo_year': 2015,
            'price': 150.0,
            'pe_ratio': 20.0,
            'peg_ratio': 0.8,  # Excellent: < 1.0
            'debt_to_equity': 0.2,  # Excellent: low debt
            'institutional_ownership': 0.4,  # Good: moderate
            'dividend_yield': 0.015,
            'earnings_cagr': 25.0,  # Strong growth
            'revenue_cagr': 22.0,
            'consistency_score': 90.0,  # Very consistent
            'peg_status': 'PASS',
            'peg_score': 100.0,
            'debt_status': 'PASS',
            'debt_score': 100.0,
            'institutional_ownership_status': 'PASS',
            'institutional_ownership_score': 100.0,
            'metrics': {}
        }

    @pytest.fixture
    def poor_stock_data(self):
        """Base data for a poor stock (all metrics bad)."""
        return {
            'symbol': 'POOR',
            'company_name': 'Poor Company',
            'country': 'US',
            'market_cap': 100000000,
            'sector': 'Technology',
            'ipo_year': 2020,
            'price': 5.0,
            'pe_ratio': 50.0,
            'peg_ratio': 3.5,  # Poor: > 2.0
            'debt_to_equity': 1.5,  # Poor: high debt
            'institutional_ownership': 0.7,  # Poor: too high
            'dividend_yield': 0.0,
            'earnings_cagr': 5.0,  # Weak growth
            'revenue_cagr': 3.0,
            'consistency_score': 30.0,  # Inconsistent
            'peg_status': 'FAIL',
            'peg_score': 10.0,
            'debt_status': 'FAIL',
            'debt_score': 10.0,
            'institutional_ownership_status': 'FAIL',
            'institutional_ownership_score': 10.0,
            'metrics': {}
        }

    @pytest.fixture
    def mixed_stock_data(self):
        """Base data for a mixed stock (some good, some bad metrics)."""
        return {
            'symbol': 'MIXED',
            'company_name': 'Mixed Company',
            'country': 'US',
            'market_cap': 1000000000,
            'sector': 'Technology',
            'ipo_year': 2018,
            'price': 50.0,
            'pe_ratio': 25.0,
            'peg_ratio': 1.3,  # Borderline
            'debt_to_equity': 0.7,  # Moderate-high
            'institutional_ownership': 0.5,  # Right at threshold
            'dividend_yield': 0.02,
            'earnings_cagr': 15.0,  # Decent growth
            'revenue_cagr': 12.0,
            'consistency_score': 60.0,  # Average
            'peg_status': 'CLOSE',
            'peg_score': 70.0,
            'debt_status': 'CLOSE',
            'debt_score': 50.0,
            'institutional_ownership_status': 'PASS',
            'institutional_ownership_score': 75.0,
            'metrics': {}
        }

    # Test Weighted Algorithm
    def test_weighted_excellent_stock(self, mock_criteria, excellent_stock_data):
        """Weighted algorithm should give high score to excellent stock."""
        result = mock_criteria._evaluate_weighted('EXCELLENT', excellent_stock_data)

        assert result['algorithm'] == 'weighted'
        assert result['overall_score'] >= 80, "Excellent stock should score >= 80"
        assert result['overall_status'] == 'STRONG_BUY'
        assert 'breakdown' in result
        assert result['breakdown']['peg_contribution'] > 0

    def test_weighted_poor_stock(self, mock_criteria, poor_stock_data):
        """Weighted algorithm should give low score to poor stock."""
        result = mock_criteria._evaluate_weighted('POOR', poor_stock_data)

        assert result['algorithm'] == 'weighted'
        assert result['overall_score'] < 40, "Poor stock should score < 40"
        assert result['overall_status'] in ['AVOID', 'CAUTION']

    def test_weighted_mixed_stock(self, mock_criteria, mixed_stock_data):
        """Weighted algorithm should give medium score to mixed stock."""
        result = mock_criteria._evaluate_weighted('MIXED', mixed_stock_data)

        assert result['algorithm'] == 'weighted'
        assert 40 <= result['overall_score'] < 80, "Mixed stock should score 40-80"
        assert result['overall_status'] in ['HOLD', 'BUY']

    # Test Two-Tier Algorithm
    def test_two_tier_excellent_stock(self, mock_criteria, excellent_stock_data):
        """Two-tier should pass must-haves and score well on nice-to-haves."""
        result = mock_criteria._evaluate_two_tier('EXCELLENT', excellent_stock_data)

        assert result['algorithm'] == 'two_tier'
        assert result['breakdown']['passed_must_haves'] is True
        assert result['overall_status'] != 'AVOID'
        assert result['overall_score'] > 0

    def test_two_tier_poor_stock_fails_must_haves(self, mock_criteria, poor_stock_data):
        """Two-tier should auto-AVOID if stock fails must-have criteria."""
        result = mock_criteria._evaluate_two_tier('POOR', poor_stock_data)

        assert result['algorithm'] == 'two_tier'
        assert result['breakdown']['passed_must_haves'] is False
        assert result['overall_status'] == 'AVOID'
        assert result['overall_score'] == 0
        assert 'deal_breakers' in result['breakdown']

    def test_two_tier_borderline_passes_must_haves(self, mock_criteria):
        """Two-tier should pass stock with PEG=1.9 and Debt=0.9 (just under limits)."""
        borderline_data = {
            'symbol': 'BORDER',
            'peg_ratio': 1.9,
            'debt_to_equity': 0.9,
            'consistency_score': 70,
            'peg_score': 50,
            'institutional_ownership_score': 80
        }
        result = mock_criteria._evaluate_two_tier('BORDER', borderline_data)

        assert result['breakdown']['passed_must_haves'] is True
        assert result['overall_status'] != 'AVOID'

    # Test Category-Based Algorithm
    def test_category_based_fast_grower(self, mock_criteria, excellent_stock_data):
        """Category-based should classify high-growth stock as fast_grower."""
        result = mock_criteria._evaluate_category_based('EXCELLENT', excellent_stock_data)

        assert result['algorithm'] == 'category_based'
        assert result['stock_category'] == 'fast_grower', f"Expected fast_grower, got {result['stock_category']}"
        assert 'breakdown' in result
        assert result['breakdown']['category'] == 'fast_grower'

    def test_category_based_stalwart(self, mock_criteria):
        """Category-based should classify moderate-growth stock as stalwart."""
        stalwart_data = {
            'symbol': 'STALWART',
            'earnings_cagr': 12.0,  # 10-20% = stalwart
            'revenue_cagr': 11.0,
            'peg_ratio': 1.2,
            'debt_to_equity': 0.5,
            'dividend_yield': 0.03,
            'market_cap': 50000000000,
            'consistency_score': 75,
            'peg_score': 85,
            'debt_score': 90,
            'institutional_ownership_score': 80
        }
        result = mock_criteria._evaluate_category_based('STALWART', stalwart_data)

        assert result['stock_category'] == 'stalwart'

    def test_category_based_slow_grower(self, mock_criteria):
        """Category-based should classify low-growth stock as slow_grower."""
        slow_data = {
            'symbol': 'SLOW',
            'earnings_cagr': 5.0,  # < 10% = slow grower
            'revenue_cagr': 4.0,
            'peg_ratio': 0.9,
            'debt_to_equity': 0.4,
            'dividend_yield': 0.05,
            'market_cap': 100000000000,
            'consistency_score': 80,
            'peg_score': 95,
            'debt_score': 95,
            'institutional_ownership_score': 85
        }
        result = mock_criteria._evaluate_category_based('SLOW', slow_data)

        assert result['stock_category'] == 'slow_grower'

    def test_category_based_turnaround(self, mock_criteria):
        """Category-based should classify negative-growth stock as turnaround."""
        turnaround_data = {
            'symbol': 'TURN',
            'earnings_cagr': -5.0,  # Negative = turnaround
            'revenue_cagr': -3.0,
            'peg_ratio': 0.5,
            'debt_to_equity': 0.8,
            'dividend_yield': 0.0,
            'market_cap': 500000000,
            'consistency_score': 40,
            'peg_score': 100,
            'debt_score': 60,
            'institutional_ownership_score': 70
        }
        result = mock_criteria._evaluate_category_based('TURN', turnaround_data)

        assert result['stock_category'] == 'turnaround'

    # Test Critical Factors Algorithm
    def test_critical_factors_excellent_stock(self, mock_criteria, excellent_stock_data):
        """Critical factors should rate excellent stock as BUY."""
        result = mock_criteria._evaluate_critical_factors('EXCELLENT', excellent_stock_data)

        assert result['algorithm'] == 'critical_factors'
        assert result['overall_status'] == 'BUY'
        assert result['overall_score'] >= 75
        assert 'reasons' in result['breakdown']

    def test_critical_factors_poor_stock(self, mock_criteria, poor_stock_data):
        """Critical factors should rate poor stock as AVOID."""
        result = mock_criteria._evaluate_critical_factors('POOR', poor_stock_data)

        assert result['algorithm'] == 'critical_factors'
        assert result['overall_status'] == 'AVOID'
        assert result['overall_score'] < 50

    def test_critical_factors_no_peg(self, mock_criteria):
        """Critical factors should handle missing PEG gracefully."""
        no_peg_data = {
            'symbol': 'NOPEG',
            'peg_ratio': None,
            'earnings_cagr': 15.0,
            'debt_to_equity': 0.4,
        }
        result = mock_criteria._evaluate_critical_factors('NOPEG', no_peg_data)

        assert result['algorithm'] == 'critical_factors'
        assert 'No PEG ratio available' in result['breakdown']['reasons']

    # Test Classic Algorithm
    def test_classic_all_pass(self, mock_criteria, excellent_stock_data):
        """Classic algorithm: all PASS statuses = PASS overall."""
        result = mock_criteria._evaluate_classic('EXCELLENT', excellent_stock_data)

        assert result['algorithm'] == 'classic'
        assert result['overall_status'] == 'PASS'
        assert result['rating_label'] == 'PASS'

    def test_classic_any_fail(self, mock_criteria):
        """Classic algorithm: any FAIL status = FAIL overall."""
        one_fail_data = {
            'symbol': 'ONEFAIL',
            'peg_status': 'PASS',
            'debt_status': 'PASS',
            'institutional_ownership_status': 'FAIL',  # One FAIL
            'peg_score': 100,
            'debt_score': 100,
            'institutional_ownership_score': 20
        }
        result = mock_criteria._evaluate_classic('ONEFAIL', one_fail_data)

        assert result['overall_status'] == 'FAIL'

    def test_classic_close_status(self, mock_criteria):
        """Classic algorithm: some PASS, some CLOSE (no FAIL) = CLOSE overall."""
        close_data = {
            'symbol': 'CLOSE',
            'peg_status': 'PASS',
            'debt_status': 'CLOSE',  # CLOSE
            'institutional_ownership_status': 'PASS',
            'peg_score': 100,
            'debt_score': 77,
            'institutional_ownership_score': 95
        }
        result = mock_criteria._evaluate_classic('CLOSE', close_data)

        assert result['overall_status'] == 'CLOSE'

    # Test evaluate_stock routing
    def test_evaluate_stock_routes_to_weighted(self, mock_criteria):
        """evaluate_stock should route to weighted algorithm by default."""
        mock_criteria._get_base_metrics = Mock(return_value={
            'symbol': 'TEST',
            'peg_ratio': 1.0,
            'peg_score': 100,
            'debt_score': 100,
            'institutional_ownership_score': 100,
            'consistency_score': 80
        })

        result = mock_criteria.evaluate_stock('TEST')  # No algorithm specified
        assert result['algorithm'] == 'weighted'

    def test_evaluate_stock_routes_to_specific_algorithm(self, mock_criteria):
        """evaluate_stock should route to specified algorithm."""
        mock_criteria._get_base_metrics = Mock(return_value={
            'symbol': 'TEST',
            'peg_status': 'PASS',
            'debt_status': 'PASS',
            'institutional_ownership_status': 'PASS',
            'peg_score': 100,
            'debt_score': 100,
            'institutional_ownership_score': 100
        })

        result = mock_criteria.evaluate_stock('TEST', algorithm='classic')
        assert result['algorithm'] == 'classic'

    def test_evaluate_stock_handles_unknown_algorithm(self, mock_criteria):
        """evaluate_stock should default to weighted for unknown algorithm."""
        mock_criteria._get_base_metrics = Mock(return_value={
            'symbol': 'TEST',
            'peg_ratio': 1.0,
            'peg_score': 100,
            'debt_score': 100,
            'institutional_ownership_score': 100,
            'consistency_score': 80
        })

        result = mock_criteria.evaluate_stock('TEST', algorithm='nonexistent')
        assert result['algorithm'] == 'weighted'


class TestAlgorithmConsistency:
    """Test that algorithms produce consistent results across different runs."""

    @pytest.fixture
    def mock_criteria(self):
        mock_db = Mock()
        mock_analyzer = Mock()

        # Mock get_all_settings to return proper settings structure
        mock_db.get_all_settings.return_value = {
            'peg_excellent': {'value': 1.0},
            'peg_good': {'value': 1.5},
            'peg_fair': {'value': 2.0},
            'debt_excellent': {'value': 0.5},
            'debt_good': {'value': 1.0},
            'debt_moderate': {'value': 2.0},
            'inst_own_min': {'value': 0.4},
            'inst_own_max': {'value': 0.8},
            'revenue_growth_excellent': {'value': 15.0},
            'revenue_growth_good': {'value': 10.0},
            'revenue_growth_fair': {'value': 5.0},
            'income_growth_excellent': {'value': 15.0},
            'income_growth_good': {'value': 10.0},
            'income_growth_fair': {'value': 5.0},
            'weight_peg': {'value': 0.35},
            'weight_consistency': {'value': 0.25},
            'weight_debt': {'value': 0.20},
            'weight_ownership': {'value': 0.20}
        }

        return LynchCriteria(mock_db, mock_analyzer)

    def test_weighted_deterministic(self, mock_criteria):
        """Weighted algorithm should produce same result for same input."""
        test_data = {
            'symbol': 'DET',
            'peg_ratio': 1.2,
            'peg_score': 85,
            'debt_score': 90,
            'institutional_ownership_score': 88,
            'consistency_score': 75
        }

        result1 = mock_criteria._evaluate_weighted('DET', test_data)
        result2 = mock_criteria._evaluate_weighted('DET', test_data)

        assert result1['overall_score'] == result2['overall_score']
        assert result1['overall_status'] == result2['overall_status']

    def test_all_algorithms_return_required_fields(self, mock_criteria):
        """All algorithms must return algorithm, overall_score, overall_status, rating_label."""
        test_data = {
            'symbol': 'REQ',
            'peg_ratio': 1.0,
            'peg_score': 100,
            'debt_score': 100,
            'institutional_ownership_score': 100,
            'consistency_score': 80,
            'peg_status': 'PASS',
            'debt_status': 'PASS',
            'institutional_ownership_status': 'PASS',
            'earnings_cagr': 20,
            'debt_to_equity': 0.3
        }

        algorithms = ['weighted', 'two_tier', 'category_based', 'critical_factors', 'classic']

        for algo in algorithms:
            method = getattr(mock_criteria, f'_evaluate_{algo}')
            result = method('REQ', test_data)

            assert 'algorithm' in result, f"{algo} missing 'algorithm'"
            assert 'overall_score' in result, f"{algo} missing 'overall_score'"
            assert 'overall_status' in result, f"{algo} missing 'overall_status'"
            assert 'rating_label' in result, f"{algo} missing 'rating_label'"
            assert result['algorithm'] == algo, f"{algo} has wrong algorithm value"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
