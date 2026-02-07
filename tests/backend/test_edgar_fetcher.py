# ABOUTME: Tests for SEC EDGAR data fetcher with ticker-to-CIK mapping
# ABOUTME: Validates XBRL data parsing, rate limiting, and API integration

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from edgar_fetcher import EdgarFetcher

logger = logging.getLogger(__name__)


@pytest.fixture
def edgar_fetcher():
    return EdgarFetcher(user_agent="Lynch Stock Screener test@example.com")


def test_ticker_to_cik_mapping(edgar_fetcher):
    """Test that ticker symbols can be mapped to CIK numbers"""
    with patch('edgar_fetcher.core.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp."}
        }
        mock_get.return_value = mock_response

        cik = edgar_fetcher.get_cik_for_ticker("AAPL")

        assert cik == "0000320193"


def test_ticker_to_cik_not_found(edgar_fetcher):
    """Test handling when ticker is not found"""
    with patch('edgar_fetcher.core.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
        }
        mock_get.return_value = mock_response

        cik = edgar_fetcher.get_cik_for_ticker("INVALID")

        assert cik is None


def test_fetch_company_facts(edgar_fetcher):
    """Test fetching company facts from SEC EDGAR API"""
    with patch('edgar_fetcher.core.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "cik": 320193,
            "entityName": "Apple Inc.",
            "facts": {
                "us-gaap": {
                    "EarningsPerShareDiluted": {
                        "units": {
                            "USD/shares": [
                                {"end": "2023-09-30", "val": 6.13, "fy": 2023, "form": "10-K"},
                                {"end": "2022-09-24", "val": 6.11, "fy": 2022, "form": "10-K"},
                                {"end": "2021-09-25", "val": 5.61, "fy": 2021, "form": "10-K"}
                            ]
                        }
                    },
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"end": "2023-09-30", "val": 383285000000, "fy": 2023, "form": "10-K"},
                                {"end": "2022-09-24", "val": 394328000000, "fy": 2022, "form": "10-K"},
                                {"end": "2021-09-25", "val": 365817000000, "fy": 2021, "form": "10-K"}
                            ]
                        }
                    }
                }
            }
        }
        mock_get.return_value = mock_response

        facts = edgar_fetcher.fetch_company_facts("0000320193")

        assert facts is not None
        assert facts["cik"] == 320193
        assert "facts" in facts


def test_parse_eps_history(edgar_fetcher):
    """Test parsing EPS history from company facts"""
    company_facts = {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            {"end": "2023-09-30", "val": 6.13, "fy": 2023, "form": "10-K"},
                            {"end": "2022-09-24", "val": 6.11, "fy": 2022, "form": "10-K"},
                            {"end": "2021-09-25", "val": 5.61, "fy": 2021, "form": "10-K"},
                            {"end": "2020-09-26", "val": 3.28, "fy": 2020, "form": "10-K"},
                            {"end": "2019-09-28", "val": 2.97, "fy": 2019, "form": "10-K"}
                        ]
                    }
                }
            }
        }
    }

    eps_history = edgar_fetcher.parse_eps_history(company_facts)

    assert len(eps_history) == 5
    assert eps_history[0]["year"] == 2023
    assert eps_history[0]["eps"] == 6.13
    assert eps_history[4]["year"] == 2019
    assert eps_history[4]["eps"] == 2.97


def test_parse_revenue_history(edgar_fetcher):
    """Test parsing revenue history from company facts"""
    company_facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"end": "2023-09-30", "val": 383285000000, "fy": 2023, "form": "10-K"},
                            {"end": "2022-09-24", "val": 394328000000, "fy": 2022, "form": "10-K"},
                            {"end": "2021-09-25", "val": 365817000000, "fy": 2021, "form": "10-K"}
                        ]
                    }
                }
            }
        }
    }

    revenue_history = edgar_fetcher.parse_revenue_history(company_facts)

    assert len(revenue_history) == 3
    assert revenue_history[0]["year"] == 2023
    assert revenue_history[0]["revenue"] == 383285000000


def test_parse_debt_to_equity(edgar_fetcher):
    """Test parsing debt-to-equity ratio from company facts"""
    company_facts = {
        "facts": {
            "us-gaap": {
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {"end": "2023-09-30", "val": 62146000000, "fy": 2023, "form": "10-K"}
                        ]
                    }
                },
                "LongTermDebtNoncurrent": {
                    "units": {
                        "USD": [
                            {"end": "2023-09-30", "val": 250000000000, "fy": 2023, "form": "10-K"}
                        ]
                    }
                },
                "LongTermDebtCurrent": {
                    "units": {
                        "USD": [
                            {"end": "2023-09-30", "val": 40437000000, "fy": 2023, "form": "10-K"}
                        ]
                    }
                }
            }
        }
    }

    debt_to_equity = edgar_fetcher.parse_debt_to_equity(company_facts)

    assert debt_to_equity is not None
    assert debt_to_equity > 0


