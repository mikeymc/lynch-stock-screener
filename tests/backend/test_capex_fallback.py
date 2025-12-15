# ABOUTME: Tests for the derived CapEx fallback functionality
# ABOUTME: Validates that missing CapEx data is correctly calculated from Net PPE and Depreciation

import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

from edgar_fetcher import EdgarFetcher


@pytest.fixture
def edgar_fetcher():
    return EdgarFetcher(user_agent="test@example.com")


def test_capex_fallback_when_direct_tag_missing(edgar_fetcher):
    """
    Test that CapEx is derived from ΔNetPPE + Depreciation when direct tags are missing.
    
    This replicates the NVDA 2013-2021 scenario where standard CapEx tags were not used.
    """
    company_facts = {
        "facts": {
            "us-gaap": {
                # No PaymentsToAcquirePropertyPlantAndEquipment
                # No PaymentsToAcquireProductiveAssets
                
                # Operating Cash Flow (for context)
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 500_000_000, "fy": 2020, "form": "10-K"},
                            {"end": "2019-12-31", "val": 400_000_000, "fy": 2019, "form": "10-K"},
                        ]
                    }
                },
                
                # Net PPE (Balance Sheet)
                "PropertyPlantAndEquipmentNet": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 1_000_000_000, "fy": 2020, "form": "10-K"},  # End: $1B
                            {"end": "2019-12-31", "val": 800_000_000, "fy": 2019, "form": "10-K"},   # End: $800M (Start for 2020)
                            {"end": "2018-12-31", "val": 600_000_000, "fy": 2018, "form": "10-K"},   # Start for 2019
                        ]
                    }
                },
                
                # Depreciation
                "Depreciation": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 150_000_000, "fy": 2020, "form": "10-K"},  # $150M
                            {"end": "2019-12-31", "val": 120_000_000, "fy": 2019, "form": "10-K"},  # $120M
                        ]
                    }
                }
            }
        }
    }
    
    cash_flow = edgar_fetcher.parse_cash_flow_history(company_facts)
    
    # Should have data for 2019 and 2020
    assert len(cash_flow) >= 2, f"Expected at least 2 years of data, got {len(cash_flow)}"
    
    cf_by_year = {entry['year']: entry for entry in cash_flow}
    
    # 2020: CapEx = (1B - 800M) + 150M = 350M
    assert 2020 in cf_by_year, "Should have 2020 data"
    assert cf_by_year[2020]['capital_expenditures'] == 350_000_000, \
        f"2020 CapEx should be $350M (derived), got ${cf_by_year[2020]['capital_expenditures']:,.0f}"
    
    # FCF = OCF - CapEx = 500M - 350M = 150M
    assert cf_by_year[2020]['free_cash_flow'] == 150_000_000, \
        f"2020 FCF should be $150M, got ${cf_by_year[2020]['free_cash_flow']:,.0f}"
    
    # 2019: CapEx = (800M - 600M) + 120M = 320M
    assert 2019 in cf_by_year, "Should have 2019 data"
    assert cf_by_year[2019]['capital_expenditures'] == 320_000_000, \
        f"2019 CapEx should be $320M (derived), got ${cf_by_year[2019]['capital_expenditures']:,.0f}"


def test_capex_prefers_direct_tag_over_fallback(edgar_fetcher):
    """
    Test that direct CapEx tags are used when available (fallback is not triggered).
    """
    company_facts = {
        "facts": {
            "us-gaap": {
                # Direct CapEx tag IS present
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 250_000_000, "fy": 2020, "form": "10-K"},
                        ]
                    }
                },
                
                # OCF
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 500_000_000, "fy": 2020, "form": "10-K"},
                        ]
                    }
                },
                
                # PPE (would give different derived value)
                "PropertyPlantAndEquipmentNet": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 1_000_000_000, "fy": 2020, "form": "10-K"},
                            {"end": "2019-12-31", "val": 800_000_000, "fy": 2019, "form": "10-K"},
                        ]
                    }
                },
                
                "Depreciation": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 150_000_000, "fy": 2020, "form": "10-K"},
                        ]
                    }
                }
            }
        }
    }
    
    cash_flow = edgar_fetcher.parse_cash_flow_history(company_facts)
    cf_by_year = {entry['year']: entry for entry in cash_flow}
    
    # Should use direct tag value ($250M), not derived value ($350M)
    assert cf_by_year[2020]['capital_expenditures'] == 250_000_000, \
        f"Should use direct CapEx ($250M), not derived. Got ${cf_by_year[2020]['capital_expenditures']:,.0f}"


