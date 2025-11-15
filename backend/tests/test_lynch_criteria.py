# ABOUTME: Tests for Peter Lynch criteria evaluation and stock flagging
# ABOUTME: Validates PASS/CLOSE/FAIL logic for PEG, debt, growth, and ownership metrics

import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lynch_criteria import LynchCriteria
from earnings_analyzer import EarningsAnalyzer
from database import Database


@pytest.fixture
def test_db():
    db_path = "test_lynch_stocks.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = Database(db_path)
    yield db
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def analyzer(test_db):
    return EarningsAnalyzer(test_db)


@pytest.fixture
def criteria(test_db, analyzer):
    return LynchCriteria(test_db, analyzer)


def test_calculate_peg_ratio(criteria):
    peg = criteria.calculate_peg_ratio(25.0, 25.0)
    assert peg == 1.0


def test_calculate_peg_ratio_zero_growth(criteria):
    peg = criteria.calculate_peg_ratio(25.0, 0.0)
    assert peg is None


def test_calculate_peg_ratio_negative_growth(criteria):
    peg = criteria.calculate_peg_ratio(25.0, -5.0)
    assert peg is None


def test_evaluate_peg_pass(criteria):
    result = criteria.evaluate_peg(0.8)
    assert result == "PASS"


def test_evaluate_peg_close(criteria):
    result = criteria.evaluate_peg(1.3)
    assert result == "CLOSE"


def test_evaluate_peg_fail(criteria):
    result = criteria.evaluate_peg(2.5)
    assert result == "FAIL"


def test_evaluate_debt_pass(criteria):
    result = criteria.evaluate_debt(0.3)
    assert result == "PASS"


def test_evaluate_debt_close(criteria):
    result = criteria.evaluate_debt(0.8)
    assert result == "CLOSE"


def test_evaluate_debt_fail(criteria):
    result = criteria.evaluate_debt(2.5)
    assert result == "FAIL"


def test_evaluate_institutional_ownership_pass(criteria):
    result = criteria.evaluate_institutional_ownership(0.40)
    assert result == "PASS"


def test_evaluate_institutional_ownership_too_low_fail(criteria):
    result = criteria.evaluate_institutional_ownership(0.10)
    assert result == "FAIL"


def test_evaluate_institutional_ownership_too_high_fail(criteria):
    result = criteria.evaluate_institutional_ownership(0.80)
    assert result == "FAIL"


def test_calculate_peg_score_excellent(criteria):
    score = criteria.calculate_peg_score(0.5)
    assert score == 100.0


def test_calculate_peg_score_good(criteria):
    score = criteria.calculate_peg_score(1.25)
    assert 75.0 <= score <= 100.0


def test_calculate_peg_score_fair(criteria):
    score = criteria.calculate_peg_score(1.75)
    assert 25.0 <= score <= 75.0


def test_calculate_peg_score_poor(criteria):
    score = criteria.calculate_peg_score(3.0)
    assert 0.0 <= score <= 25.0


def test_calculate_debt_score_excellent(criteria):
    score = criteria.calculate_debt_score(0.3)
    assert score == 100.0


def test_calculate_debt_score_good(criteria):
    score = criteria.calculate_debt_score(0.75)
    assert 75.0 <= score <= 100.0


def test_calculate_debt_score_moderate(criteria):
    score = criteria.calculate_debt_score(1.5)
    assert 25.0 <= score <= 75.0


def test_calculate_debt_score_high(criteria):
    score = criteria.calculate_debt_score(3.0)
    assert 0.0 <= score <= 25.0


def test_calculate_institutional_ownership_score_ideal_center(criteria):
    score = criteria.calculate_institutional_ownership_score(0.40)
    assert score == 100.0


def test_calculate_institutional_ownership_score_ideal_range(criteria):
    score = criteria.calculate_institutional_ownership_score(0.30)
    assert 75.0 <= score <= 100.0


def test_calculate_institutional_ownership_score_too_low(criteria):
    score = criteria.calculate_institutional_ownership_score(0.10)
    assert 0.0 <= score <= 75.0


def test_calculate_institutional_ownership_score_too_high(criteria):
    score = criteria.calculate_institutional_ownership_score(0.80)
    assert 0.0 <= score <= 75.0