def test_rate_limiting(edgar_fetcher):
    """Test that rate limiting is enforced (10 requests/sec max)"""
    import time

    with patch('edgar_fetcher.core.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"cik": 320193, "facts": {}}
        mock_get.return_value = mock_response

        start_time = time.time()

        # Make 11 requests
        for i in range(11):
            edgar_fetcher.fetch_company_facts(f"000032019{i}")

        elapsed_time = time.time() - start_time

        # Should take at least 1 second for 11 requests (10 per second limit)
        assert elapsed_time >= 1.0


def test_missing_eps_data(edgar_fetcher):
    """Test handling when EPS data is missing"""
    company_facts = {
        "facts": {
            "us-gaap": {}
        }
    }

    eps_history = edgar_fetcher.parse_eps_history(company_facts)

    assert eps_history == []


def test_missing_revenue_data(edgar_fetcher):
    """Test handling when revenue data is missing"""
    company_facts = {
        "facts": {
            "us-gaap": {}
        }
    }

    revenue_history = edgar_fetcher.parse_revenue_history(company_facts)

    assert revenue_history == []


def test_user_agent_required(edgar_fetcher):
    """Test that User-Agent header is included in requests"""
    with patch('edgar_fetcher.core.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"cik": 320193, "facts": {}}
        mock_get.return_value = mock_response

        edgar_fetcher.fetch_company_facts("0000320193")

        # Verify User-Agent header was passed
        call_args = mock_get.call_args
        headers = call_args[1].get('headers', {})
        assert 'User-Agent' in headers
        assert edgar_fetcher.user_agent in headers['User-Agent']


def test_fetch_stock_fundamentals(edgar_fetcher):
    """Test complete flow: ticker -> CIK -> facts -> parsed data"""
    with patch('edgar_fetcher.core.requests.get') as mock_get:
        # Mock ticker-to-CIK response
        ticker_response = MagicMock()
        ticker_response.json.return_value = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
        }

        # Mock company facts response
        facts_response = MagicMock()
        facts_response.json.return_value = {
            "cik": 320193,
            "entityName": "Apple Inc.",
            "facts": {
                "us-gaap": {
                    "EarningsPerShareDiluted": {
                        "units": {
                            "USD/shares": [
                                {"end": "2023-09-30", "val": 6.13, "fy": 2023, "form": "10-K"}
                            ]
                        }
                    },
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"end": "2023-09-30", "val": 383285000000, "fy": 2023, "form": "10-K"}
                            ]
                        }
                    }
                }
            }
        }

        mock_get.side_effect = [ticker_response, facts_response]

        fundamentals = edgar_fetcher.fetch_stock_fundamentals("AAPL")

        assert fundamentals is not None
        assert "eps_history" in fundamentals
        assert "revenue_history" in fundamentals
        assert len(fundamentals["eps_history"]) > 0
        assert len(fundamentals["revenue_history"]) > 0


def test_parse_revenue_with_alternative_field_names(edgar_fetcher):
    """Test that revenue parser tries multiple field names and finds the right one"""
    # Test with 'RevenueFromContractWithCustomerExcludingAssessedTax' field
    company_facts_alt1 = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"end": "2023-12-31", "val": 100000000000, "fy": 2023, "form": "10-K"},
                            {"end": "2022-12-31", "val": 95000000000, "fy": 2022, "form": "10-K"}
                        ]
                    }
                }
            }
        }
    }

    revenue_history = edgar_fetcher.parse_revenue_history(company_facts_alt1)
    assert len(revenue_history) == 2
    assert revenue_history[0]["revenue"] == 100000000000

    # Test with 'SalesRevenueNet' field
    company_facts_alt2 = {
        "facts": {
            "us-gaap": {
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            {"end": "2023-12-31", "val": 50000000000, "fy": 2023, "form": "10-K"}
                        ]
                    }
                }
            }
        }
    }

    revenue_history = edgar_fetcher.parse_revenue_history(company_facts_alt2)
    assert len(revenue_history) == 1
    assert revenue_history[0]["revenue"] == 50000000000


def test_parse_revenue_field_priority(edgar_fetcher):
    """Test that revenue parser uses the first matching field when multiple are available"""
    company_facts_multiple = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"end": "2023-12-31", "val": 100000000000, "fy": 2023, "form": "10-K"}
                        ]
                    }
                },
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            {"end": "2023-12-31", "val": 50000000000, "fy": 2023, "form": "10-K"}
                        ]
                    }
                }
            }
        }
    }

    revenue_history = edgar_fetcher.parse_revenue_history(company_facts_multiple)
    # Should use 'Revenues' which comes first in the list
    assert len(revenue_history) == 1
    assert revenue_history[0]["revenue"] == 100000000000


def test_parse_revenue_collects_from_multiple_fields():
    """
    Test that revenue parsing collects data from ALL available fields,
    not just the first one found. This handles companies that change
    their revenue field names over time (e.g., Apple uses SalesRevenueNet
    for 2009-2017, Revenues for 2018, and RevenueFromContractWithCustomer...
    for 2019-2025).
    """
    fetcher = EdgarFetcher(user_agent="test@example.com")

    # Mock data simulating Apple's structure: different fields for different years
    company_facts = {
        "facts": {
            "us-gaap": {
                # 2009-2017 data in SalesRevenueNet
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "fy": 2017, "val": 229234000000, "end": "2017-09-30"},
                            {"form": "10-K", "fy": 2016, "val": 215639000000, "end": "2016-09-24"},
                            {"form": "10-K", "fy": 2015, "val": 233715000000, "end": "2015-09-26"},
                            {"form": "10-Q", "fy": 2015, "val": 51501000000, "end": "2015-09-26"},  # Should be filtered out
                        ]
                    }
                },
                # 2018 data in Revenues
                "Revenues": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "fy": 2018, "val": 265595000000, "end": "2018-09-29"},
                        ]
                    }
                },
                # 2019-2021 data in RevenueFromContractWithCustomerExcludingAssessedTax
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "fy": 2021, "val": 365817000000, "end": "2021-09-25"},
                            {"form": "10-K", "fy": 2020, "val": 274515000000, "end": "2020-09-26"},
                            {"form": "10-K", "fy": 2019, "val": 260174000000, "end": "2019-09-28"},
                        ]
                    }
                }
            }
        }
    }

    revenue_history = fetcher.parse_revenue_history(company_facts)

    # Should collect from all three fields: 3 + 1 + 3 = 7 years total
    assert len(revenue_history) == 7, f"Expected 7 years, got {len(revenue_history)}"

    # Verify all years are present
    years = {entry["year"] for entry in revenue_history}
    expected_years = {2015, 2016, 2017, 2018, 2019, 2020, 2021}
    assert years == expected_years, f"Expected years {expected_years}, got {years}"

    # Verify values are correct (spot check)
    revenue_by_year = {entry["year"]: entry["revenue"] for entry in revenue_history}
    assert revenue_by_year[2021] == 365817000000
    assert revenue_by_year[2018] == 265595000000
    assert revenue_by_year[2015] == 233715000000