def test_capex_fallback_with_depreciation_and_amortization(edgar_fetcher):
    """
    Test that DepreciationAndAmortization is used as fallback when Depreciation is unavailable.
    """
    company_facts = {
        "facts": {
            "us-gaap": {
                # No direct CapEx tags
                
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 500_000_000, "fy": 2020, "form": "10-K"},
                        ]
                    }
                },
                
                "PropertyPlantAndEquipmentNet": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 1_000_000_000, "fy": 2020, "form": "10-K"},
                            {"end": "2019-12-31", "val": 800_000_000, "fy": 2019, "form": "10-K"},
                        ]
                    }
                },
                
                # No Depreciation tag, only DepreciationAndAmortization
                "DepreciationAndAmortization": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 200_000_000, "fy": 2020, "form": "10-K"},
                        ]
                    }
                }
            }
        }
    }
    
    cash_flow = edgar_fetcher.parse_cash_flow_history(company_facts)
    cf_by_year = {entry['year']: entry for entry in cash_flow}
    
    # CapEx = (1B - 800M) + 200M = 400M (using D&A instead of D)
    assert cf_by_year[2020]['capital_expenditures'] == 400_000_000, \
        f"Should use D&A for fallback. Expected $400M, got ${cf_by_year[2020]['capital_expenditures']:,.0f}"


def test_capex_fallback_rejects_large_negative_values(edgar_fetcher):
    """
    Test that large negative derived CapEx values are rejected (indicates divestitures, not CapEx).
    """
    company_facts = {
        "facts": {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 500_000_000, "fy": 2020, "form": "10-K"},
                        ]
                    }
                },
                
                # Net PPE decreased significantly (company divested assets)
                "PropertyPlantAndEquipmentNet": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 300_000_000, "fy": 2020, "form": "10-K"},   # End: $300M
                            {"end": "2019-12-31", "val": 800_000_000, "fy": 2019, "form": "10-K"},   # Start: $800M
                        ]
                    }
                },
                
                "Depreciation": {
                    "units": {
                        "USD": [
                            {"end": "2020-12-31", "val": 100_000_000, "fy": 2020, "form": "10-K"},
                        ]
                    }
                }
            }
        }
    }
    
    cash_flow = edgar_fetcher.parse_cash_flow_history(company_facts)
    cf_by_year = {entry['year']: entry for entry in cash_flow}
    
    # Derived CapEx = (300M - 800M) + 100M = -400M (large negative = divestiture)
    # This should be rejected (set to None)
    assert cf_by_year[2020]['capital_expenditures'] is None, \
        f"Large negative derived CapEx should be rejected, got ${cf_by_year[2020]['capital_expenditures']}"
    
    # FCF should also be None when CapEx is None
    assert cf_by_year[2020]['free_cash_flow'] is None, \
        "FCF should be None when CapEx is None"


@pytest.mark.integration
@pytest.mark.slow
def test_nvda_capex_gap_filled():
    """
    Integration test: Verify that NVDA's 2013-2021 CapEx gap is filled with derived values.
    """
    fetcher = EdgarFetcher(user_agent="Lynch Stock Screener test@example.com")
    
    cik = fetcher.get_cik_for_ticker("NVDA")
    assert cik is not None, "Should find CIK for NVDA"
    
    company_facts = fetcher.fetch_company_facts(cik)
    assert company_facts is not None, "Should fetch company facts for NVDA"
    
    cash_flow = fetcher.parse_cash_flow_history(company_facts)
    cf_by_year = {entry['year']: entry for entry in cash_flow}
    
    # These years were previously missing, should now have derived values
    gap_years = [2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021]
    
    for year in gap_years:
        if year in cf_by_year:
            capex = cf_by_year[year]['capital_expenditures']
            fcf = cf_by_year[year]['free_cash_flow']
            
            assert capex is not None, f"NVDA {year} should have CapEx (derived), got None"
            assert capex > 0, f"NVDA {year} CapEx should be positive, got ${capex:,.0f}"
            assert fcf is not None, f"NVDA {year} should have FCF, got None"