def test_evaluate_stock_all_pass(criteria, test_db):
    test_db.save_stock_basic("PASS", "Pass Corp.", "NASDAQ", "Technology")
    metrics = {
        'price': 100.0,
        'pe_ratio': 12.0,
        'market_cap': 1000000000000,
        'debt_to_equity': 0.25,
        'institutional_ownership': 0.35,
        'revenue': 500000000000
    }
    test_db.save_stock_metrics("PASS", metrics)

    for year, eps, revenue in [(2019, 3.0, 400000000000), (2020, 3.5, 425000000000),
                                (2021, 4.0, 450000000000), (2022, 4.5, 475000000000),
                                (2023, 5.0, 500000000000)]:
        test_db.save_earnings_history("PASS", year, eps, revenue)

    result = criteria.evaluate_stock("PASS")

    assert result is not None
    assert result['overall_status'] == "PASS"
    assert result['peg_ratio'] < 1.0
    assert result['peg_status'] == "PASS"
    assert result['debt_status'] == "PASS"
    assert result['institutional_ownership_status'] == "PASS"


def test_evaluate_stock_some_close(criteria, test_db):
    test_db.save_stock_basic("CLOSE", "Close Corp.", "NASDAQ", "Technology")
    metrics = {
        'price': 100.0,
        'pe_ratio': 22.0,
        'market_cap': 1000000000000,
        'debt_to_equity': 0.8,  # In CLOSE range (0.5-1.0)
        'institutional_ownership': 0.48,
        'revenue': 500000000000
    }
    test_db.save_stock_metrics("CLOSE", metrics)

    for year, eps, revenue in [(2019, 3.0, 400000000000), (2020, 3.5, 425000000000),
                                (2021, 4.2, 450000000000), (2022, 4.6, 475000000000),
                                (2023, 5.2, 500000000000)]:
        test_db.save_earnings_history("CLOSE", year, eps, revenue)

    result = criteria.evaluate_stock("CLOSE")

    assert result is not None
    assert "CLOSE" in [result['peg_status'], result['debt_status'], result['institutional_ownership_status']]
    # Debt should be CLOSE with 0.8 (between 0.5 and 1.0)
    assert result['debt_status'] == "CLOSE"


def test_evaluate_stock_failing_peg(criteria, test_db):
    test_db.save_stock_basic("FAIL", "Fail Corp.", "NASDAQ", "Technology")
    metrics = {
        'price': 100.0,
        'pe_ratio': 50.0,
        'market_cap': 1000000000000,
        'debt_to_equity': 0.25,
        'institutional_ownership': 0.35,
        'revenue': 500000000000
    }
    test_db.save_stock_metrics("FAIL", metrics)

    for year, eps, revenue in [(2019, 3.0, 400000000000), (2020, 3.2, 420000000000),
                                (2021, 3.4, 440000000000), (2022, 3.6, 460000000000),
                                (2023, 3.8, 480000000000)]:
        test_db.save_earnings_history("FAIL", year, eps, revenue)

    result = criteria.evaluate_stock("FAIL")

    assert result is not None
    assert result['peg_status'] == "FAIL"
    assert result['overall_status'] != "PASS"


def test_evaluate_stock_insufficient_data(criteria, test_db):
    test_db.save_stock_basic("INSUFF", "Insufficient Corp.", "NASDAQ", "Technology")
    metrics = {
        'price': 100.0,
        'pe_ratio': 20.0,
        'market_cap': 1000000000000,
        'debt_to_equity': 0.25,
        'institutional_ownership': 0.35,
        'revenue': 500000000000
    }
    test_db.save_stock_metrics("INSUFF", metrics)

    result = criteria.evaluate_stock("INSUFF")

    assert result is not None
    assert result['overall_status'] == "FAIL"
    assert result['peg_ratio'] is None
    assert result['earnings_cagr'] is None


def test_evaluate_stock_missing_metrics(criteria, test_db):
    test_db.save_stock_basic("MISSING", "Missing Corp.", "NASDAQ", "Technology")

    result = criteria.evaluate_stock("MISSING")

    assert result is None


def test_evaluate_stock_no_pe_ratio(criteria, test_db):
    test_db.save_stock_basic("NOPE", "No PE Corp.", "NASDAQ", "Technology")
    metrics = {
        'price': 50.0,
        'pe_ratio': None,
        'market_cap': 500000000000,
        'debt_to_equity': 0.25,
        'institutional_ownership': 0.35,
        'revenue': 500000000000
    }
    test_db.save_stock_metrics("NOPE", metrics)
    test_db.save_earnings_history("NOPE", 2023, 2.0, 500000000000)
    test_db.save_earnings_history("NOPE", 2022, 1.8, 480000000000)
    test_db.save_earnings_history("NOPE", 2021, 1.5, 450000000000)

    result = criteria.evaluate_stock("NOPE")

    assert result is not None
    assert result['overall_status'] == "FAIL"
    assert result['peg_ratio'] is None
    assert result['peg_status'] == "FAIL"
    assert result['earnings_cagr'] is not None