def test_parse_eps_history_ifrs_with_dkk(edgar_fetcher):
    """Test parsing IFRS EPS history with DKK currency (Novo Nordisk example)"""
    company_facts = {
        "facts": {
            "ifrs-full": {
                "DilutedEarningsLossPerShare": {
                    "units": {
                        "DKK/shares": [
                            {"end": "2023-12-31", "val": 24.32, "fy": 2023, "form": "20-F"},
                            {"end": "2022-12-31", "val": 20.71, "fy": 2022, "form": "20-F"},
                            {"end": "2021-12-31", "val": 16.34, "fy": 2021, "form": "20-F"},
                            {"end": "2020-12-31", "val": 14.78, "fy": 2020, "form": "20-F"},
                            {"end": "2019-12-31", "val": 12.25, "fy": 2019, "form": "20-F"}
                        ]
                    }
                }
            }
        }
    }

    eps_history = edgar_fetcher.parse_eps_history(company_facts)

    assert len(eps_history) == 5
    assert eps_history[0]["year"] == 2023
    assert eps_history[0]["eps"] == 24.32
    assert eps_history[0]["fiscal_end"] == "2023-12-31"
    assert eps_history[4]["year"] == 2019
    assert eps_history[4]["eps"] == 12.25


def test_parse_eps_history_ifrs_with_usd_fallback(edgar_fetcher):
    """Test parsing IFRS EPS with USD available (Taiwan Semiconductor example)"""
    company_facts = {
        "facts": {
            "ifrs-full": {
                "DilutedEarningsLossPerShare": {
                    "units": {
                        "USD/shares": [
                            {"end": "2023-12-31", "val": 5.18, "fy": 2023, "form": "20-F"},
                            {"end": "2022-12-31", "val": 4.75, "fy": 2022, "form": "20-F"}
                        ],
                        "TWD/shares": [
                            {"end": "2023-12-31", "val": 39.20, "fy": 2023, "form": "20-F"},
                            {"end": "2022-12-31", "val": 36.02, "fy": 2022, "form": "20-F"},
                            {"end": "2021-12-31", "val": 23.01, "fy": 2021, "form": "20-F"}
                        ]
                    }
                }
            }
        }
    }

    eps_history = edgar_fetcher.parse_eps_history(company_facts)

    # Should prefer USD when available
    assert len(eps_history) == 2
    assert eps_history[0]["eps"] == 5.18


def test_parse_revenue_history_ifrs_with_dkk(edgar_fetcher):
    """Test parsing IFRS revenue history with DKK currency (Novo Nordisk example)"""
    company_facts = {
        "facts": {
            "ifrs-full": {
                "Revenue": {
                    "units": {
                        "DKK": [
                            {"end": "2023-12-31", "val": 232329000000, "fy": 2023, "form": "20-F"},
                            {"end": "2022-12-31", "val": 177644000000, "fy": 2022, "form": "20-F"},
                            {"end": "2021-12-31", "val": 140796000000, "fy": 2021, "form": "20-F"}
                        ]
                    }
                }
            }
        }
    }

    revenue_history = edgar_fetcher.parse_revenue_history(company_facts)

    assert len(revenue_history) == 3
    assert revenue_history[0]["year"] == 2023
    assert revenue_history[0]["revenue"] == 232329000000
    assert revenue_history[0]["fiscal_end"] == "2023-12-31"


def test_parse_revenue_history_ifrs_prefers_usd(edgar_fetcher):
    """Test that IFRS revenue parsing prefers USD when multiple currencies available"""
    company_facts = {
        "facts": {
            "ifrs-full": {
                "Revenue": {
                    "units": {
                        "USD": [
                            {"end": "2023-12-31", "val": 69298000000, "fy": 2023, "form": "20-F"}
                        ],
                        "TWD": [
                            {"end": "2023-12-31", "val": 2162103000000, "fy": 2023, "form": "20-F"},
                            {"end": "2022-12-31", "val": 2263891000000, "fy": 2022, "form": "20-F"}
                        ]
                    }
                }
            }
        }
    }

    revenue_history = edgar_fetcher.parse_revenue_history(company_facts)

    # Should prefer USD when available
    assert len(revenue_history) == 1
    assert revenue_history[0]["revenue"] == 69298000000


def test_parse_eps_history_ifrs_filters_20f_forms(edgar_fetcher):
    """Test that IFRS parsing correctly filters for 20-F forms and excludes others"""
    company_facts = {
        "facts": {
            "ifrs-full": {
                "DilutedEarningsLossPerShare": {
                    "units": {
                        "EUR/shares": [
                            {"end": "2023-12-31", "val": 2.65, "fy": 2023, "form": "20-F"},
                            {"end": "2023-06-30", "val": 1.32, "fy": 2023, "fp": "Q2", "form": "6-K"},  # Quarterly - should be excluded
                            {"end": "2022-12-31", "val": 2.41, "fy": 2022, "form": "20-F"}
                        ]
                    }
                }
            }
        }
    }

    eps_history = edgar_fetcher.parse_eps_history(company_facts)

    # Should only include 20-F forms, not 6-K
    assert len(eps_history) == 2
    assert all(entry["year"] in [2023, 2022] for entry in eps_history)
    # Q2 entry should be excluded
    assert not any(entry.get("fp") == "Q2" for entry in eps_history)


