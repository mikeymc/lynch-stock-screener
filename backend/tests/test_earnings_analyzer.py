# ABOUTME: Tests for 5-year earnings growth analysis and CAGR calculations
# ABOUTME: Validates earnings consistency metrics and growth trend detection

import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from earnings_analyzer import EarningsAnalyzer
from database import Database


@pytest.fixture
def test_db():
    db_path = "test_analyzer_stocks.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def analyzer(test_db):
    return EarningsAnalyzer(test_db)


def test_calculate_cagr_positive_growth(analyzer):
    cagr = analyzer.calculate_cagr(100, 150, 5)
    assert cagr is not None
    assert 8 < cagr < 11


def test_calculate_cagr_negative_growth(analyzer):
    cagr = analyzer.calculate_cagr(150, 100, 5)
    assert cagr is not None
    assert cagr < 0


def test_calculate_cagr_zero_start_value(analyzer):
    cagr = analyzer.calculate_cagr(0, 100, 5)
    assert cagr is None


def test_calculate_cagr_zero_years(analyzer):
    cagr = analyzer.calculate_cagr(100, 150, 0)
    assert cagr is None


def test_calculate_growth_consistency_stable(analyzer):
    values = [100, 110, 121, 133, 146]
    consistency = analyzer.calculate_growth_consistency(values)
    assert consistency is not None
    assert consistency < 5


def test_calculate_growth_consistency_volatile(analyzer):
    values = [100, 150, 80, 200, 90]
    consistency = analyzer.calculate_growth_consistency(values)
    assert consistency is not None
    assert consistency > 20


def test_calculate_growth_consistency_insufficient_data(analyzer):
    values = [100]
    consistency = analyzer.calculate_growth_consistency(values)
    assert consistency is None


def test_calculate_earnings_growth_with_5_years(analyzer, test_db):
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_earnings_history("AAPL", 2019, 2.97, 260000000000)
    test_db.save_earnings_history("AAPL", 2020, 3.28, 275000000000)
    test_db.save_earnings_history("AAPL", 2021, 5.61, 366000000000)
    test_db.save_earnings_history("AAPL", 2022, 6.11, 394000000000)
    test_db.save_earnings_history("AAPL", 2023, 6.13, 383000000000)

    result = analyzer.calculate_earnings_growth("AAPL")

    assert result is not None
    assert 'earnings_cagr' in result
    assert 'revenue_cagr' in result
    assert 'consistency_score' in result
    assert result['earnings_cagr'] > 0
    assert result['revenue_cagr'] > 0


def test_calculate_earnings_growth_insufficient_data(analyzer, test_db):
    test_db.save_stock_basic("TEST", "Test Corp.", "NASDAQ", "Technology")
    test_db.save_earnings_history("TEST", 2023, 5.0, 100000000000)
    test_db.save_earnings_history("TEST", 2022, 4.5, 95000000000)

    result = analyzer.calculate_earnings_growth("TEST")

    assert result is None


def test_calculate_earnings_growth_no_data(analyzer, test_db):
    test_db.save_stock_basic("EMPTY", "Empty Corp.", "NASDAQ", "Technology")

    result = analyzer.calculate_earnings_growth("EMPTY")

    assert result is None


def test_calculate_earnings_growth_declining_earnings(analyzer, test_db):
    test_db.save_stock_basic("DECL", "Declining Corp.", "NASDAQ", "Technology")
    test_db.save_earnings_history("DECL", 2019, 10.0, 500000000000)
    test_db.save_earnings_history("DECL", 2020, 9.0, 480000000000)
    test_db.save_earnings_history("DECL", 2021, 8.0, 460000000000)
    test_db.save_earnings_history("DECL", 2022, 7.0, 440000000000)
    test_db.save_earnings_history("DECL", 2023, 6.0, 420000000000)

    result = analyzer.calculate_earnings_growth("DECL")

    assert result is not None
    assert result['earnings_cagr'] < 0
    assert result['revenue_cagr'] < 0


def test_calculate_earnings_growth_with_zeros(analyzer, test_db):
    test_db.save_stock_basic("ZERO", "Zero Corp.", "NASDAQ", "Technology")
    test_db.save_earnings_history("ZERO", 2019, 0.0, 100000000000)
    test_db.save_earnings_history("ZERO", 2020, 1.0, 110000000000)
    test_db.save_earnings_history("ZERO", 2021, 2.0, 120000000000)
    test_db.save_earnings_history("ZERO", 2022, 3.0, 130000000000)
    test_db.save_earnings_history("ZERO", 2023, 4.0, 140000000000)

    result = analyzer.calculate_earnings_growth("ZERO")

    assert result is None or result['earnings_cagr'] is None
