#!/usr/bin/env python3
"""Quick test runner to verify new scoring methods work correctly"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from lynch_criteria import LynchCriteria
from database import Database
from earnings_analyzer import EarningsAnalyzer

def test_new_methods(test_db):
    """Test the new metric-specific evaluation methods"""
    analyzer = EarningsAnalyzer(test_db)
    criteria = LynchCriteria(test_db, analyzer)

    print("Testing PEG evaluation methods...")

    # Test PEG evaluation
    assert criteria.evaluate_peg(0.8) == "PASS", "PEG 0.8 should PASS"
    assert criteria.evaluate_peg(1.3) == "CLOSE", "PEG 1.3 should be CLOSE"
    assert criteria.evaluate_peg(2.5) == "FAIL", "PEG 2.5 should FAIL"
    print("✓ PEG evaluation tests passed")

    # Test PEG scoring
    assert criteria.calculate_peg_score(0.5) == 100.0, "PEG 0.5 should score 100"
    score = criteria.calculate_peg_score(1.25)
    assert 75.0 <= score <= 100.0, f"PEG 1.25 should score 75-100, got {score}"
    score = criteria.calculate_peg_score(1.75)
    assert 25.0 <= score <= 75.0, f"PEG 1.75 should score 25-75, got {score}"
    score = criteria.calculate_peg_score(3.0)
    assert 0.0 <= score <= 25.0, f"PEG 3.0 should score 0-25, got {score}"
    print("✓ PEG scoring tests passed")

    print("\nTesting Debt evaluation methods...")

    # Test Debt evaluation
    assert criteria.evaluate_debt(0.3) == "PASS", "Debt 0.3 should PASS"
    assert criteria.evaluate_debt(0.8) == "CLOSE", "Debt 0.8 should be CLOSE"
    assert criteria.evaluate_debt(2.5) == "FAIL", "Debt 2.5 should FAIL"
    print("✓ Debt evaluation tests passed")

    # Test Debt scoring
    assert criteria.calculate_debt_score(0.3) == 100.0, "Debt 0.3 should score 100"
    score = criteria.calculate_debt_score(0.75)
    assert 75.0 <= score <= 100.0, f"Debt 0.75 should score 75-100, got {score}"
    score = criteria.calculate_debt_score(1.5)
    assert 25.0 <= score <= 75.0, f"Debt 1.5 should score 25-75, got {score}"
    score = criteria.calculate_debt_score(3.0)
    assert 0.0 <= score <= 25.0, f"Debt 3.0 should score 0-25, got {score}"
    print("✓ Debt scoring tests passed")

    print("\nTesting Institutional Ownership evaluation methods...")

    # Test Institutional Ownership evaluation
    assert criteria.evaluate_institutional_ownership(0.40) == "PASS", "InstOwn 40% should PASS"
    assert criteria.evaluate_institutional_ownership(0.10) == "CLOSE", "InstOwn 10% should be CLOSE (below minimum)"
    assert criteria.evaluate_institutional_ownership(0.80) == "FAIL", "InstOwn 80% should FAIL (too high)"
    print("✓ Institutional Ownership evaluation tests passed")

    # Test Institutional Ownership scoring
    assert criteria.calculate_institutional_ownership_score(0.40) == 100.0, "InstOwn 40% should score 100 (center)"
    score = criteria.calculate_institutional_ownership_score(0.30)
    assert 75.0 <= score <= 100.0, f"InstOwn 30% should score 75-100, got {score}"
    score = criteria.calculate_institutional_ownership_score(0.10)
    assert 0.0 <= score <= 75.0, f"InstOwn 10% should score 0-75, got {score}"
    score = criteria.calculate_institutional_ownership_score(0.80)
    assert 0.0 <= score <= 75.0, f"InstOwn 80% should score 0-75, got {score}"
    print("✓ Institutional Ownership scoring tests passed")

    print("\n" + "="*50)
    print("All tests passed! ✓")
    print("="*50)

if __name__ == "__main__":
    try:
        test_new_methods()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