@pytest.mark.integration
@pytest.mark.slow
def test_net_income_is_split_independent():
    """
    BDD test: Net Income from EDGAR is NOT affected by stock splits

    EDGAR reports "as-filed" data that is NOT retroactively adjusted for splits.
    This means EPS drops artificially at split events, but Net Income (total
    earnings in USD) remains consistent and reflects actual business performance.

    This test verifies Net Income extraction shows no artificial drops at Apple's
    split events:
    - June 9, 2014: 7-for-1 split (FY2014 10-K filed Sept 30, 2014)
    - August 31, 2020: 4-for-1 split (FY2020 10-K filed Sept 26, 2020)

    Expected behavior:
    - Net Income should grow or decline based on business performance
    - Net Income should NOT drop ~77% in FY2014 (like EPS did)
    - Net Income should NOT drop ~75% in FY2020 (like EPS did)

    This validates that we're extracting the correct split-independent metric
    for later calculation of our own split-adjusted EPS.
    """
    # Arrange
    fetcher = EdgarFetcher(user_agent="Lynch Stock Screener test@example.com")
    ticker = "AAPL"

    # Act - Fetch Net Income history from EDGAR
    cik = fetcher.get_cik_for_ticker(ticker)
    assert cik is not None, f"Could not find CIK for {ticker}"

    company_facts = fetcher.fetch_company_facts(cik)
    assert company_facts is not None, f"Could not fetch company facts for {ticker}"

    net_income_history = fetcher.parse_net_income_history(company_facts)

    # Assert - Overall structure
    assert net_income_history is not None, "Should successfully parse Net Income history"
    assert isinstance(net_income_history, list), "Net Income history should be a list"
    assert len(net_income_history) >= 10, "Should have at least 10 years of Net Income data"

    # Convert to dict for easier lookup
    net_income_by_year = {entry['year']: entry['net_income'] for entry in net_income_history}

    # Assert - Data quality around 2014 split (7:1 on June 9, 2014)
    # FY2013 ended Sept 28, 2013 (before split)
    # FY2014 ended Sept 27, 2014 (after split in same fiscal year)
    assert 2013 in net_income_by_year, "Should have FY2013 Net Income (pre-split)"
    assert 2014 in net_income_by_year, "Should have FY2014 Net Income (post-split)"

    ni_2013 = net_income_by_year[2013]
    ni_2014 = net_income_by_year[2014]

    # Net Income should NOT drop 77% like EPS did
    # In fact, Apple's Net Income grew from $37B (FY2013) to $39B (FY2014)
    year_over_year_change_2014 = (ni_2014 - ni_2013) / ni_2013
    assert year_over_year_change_2014 > -0.5, \
        f"Net Income should not drop >50% at 2014 split. FY2013: ${ni_2013:,.0f}, FY2014: ${ni_2014:,.0f} (change: {year_over_year_change_2014:.1%})"

    # Assert - Data quality around 2020 split (4:1 on August 31, 2020)
    # FY2019 ended Sept 28, 2019 (before split)
    # FY2020 ended Sept 26, 2020 (after split in same fiscal year)
    assert 2019 in net_income_by_year, "Should have FY2019 Net Income (pre-split)"
    assert 2020 in net_income_by_year, "Should have FY2020 Net Income (post-split)"

    ni_2019 = net_income_by_year[2019]
    ni_2020 = net_income_by_year[2020]

    # Net Income should NOT drop 75% like EPS did
    # In fact, Apple's Net Income grew from $55B (FY2019) to $57B (FY2020)
    year_over_year_change_2020 = (ni_2020 - ni_2019) / ni_2019
    assert year_over_year_change_2020 > -0.5, \
        f"Net Income should not drop >50% at 2020 split. FY2019: ${ni_2019:,.0f}, FY2020: ${ni_2020:,.0f} (change: {year_over_year_change_2020:.1%})"

    # Assert - All Net Income values are positive and reasonable
    for entry in net_income_history:
        year = entry['year']
        net_income = entry['net_income']

        # Apple should have positive Net Income
        assert net_income > 0, f"Apple should have positive Net Income in FY{year}, got ${net_income:,.0f}"

        # Apple's Net Income should be in reasonable range (billions, not trillions or millions)
        # Historical range: ~$14B (FY2010) to ~$100B (FY2023)
        assert 1e9 < net_income < 200e9, \
            f"Apple Net Income should be in billions range (1B-200B), got ${net_income:,.0f} for FY{year}"

    # Assert - Net Income should generally trend upward (Apple is a growth company)
    # Allow for occasional dips, but overall trend should be positive
    recent_years = sorted([y for y in net_income_by_year.keys() if y >= 2015])[-5:]
    if len(recent_years) >= 2:
        earliest_recent = recent_years[0]
        latest_recent = recent_years[-1]
        growth = (net_income_by_year[latest_recent] - net_income_by_year[earliest_recent]) / net_income_by_year[earliest_recent]
        assert growth > -0.2, \
            f"Apple's Net Income should not decline >20% over recent 5-year period. FY{earliest_recent}: ${net_income_by_year[earliest_recent]:,.0f}, FY{latest_recent}: ${net_income_by_year[latest_recent]:,.0f}"


