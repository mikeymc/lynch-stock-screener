"""
Unit tests for Lynch scoring algorithms.
Tests the weighted algorithm to ensure it produces correct scores and ratings based on
different stock scenarios.
"""

import pytest
from unittest.mock import Mock, MagicMock
from lynch_criteria import LynchCriteria, ALGORITHM_METADATA


class TestAlgorithmMetadata:
    """Test algorithm metadata is properly defined."""

    def test_weighted_algorithm_has_metadata(self):
        """Ensure weighted algorithm has complete metadata."""
        assert 'weighted' in ALGORITHM_METADATA, "Missing metadata for weighted"

        metadata = ALGORITHM_METADATA['weighted']
        assert 'name' in metadata, "weighted missing 'name'"
        assert 'short_desc' in metadata, "weighted missing 'short_desc'"
        assert 'description' in metadata, "weighted missing 'description'"
        assert 'recommended' in metadata, "weighted missing 'recommended'"

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

        # Mock get_algorithm_configs to return a list with config dict
        mock_db.get_algorithm_configs.return_value = [{
            'id': 1,
            'name': 'test_config',
            'peg_excellent': 1.0,
            'peg_good': 1.5,
            'peg_fair': 2.0,
            'debt_excellent': 0.5,
            'debt_good': 1.0,
            'debt_moderate': 2.0,
            'inst_own_min': 0.4,
            'inst_own_max': 0.8,
            'revenue_growth_excellent': 15.0,
            'revenue_growth_good': 10.0,
            'revenue_growth_fair': 5.0,
            'income_growth_excellent': 15.0,
            'income_growth_good': 10.0,
            'income_growth_fair': 5.0,
            'weight_peg': 0.35,
            'weight_consistency': 0.25,
            'weight_debt': 0.20,
            'weight_ownership': 0.20
        }]

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

        # Mock get_algorithm_configs to return a list with config dict
        mock_db.get_algorithm_configs.return_value = [{
            'id': 1,
            'name': 'test_config',
            'peg_excellent': 1.0,
            'peg_good': 1.5,
            'peg_fair': 2.0,
            'debt_excellent': 0.5,
            'debt_good': 1.0,
            'debt_moderate': 2.0,
            'inst_own_min': 0.4,
            'inst_own_max': 0.8,
            'revenue_growth_excellent': 15.0,
            'revenue_growth_good': 10.0,
            'revenue_growth_fair': 5.0,
            'income_growth_excellent': 15.0,
            'income_growth_good': 10.0,
            'income_growth_fair': 5.0,
            'weight_peg': 0.35,
            'weight_consistency': 0.25,
            'weight_debt': 0.20,
            'weight_ownership': 0.20
        }]

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

    def test_weighted_algorithm_returns_required_fields(self, mock_criteria):
        """Weighted algorithm must return algorithm, overall_score, overall_status, rating_label."""
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

        result = mock_criteria._evaluate_weighted('REQ', test_data)

        assert 'algorithm' in result, "Missing 'algorithm'"
        assert 'overall_score' in result, "Missing 'overall_score'"
        assert 'overall_status' in result, "Missing 'overall_status'"
        assert 'rating_label' in result, "Missing 'rating_label'"
        assert result['algorithm'] == 'weighted', "Wrong algorithm value"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
