# ABOUTME: Tests for SEC EDGAR data fetcher with ticker-to-CIK mapping
# ABOUTME: Validates XBRL data parsing, rate limiting, and API integration

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from edgar_fetcher import EdgarFetcher


@pytest.fixture
def edgar_fetcher():
    return EdgarFetcher(user_agent="Lynch Stock Screener test@example.com")


def test_ticker_to_cik_mapping(edgar_fetcher):
    """Test that ticker symbols can be mapped to CIK numbers"""
    with patch('edgar_fetcher.requests.get') as mock_get:
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
    with patch('edgar_fetcher.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
        }
        mock_get.return_value = mock_response

        cik = edgar_fetcher.get_cik_for_ticker("INVALID")

        assert cik is None


def test_fetch_company_facts(edgar_fetcher):
    """Test fetching company facts from SEC EDGAR API"""
    with patch('edgar_fetcher.requests.get') as mock_get:
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
                "LiabilitiesAndStockholdersEquity": {
                    "units": {
                        "USD": [
                            {"end": "2023-09-30", "val": 352755000000, "fy": 2023, "form": "10-K"}
                        ]
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {"end": "2023-09-30", "val": 62146000000, "fy": 2023, "form": "10-K"}
                        ]
                    }
                },
                "Liabilities": {
                    "units": {
                        "USD": [
                            {"end": "2023-09-30", "val": 290437000000, "fy": 2023, "form": "10-K"}
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

    with patch('edgar_fetcher.requests.get') as mock_get:
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
    with patch('edgar_fetcher.requests.get') as mock_get:
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
    with patch('edgar_fetcher.requests.get') as mock_get:
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