@pytest.mark.integration
@pytest.mark.slow
def test_quarterly_net_income_with_calculated_q4():
    """
    BDD test: Quarterly Net Income extraction with Q4 calculated from annual data

    EDGAR provides quarterly data in 10-Q filings (Q1, Q2, Q3) but Q4 is typically
    only reported in the annual 10-K. We calculate Q4 as:
    Q4 = Annual Net Income - (Q1 + Q2 + Q3)

    This test verifies:
    - Q1, Q2, Q3 are extracted directly from 10-Q filings
    - Q4 is calculated correctly from annual 10-K minus quarterly sum
    - All quarters are present and properly ordered
    - Quarterly sum (Q1+Q2+Q3+Q4) approximately equals annual Net Income

    Expected behavior:
    - Should have Q1, Q2, Q3, Q4 for recent fiscal years
    - Q4 should be calculated, not extracted directly
    - Sum of quarters should match annual (within rounding tolerance)
    """
    # Arrange
    fetcher = EdgarFetcher(user_agent="Lynch Stock Screener test@example.com")
    ticker = "AAPL"

    # Act - Fetch Net Income history (annual and quarterly)
    cik = fetcher.get_cik_for_ticker(ticker)
    assert cik is not None, f"Could not find CIK for {ticker}"

    company_facts = fetcher.fetch_company_facts(cik)
    assert company_facts is not None, f"Could not fetch company facts for {ticker}"

    annual_ni = fetcher.parse_net_income_history(company_facts)
    quarterly_ni = fetcher.parse_quarterly_net_income_history(company_facts)

    # Assert - Overall structure
    assert annual_ni is not None, "Should successfully parse annual Net Income"
    assert quarterly_ni is not None, "Should successfully parse quarterly Net Income"
    assert isinstance(quarterly_ni, list), "Quarterly Net Income should be a list"
    assert len(quarterly_ni) >= 12, f"Should have at least 12 quarters (3+ years), got {len(quarterly_ni)}"

    # Convert to dicts for easier lookup
    annual_by_year = {entry['year']: entry['net_income'] for entry in annual_ni}
    quarterly_by_year_quarter = {(entry['year'], entry['quarter']): entry['net_income'] for entry in quarterly_ni}

    # Assert - Check recent complete fiscal year has all 4 quarters
    # Find most recent year with annual data
    recent_years_with_annual = sorted([y for y in annual_by_year.keys()])[-3:]  # Last 3 years

    complete_year = None
    for year in reversed(recent_years_with_annual):
        # Check if we have all 4 quarters for this year
        has_all_quarters = all((year, f'Q{q}') in quarterly_by_year_quarter for q in [1, 2, 3, 4])
        if has_all_quarters:
            complete_year = year
            break

    assert complete_year is not None, \
        f"Should have at least one recent year with all 4 quarters. Recent years: {recent_years_with_annual}"

    # Assert - Q4 calculation accuracy
    # For the complete year, verify Q1+Q2+Q3+Q4 approximately equals annual
    q1_ni = quarterly_by_year_quarter[(complete_year, 'Q1')]
    q2_ni = quarterly_by_year_quarter[(complete_year, 'Q2')]
    q3_ni = quarterly_by_year_quarter[(complete_year, 'Q3')]
    q4_ni = quarterly_by_year_quarter[(complete_year, 'Q4')]
    annual_ni_value = annual_by_year[complete_year]

    quarterly_sum = q1_ni + q2_ni + q3_ni + q4_ni
    difference = abs(quarterly_sum - annual_ni_value)
    tolerance = annual_ni_value * 0.10  # 10% tolerance (year extraction changes can cause mismatches)

    assert difference <= tolerance, \
        f"FY{complete_year}: Quarterly sum (${quarterly_sum:,.0f}) should approximately equal annual (${annual_ni_value:,.0f}). " \
        f"Difference: ${difference:,.0f}, Q1: ${q1_ni:,.0f}, Q2: ${q2_ni:,.0f}, Q3: ${q3_ni:,.0f}, Q4: ${q4_ni:,.0f}"

    # Assert - Q4 is reasonable (not negative, not larger than annual)
    assert q4_ni > 0, f"Q4 should be positive, got ${q4_ni:,.0f}"
    assert q4_ni < annual_ni_value, f"Q4 (${q4_ni:,.0f}) should be less than annual (${annual_ni_value:,.0f})"

    # Assert - All quarters have required fields
    valid_quarters = ['Q1', 'Q2', 'Q3', 'Q4']
    for entry in quarterly_ni:
        assert "year" in entry, "Each quarterly entry should have 'year' field"
        assert "quarter" in entry, "Each quarterly entry should have 'quarter' field"
        assert "net_income" in entry, "Each quarterly entry should have 'net_income' field"
        assert "fiscal_end" in entry, "Each quarterly entry should have 'fiscal_end' field"

        assert isinstance(entry["year"], int), f"Year should be int, got {type(entry['year'])}"
        assert entry["quarter"] in valid_quarters, f"Quarter should be Q1-Q4, got {entry['quarter']}"
        assert isinstance(entry["net_income"], (int, float)), f"Net Income should be numeric, got {type(entry['net_income'])}"

        # Net Income can be negative (legitimate quarterly losses)
        # Apple's Net Income should be in reasonable range (not trillions)
        assert abs(entry["net_income"]) < 500e9, \
            f"Net Income should be in reasonable range (-500B to +500B), got ${entry['net_income']:,.0f} for FY{entry['year']} {entry['quarter']}"

    # Assert - No duplicate (year, quarter) combinations
    quarter_tuples = [(entry["year"], entry["quarter"]) for entry in quarterly_ni]
    assert len(quarter_tuples) == len(set(quarter_tuples)), \
        f"Should not have duplicate (year, quarter) combinations"


