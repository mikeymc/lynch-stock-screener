"""
Unit test for shares outstanding unit normalization

Tests that shares reported in millions (< 10,000) are correctly normalized
to actual share count by multiplying by 1,000,000.
"""
import pytest
from edgar_fetcher import EdgarFetcher


def test_shares_outstanding_unit_normalization():
    """Test that shares reported in millions are normalized to actual count"""
    fetcher = EdgarFetcher(user_agent="test@example.com")
    
    # Mock company facts with mixed units (some in millions, some actual)
    company_facts = {
        "facts": {
            "us-gaap": {
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            # Recent years: reported in millions (< 10,000)
                            {"form": "10-K", "fy": 2024, "val": 722, "end": "2024-12-31"},
                            {"form": "10-K", "fy": 2023, "val": 732, "end": "2023-12-31"},
                            {"form": "10-K", "fy": 2022, "val": 741, "end": "2022-12-31"},
                            
                            # Older years: reported in actual shares (> 1,000,000)
                            {"form": "10-K", "fy": 2021, "val": 750100000, "end": "2021-12-31"},
                            {"form": "10-K", "fy": 2020, "val": 764900000, "end": "2020-12-31"},
                        ]
                    }
                }
            }
        }
    }
    
    # Act
    shares_history = fetcher.parse_shares_outstanding_history(company_facts)
    
    # Assert - All shares should be normalized to actual count
    shares_by_year = {entry['year']: entry['shares'] for entry in shares_history}
    
    # Years 2022-2024 should be converted from millions to actual
    assert shares_by_year[2024] == 722_000_000, f"2024 shares should be 722M, got {shares_by_year[2024]:,}"
    assert shares_by_year[2023] == 732_000_000, f"2023 shares should be 732M, got {shares_by_year[2023]:,}"
    assert shares_by_year[2022] == 741_000_000, f"2022 shares should be 741M, got {shares_by_year[2022]:,}"
    
    # Years 2020-2021 should remain unchanged (already in actual count)
    assert shares_by_year[2021] == 750_100_000, f"2021 shares should remain 750.1M, got {shares_by_year[2021]:,}"
    assert shares_by_year[2020] == 764_900_000, f"2020 shares should remain 764.9M, got {shares_by_year[2020]:,}"
    
    # All values should be > 100 million (no public company has fewer shares)
    for year, shares in shares_by_year.items():
        assert shares > 100_000_000, f"Year {year} has suspiciously low share count: {shares:,}"
        assert shares < 100_000_000_000, f"Year {year} has suspiciously high share count: {shares:,}"
    
    print("✓ Shares outstanding normalization working correctly")


def test_eps_calculation_with_normalized_shares():
    """Test that EPS is calculated correctly after shares normalization"""
    fetcher = EdgarFetcher(user_agent="test@example.com")
    
    # Mock data matching McDonald's pattern (shares in millions for recent years)
    company_facts = {
        "facts": {
            "us-gaap": {
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            {"form": "10-K", "fy": 2024, "val": 722, "end": "2024-12-31"},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "val": 8223000000, "end": "2024-12-31"},  # $8.223B net income
                        ]
                    }
                }
            }
        }
    }
    
    # Act
    eps_history = fetcher.calculate_split_adjusted_annual_eps_history(company_facts)
    
    # Assert
    assert len(eps_history) == 1, "Should have 1 year of EPS data"
    
    eps_2024 = eps_history[0]
    assert eps_2024['year'] == 2024
    
    # EPS should be ~$11.39 (8,223,000,000 / 722,000,000)
    # NOT 11,390,774 (8,223,000,000 / 722)
    expected_eps = 8223000000 / 722_000_000  # ~11.39
    assert abs(eps_2024['eps'] - expected_eps) < 0.01, \
        f"EPS should be ~{expected_eps:.2f}, got {eps_2024['eps']:.2f}"
    
    assert 10 < eps_2024['eps'] < 15, \
        f"EPS should be in reasonable range (10-15), got {eps_2024['eps']:.2f}"
    
    print(f"✓ EPS calculated correctly: ${eps_2024['eps']:.2f}")


if __name__ == "__main__":
    test_shares_outstanding_unit_normalization()
    test_eps_calculation_with_normalized_shares()