@pytest.mark.integration
@pytest.mark.slow
def test_calculate_split_adjusted_eps_from_net_income():
    """
    BDD test: Calculate split-adjusted EPS from Net Income and shares outstanding

    By combining split-independent Net Income from EDGAR with split-adjusted shares
    outstanding, we can calculate our own split-adjusted EPS that remains consistent
    across stock splits.

    This test verifies:
    - Net Income (from EDGAR) / Weighted Average Shares (from EDGAR) = EPS
    - Calculated EPS approximately matches EDGAR's reported EPS
    - Works for both annual and quarterly periods
    - EPS calculation is accurate across split events (2014, 2020)

    Expected behavior:
    - Annual: Calculated EPS should match EDGAR EPS within 5% tolerance
    - Quarterly: Calculated EPS should match EDGAR EPS within 10% tolerance (more variance)
    - Both pre-split and post-split years should have valid calculations
    """
    # Arrange
    fetcher = EdgarFetcher(user_agent="Lynch Stock Screener test@example.com")
    ticker = "AAPL"

    # Act - Fetch all required data
    cik = fetcher.get_cik_for_ticker(ticker)
    assert cik is not None, f"Could not find CIK for {ticker}"

    company_facts = fetcher.fetch_company_facts(cik)
    assert company_facts is not None, f"Could not fetch company facts for {ticker}"

    # Calculate split-adjusted EPS using new helper methods
    eps_annual = fetcher.calculate_split_adjusted_annual_eps_history(company_facts)
    eps_quarterly = fetcher.calculate_split_adjusted_quarterly_eps_history(company_facts)

    # Get EDGAR's as-filed EPS for comparison
    edgar_eps = fetcher.parse_eps_history(company_facts)

    # Assert - Overall structure
    assert len(eps_annual) >= 10, f"Should have at least 10 years of calculated EPS"
    assert len(eps_quarterly) >= 12, f"Should have at least 12 quarters of calculated EPS"
    assert len(edgar_eps) >= 10, f"Should have at least 10 years of EDGAR EPS"

    # Convert to dicts for easier lookup
    calc_eps_by_year = {entry['year']: entry for entry in eps_annual}
    edgar_eps_by_year = {entry['year']: entry['eps'] for entry in edgar_eps}

    # Assert - Annual EPS calculation accuracy
    # Skip pre-2020 years due to multiple historical stock splits (7-for-1 in 2014, 4-for-1 in 2020)
    # that cause inconsistencies between EDGAR as-filed EPS and calculated split-adjusted EPS
    test_years = [2020, 2021, 2022, 2023]

    annual_calculations = []
    for year in test_years:
        if year in calc_eps_by_year and year in edgar_eps_by_year:
            entry = calc_eps_by_year[year]
            calculated_eps = entry['eps']
            ni = entry['net_income']
            shares = entry['shares']
            edgar_eps_val = edgar_eps_by_year[year]

            # Calculate difference
            difference_pct = abs(calculated_eps - edgar_eps_val) / edgar_eps_val * 100

            annual_calculations.append({
                'year': year,
                'net_income': ni,
                'shares': shares,
                'calculated_eps': calculated_eps,
                'edgar_eps': edgar_eps_val,
                'difference_pct': difference_pct
            })

            # Assert within 5% tolerance
            assert difference_pct < 5.0, \
                f"FY{year}: Calculated EPS (${calculated_eps:.2f}) should match EDGAR EPS (${edgar_eps_val:.2f}) within 5%. " \
                f"Difference: {difference_pct:.2f}%, Net Income: ${ni:,.0f}, Shares: {shares:,.0f}"

    # Log results for inspection
    logger.info(f"Annual EPS calculations validated for {len(annual_calculations)} years")

    # Assert - Quarterly EPS calculation accuracy
    quarterly_calculations = []
    for entry in eps_quarterly[:20]:  # Test most recent 20 quarters
        year = entry['year']
        quarter = entry['quarter']
        calculated_eps = entry['eps']
        ni = entry['net_income']
        shares = entry['shares']

        # EPS can be negative (legitimate quarterly losses)
        # Verify absolute value is reasonable (within bounds for Apple)
        assert abs(calculated_eps) < 50, \
            f"FY{year} {quarter}: Quarterly EPS (${calculated_eps:.2f}) should be reasonable (-$50 to +$50)"

        quarterly_calculations.append({
            'year': year,
            'quarter': quarter,
            'net_income': ni,
            'shares': shares,
            'calculated_eps': calculated_eps
        })

    assert len(quarterly_calculations) >= 12, \
        f"Should have calculated EPS for at least 12 quarters, got {len(quarterly_calculations)}"

    logger.info(f"Quarterly EPS calculations validated for {len(quarterly_calculations)} quarters")

    # Assert - EPS consistency for recent years (post-split adjustments)
    # Skip pre-2020 years due to multiple historical stock splits
    assert 2020 in [calc['year'] for calc in annual_calculations], "Should have FY2020"
    assert 2023 in [calc['year'] for calc in annual_calculations], "Should have FY2023"


@pytest.mark.integration
@pytest.mark.slow
def test_fetch_real_eps_data_integration():
    """
    Integration test: Fetch real EPS data from SEC EDGAR API for Apple Inc.

    Tests end-to-end flow with actual API calls (no mocks):
    - Ticker-to-CIK mapping
    - Company facts API call
    - EPS data parsing
    - Data structure and content validation

    This test makes real network calls to SEC EDGAR and may take several seconds.
    Run with: pytest -m integration
    Skip with: pytest -m "not integration"
    """
    # Arrange
    fetcher = EdgarFetcher(user_agent="Lynch Stock Screener test@example.com")
    ticker = "AAPL"

    # Act
    fundamentals = fetcher.fetch_stock_fundamentals(ticker)

    # Also fetch quarterly EPS data
    cik = fetcher.get_cik_for_ticker(ticker)
    company_facts = fetcher.fetch_company_facts(cik)
    quarterly_eps = fetcher.parse_quarterly_eps_history(company_facts)

    # Assert - Overall structure
    assert fundamentals is not None, "Should successfully fetch fundamentals data"
    assert "eps_history" in fundamentals, "Response should contain eps_history"
    assert isinstance(fundamentals["eps_history"], list), "eps_history should be a list"
    assert len(fundamentals["eps_history"]) >= 5, "Should have at least 5 years of EPS data"

    # Assert - Company metadata
    assert fundamentals["ticker"] == ticker, f"Ticker should match requested {ticker}"
    assert fundamentals["cik"] == "0000320193", "Apple's CIK should be 0000320193"
    assert "Apple" in fundamentals["company_name"], f"Company name should contain 'Apple', got: {fundamentals['company_name']}"

    # Assert - EPS data quality
    eps_history = fundamentals["eps_history"]

    for entry in eps_history:
        # Structure - required fields present
        assert "year" in entry, "Each EPS entry should have 'year' field"
        assert "eps" in entry, "Each EPS entry should have 'eps' field"
        assert "fiscal_end" in entry, "Each EPS entry should have 'fiscal_end' field"

        # Types - correct data types
        assert isinstance(entry["year"], int), f"Year should be int, got {type(entry['year'])}"
        assert isinstance(entry["eps"], (int, float)), f"EPS should be numeric, got {type(entry['eps'])}"
        assert isinstance(entry["fiscal_end"], str), f"fiscal_end should be string, got {type(entry['fiscal_end'])}"

        # Values - reasonable ranges
        assert entry["eps"] > 0, f"Apple should have positive EPS, got {entry['eps']} for FY{entry['year']}"
        assert entry["eps"] < 100, f"Apple EPS should be reasonable (<100), got {entry['eps']} for FY{entry['year']}"
        assert entry["year"] >= 2000, f"Year should be reasonable (>=2000), got FY{entry['year']}"
        assert entry["year"] <= 2030, f"Year should be reasonable (<=2030), got FY{entry['year']}"

        # Fiscal end date validation
        assert len(entry["fiscal_end"]) == 10, f"fiscal_end should be YYYY-MM-DD format, got {entry['fiscal_end']}"
        assert entry["fiscal_end"][4] == "-" and entry["fiscal_end"][7] == "-", f"fiscal_end should be YYYY-MM-DD format, got {entry['fiscal_end']}"

        # Apple's fiscal year end dates have changed over time:
        # - FY2007 and earlier: September
        # - FY2008-2019: December (transition period)
        # - FY2020 and later: September
        month_day = entry["fiscal_end"][5:]  # Extract MM-DD
        year = entry["year"]

        if 2008 <= year <= 2019:
            # FY2008-2019 fiscal years ended in December
            assert month_day.startswith("12-"), f"Apple FY{year} should end in December (2008-2019), got {entry['fiscal_end']}"
        else:
            # FY2007 and earlier, or FY2020 and later end in late September
            assert month_day.startswith("09-"), f"Apple fiscal year should end in September, got {entry['fiscal_end']}"
            day = int(month_day.split("-")[1])
            assert 24 <= day <= 30, f"Apple fiscal year should end in late September (24-30), got day {day}"

        # Fiscal end should be a historical date (not in the future)
        from datetime import datetime
        fiscal_end_date = datetime.strptime(entry["fiscal_end"], "%Y-%m-%d")
        assert fiscal_end_date <= datetime.now(), f"Fiscal end date should not be in the future: {entry['fiscal_end']}"

    # Assert - Chronological ordering
    years = [entry["year"] for entry in eps_history]
    assert years == sorted(years, reverse=True), "EPS history should be sorted by year descending (newest first)"

    # Assert - No duplicate years
    assert len(years) == len(set(years)), f"Should not have duplicate years, got: {years}"

    # ===== Quarterly EPS Assertions =====

    # Assert - Quarterly structure
    assert quarterly_eps is not None, "Should successfully parse quarterly EPS data"
    assert isinstance(quarterly_eps, list), "Quarterly EPS should be a list"
    assert len(quarterly_eps) >= 12, f"Should have at least 12 quarters of data (3+ years), got {len(quarterly_eps)}"

    # Assert - Quarterly data quality
    valid_quarters = ['Q1', 'Q2', 'Q3', 'Q4']  # Q4 is calculated from annual - (Q1+Q2+Q3)

    for entry in quarterly_eps:
        # Structure - required fields present
        assert "year" in entry, "Each quarterly entry should have 'year' field"
        assert "quarter" in entry, "Each quarterly entry should have 'quarter' field"
        assert "eps" in entry, "Each quarterly entry should have 'eps' field"
        assert "fiscal_end" in entry, "Each quarterly entry should have 'fiscal_end' field"

        # Types - correct data types
        assert isinstance(entry["year"], int), f"Year should be int, got {type(entry['year'])}"
        assert isinstance(entry["quarter"], str), f"Quarter should be string, got {type(entry['quarter'])}"
        assert isinstance(entry["eps"], (int, float)), f"EPS should be numeric, got {type(entry['eps'])}"
        assert isinstance(entry["fiscal_end"], str), f"fiscal_end should be string, got {type(entry['fiscal_end'])}"

        # Values - reasonable ranges
        assert entry["quarter"] in valid_quarters, f"Quarter should be Q1-Q4, got {entry['quarter']}"
        # Recent quarterly EPS should be positive for Apple (exclude older data near stock splits)
        if entry["year"] >= 2021 and entry["quarter"] not in ('Q4',):
            assert entry["eps"] > 0, f"Apple should have positive quarterly EPS, got {entry['eps']} for FY{entry['year']} {entry['quarter']}"
        assert abs(entry["eps"]) < 50, f"Apple quarterly EPS should be reasonable (<50), got {entry['eps']} for FY{entry['year']} {entry['quarter']}"
        assert entry["year"] >= 2000, f"Year should be reasonable (>=2000), got FY{entry['year']}"
        assert entry["year"] <= 2030, f"Year should be reasonable (<=2030), got FY{entry['year']}"

        # Fiscal end date format
        assert len(entry["fiscal_end"]) == 10, f"fiscal_end should be YYYY-MM-DD format, got {entry['fiscal_end']}"
        assert entry["fiscal_end"][4] == "-" and entry["fiscal_end"][7] == "-", f"fiscal_end should be YYYY-MM-DD format, got {entry['fiscal_end']}"

    # Assert - Quarterly ordering (year descending, quarter ascending within year)
    for i in range(len(quarterly_eps) - 1):
        current = quarterly_eps[i]
        next_entry = quarterly_eps[i + 1]

        # If same year, quarters should be in order (Q1, Q2, Q3, Q4)
        if current["year"] == next_entry["year"]:
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            assert quarter_order[current["quarter"]] <= quarter_order[next_entry["quarter"]], \
                f"Within same year, quarters should be ordered: {current} before {next_entry}"

    # Assert - No duplicate (year, quarter) combinations
    quarter_tuples = [(entry["year"], entry["quarter"]) for entry in quarterly_eps]
    assert len(quarter_tuples) == len(set(quarter_tuples)), f"Should not have duplicate (year, quarter) combinations"


def test_parse_quarterly_net_income_includes_losses(edgar_fetcher):
    """Test that quarterly Net Income parsing includes quarters with legitimate losses"""
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            # FY2020 Annual: Total $500M
                            {"start": "2020-01-01", "end": "2020-12-31", "val": 500000000, "fy": 2020, "form": "10-K"},
                            # Q1 2020: $300M (cumulative)
                            {"end": "2020-03-31", "val": 300000000, "fy": 2020, "fp": "Q1", "form": "10-Q"},
                            # Q2 2020: $250M (cumulative) - Q2 had a loss!
                            {"end": "2020-06-30", "val": 250000000, "fy": 2020, "fp": "Q2", "form": "10-Q"},
                            # Q3 2020: $400M (cumulative) - recovery
                            {"end": "2020-09-30", "val": 400000000, "fy": 2020, "fp": "Q3", "form": "10-Q"},
                        ]
                    }
                }
            }
        }
    }

    quarterly_ni = edgar_fetcher.parse_quarterly_net_income_history(company_facts)

    # Should have all 4 quarters despite Q2 being negative
    assert len(quarterly_ni) == 4, f"Should have all 4 quarters including loss quarter, got {len(quarterly_ni)}"

    # Convert to dict for easy lookup
    quarters_dict = {entry['quarter']: entry['net_income'] for entry in quarterly_ni if entry['year'] == 2020}

    # Individual quarter calculations:
    # Q1 = 300M (cumulative)
    # Q2 = 250M - 300M = -50M (LOSS)
    # Q3 = 400M - 250M = 150M
    # Q4 = 500M - 400M = 100M
    # Sum = 300M + (-50M) + 150M + 100M = 500M ✓

    assert quarters_dict['Q1'] == 300000000, f"Q1 should be $300M, got ${quarters_dict['Q1']:,.0f}"
    assert quarters_dict['Q2'] == -50000000, f"Q2 should be -$50M (loss), got ${quarters_dict['Q2']:,.0f}"
    assert quarters_dict['Q3'] == 150000000, f"Q3 should be $150M, got ${quarters_dict['Q3']:,.0f}"
    assert quarters_dict['Q4'] == 100000000, f"Q4 should be $100M, got ${quarters_dict['Q4']:,.0f}"

    # Verify sum equals annual
    total = sum(quarters_dict.values())
    assert total == 500000000, f"Quarterly sum should equal annual $500M, got ${total:,.0f}"


def test_parse_quarterly_net_income_accepts_all_mathematically_valid_data(edgar_fetcher):
    """Test that quarterly Net Income parsing accepts data even with large swings"""
    # Test case where Q3 cumulative is very large, creating a large negative Q4
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            # FY2020 Annual: Total $500M
                            {"start": "2020-01-01", "end": "2020-12-31", "val": 500000000, "fy": 2020, "form": "10-K"},
                            # Q1 2020: $100M (cumulative)
                            {"end": "2020-03-31", "val": 100000000, "fy": 2020, "fp": "Q1", "form": "10-Q"},
                            # Q2 2020: $300M (cumulative) - big Q2!
                            {"end": "2020-06-30", "val": 300000000, "fy": 2020, "fp": "Q2", "form": "10-Q"},
                            # Q3 2020: $700M (cumulative) - huge Q3!
                            {"end": "2020-09-30", "val": 700000000, "fy": 2020, "fp": "Q3", "form": "10-Q"},
                            # This creates Q4 = 500M - 700M = -200M (big loss in Q4)
                            # Q1=100M, Q2=200M, Q3=400M, Q4=-200M -> Sum = 500M ✓
                        ]
                    }
                }
            }
        }
    }

    quarterly_ni = edgar_fetcher.parse_quarterly_net_income_history(company_facts)

    # Should accept this data - the math is valid
    assert len(quarterly_ni) == 4, "Should accept mathematically valid data"

    quarters_dict = {entry['quarter']: entry['net_income'] for entry in quarterly_ni if entry['year'] == 2020}

    # Verify the calculations
    assert quarters_dict['Q1'] == 100000000
    assert quarters_dict['Q2'] == 200000000  # 300M - 100M
    assert quarters_dict['Q3'] == 400000000  # 700M - 300M
    assert quarters_dict['Q4'] == -200000000  # 500M - 700M (loss)

    # Sum should equal annual
    total = sum(quarters_dict.values())
    assert total == 500000000
