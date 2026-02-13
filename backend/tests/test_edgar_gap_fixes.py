# ABOUTME: Tests for EDGAR gap fixes - EPS fallback, equity/NI tag coverage, quarterly EPS extraction
# ABOUTME: Validates parsers handle non-standard XBRL tags and that quarterly period key discovery is revenue-independent

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from edgar_fetcher.equity_debt import EquityDebtMixin
from edgar_fetcher.eps import EPSMixin
from edgar_fetcher.income import IncomeMixin


def make_company_facts(namespace, tag, values):
    """Build a minimal company_facts dict for a single XBRL tag."""
    return {
        'facts': {
            namespace: {
                tag: {
                    'units': {
                        'USD': values
                    }
                }
            }
        }
    }


def make_annual_entry(year, val, form='10-K'):
    """Build a minimal annual EDGAR entry."""
    return {
        'form': form,
        'end': f'{year}-12-31',
        'val': val,
        'fy': year,
        'fp': 'FY'
    }


class ConcreteEquityMixin(EquityDebtMixin):
    """Concrete subclass for testing the mixin."""
    pass


class ConcreteEPSMixin(EPSMixin):
    """Concrete subclass for testing the mixin."""

    def parse_net_income_history(self, company_facts):
        # Minimal stub - real impl is in IncomeMixin
        ni_data = (
            company_facts.get('facts', {})
            .get('us-gaap', {})
            .get('NetIncomeLoss', {})
            .get('units', {})
            .get('USD', [])
        )
        result = []
        for entry in ni_data:
            if entry.get('form') == '10-K':
                fiscal_end = entry.get('end')
                year = int(fiscal_end[:4]) if fiscal_end else None
                if year and entry.get('val') is not None:
                    result.append({'year': year, 'net_income': entry['val'], 'fiscal_end': fiscal_end})
        return result

    def parse_shares_outstanding_history(self, company_facts):
        # Minimal stub - real impl is in SharesMixin
        shares_data = (
            company_facts.get('facts', {})
            .get('us-gaap', {})
            .get('WeightedAverageNumberOfDilutedSharesOutstanding', {})
            .get('units', {})
            .get('shares', [])
        )
        result = []
        for entry in shares_data:
            if entry.get('form') == '10-K':
                fiscal_end = entry.get('end')
                year = int(fiscal_end[:4]) if fiscal_end else None
                if year and entry.get('val') is not None:
                    result.append({'year': year, 'shares': entry['val'], 'fiscal_end': fiscal_end})
        return result


# ── Shareholder Equity Tag Coverage Tests ────────────────────────────────────

class TestShareholderEquityTagCoverage:

    def setup_method(self):
        self.mixin = ConcreteEquityMixin()

    def test_standard_tag_still_works(self):
        """StockholdersEquity is the primary tag and must still work."""
        facts = make_company_facts('us-gaap', 'StockholdersEquity', [
            make_annual_entry(2023, 5_000_000_000),
            make_annual_entry(2022, 4_500_000_000),
        ])
        result = self.mixin.parse_shareholder_equity_history(facts)
        assert len(result) == 2
        assert result[0]['year'] == 2023
        assert result[0]['shareholder_equity'] == 5_000_000_000

    def test_common_stockholders_equity_tag(self):
        """CommonStockholdersEquity is used by some companies (e.g. utilities)."""
        facts = make_company_facts('us-gaap', 'CommonStockholdersEquity', [
            make_annual_entry(2023, 3_200_000_000),
            make_annual_entry(2022, 2_900_000_000),
        ])
        result = self.mixin.parse_shareholder_equity_history(facts)
        assert len(result) == 2, f"Expected 2 results, got {len(result)}"
        assert result[0]['year'] == 2023
        assert result[0]['shareholder_equity'] == 3_200_000_000

    def test_members_equity_tag(self):
        """MembersEquity is used by LLC-structured companies."""
        facts = make_company_facts('us-gaap', 'MembersEquity', [
            make_annual_entry(2023, 1_800_000_000),
        ])
        result = self.mixin.parse_shareholder_equity_history(facts)
        assert len(result) == 1, f"Expected 1 result, got {len(result)}"
        assert result[0]['shareholder_equity'] == 1_800_000_000

    def test_bank_equity_tag(self):
        """CommonEquityTierOneCapital is used by banks/financial institutions."""
        facts = make_company_facts('us-gaap', 'CommonEquityTierOneCapital', [
            make_annual_entry(2023, 50_000_000_000),
            make_annual_entry(2022, 47_000_000_000),
        ])
        result = self.mixin.parse_shareholder_equity_history(facts)
        assert len(result) == 2, f"Expected 2 results, got {len(result)}"
        assert result[0]['shareholder_equity'] == 50_000_000_000

    def test_standard_tag_preferred_over_fallback(self):
        """StockholdersEquity should win over CommonStockholdersEquity for the same year."""
        facts = {
            'facts': {
                'us-gaap': {
                    'StockholdersEquity': {
                        'units': {'USD': [make_annual_entry(2023, 10_000_000_000)]}
                    },
                    'CommonStockholdersEquity': {
                        'units': {'USD': [make_annual_entry(2023, 9_000_000_000)]}
                    }
                }
            }
        }
        result = self.mixin.parse_shareholder_equity_history(facts)
        assert len(result) == 1
        # Standard tag should win
        assert result[0]['shareholder_equity'] == 10_000_000_000

    def test_returns_empty_when_no_equity_tags(self):
        """Should return empty list if no recognized equity tags exist."""
        facts = {'facts': {'us-gaap': {'SomeOtherTag': {'units': {'USD': []}}}}}
        result = self.mixin.parse_shareholder_equity_history(facts)
        assert result == []


# ── EPS Calculated Fallback Tests ─────────────────────────────────────────────

class TestCalculatedEPSFallback:

    def setup_method(self):
        self.mixin = ConcreteEPSMixin()

    def _make_facts_with_ni_and_shares(self, ni_by_year, shares_by_year):
        """Build company_facts with NetIncomeLoss and WeightedAverageShares."""
        ni_entries = [
            {
                'form': '10-K',
                'end': f'{year}-12-31',
                'val': ni,
                'fy': year
            }
            for year, ni in ni_by_year.items()
        ]
        shares_entries = [
            {
                'form': '10-K',
                'end': f'{year}-12-31',
                'val': shares,
                'fy': year
            }
            for year, shares in shares_by_year.items()
        ]
        return {
            'facts': {
                'us-gaap': {
                    'NetIncomeLoss': {'units': {'USD': ni_entries}},
                    'WeightedAverageNumberOfDilutedSharesOutstanding': {'units': {'shares': shares_entries}},
                }
            }
        }

    def test_calculated_eps_when_direct_eps_missing(self):
        """calculate_split_adjusted_annual_eps_history returns EPS when EarningsPerShareDiluted absent."""
        facts = self._make_facts_with_ni_and_shares(
            ni_by_year={2023: 1_000_000_000, 2022: 900_000_000},
            shares_by_year={2023: 500_000_000, 2022: 500_000_000}
        )
        # Direct EPS should be empty (no EarningsPerShareDiluted tag)
        direct_eps = self.mixin.parse_eps_history(facts)
        assert direct_eps == []

        # Calculated EPS should work
        calc_eps = self.mixin.calculate_split_adjusted_annual_eps_history(facts)
        assert len(calc_eps) == 2
        assert abs(calc_eps[0]['eps'] - 2.0) < 0.001  # 1B / 500M = 2.0
        assert calc_eps[0]['year'] == 2023

    def test_calculated_eps_uses_division(self):
        """EPS = net_income / shares_outstanding."""
        facts = self._make_facts_with_ni_and_shares(
            ni_by_year={2024: 4_200_000_000},
            shares_by_year={2024: 1_000_000_000}
        )
        calc_eps = self.mixin.calculate_split_adjusted_annual_eps_history(facts)
        assert len(calc_eps) == 1
        assert abs(calc_eps[0]['eps'] - 4.2) < 0.001

    def test_calculated_eps_empty_when_shares_missing(self):
        """Should return empty if shares data is not available."""
        facts = {
            'facts': {
                'us-gaap': {
                    'NetIncomeLoss': {
                        'units': {'USD': [make_annual_entry(2023, 500_000_000)]}
                    }
                    # No shares tag
                }
            }
        }
        calc_eps = self.mixin.calculate_split_adjusted_annual_eps_history(facts)
        assert calc_eps == []


# ── edgar_data dict wiring test ────────────────────────────────────────────────

def test_store_edgar_earnings_uses_calculated_eps_when_direct_missing():
    """
    _store_edgar_earnings should store EPS from calculated_eps_history
    when eps_history is empty.
    """
    from unittest.mock import MagicMock, patch
    from data_fetcher.earnings import EarningsMixin

    class ConcreteEarningsMixin(EarningsMixin):
        pass

    mixin = ConcreteEarningsMixin()
    mixin.db = MagicMock()
    mixin._backfill_debt_to_equity = MagicMock()
    mixin._backfill_cash_flow = MagicMock()

    edgar_data = {
        'eps_history': [],  # Direct EPS missing
        'calculated_eps_history': [  # Calculated fallback present
            {'year': 2023, 'eps': 3.50, 'fiscal_end': '2023-12-31'},
        ],
        'revenue_history': [
            {'year': 2023, 'revenue': 10_000_000_000, 'fiscal_end': '2023-12-31'}
        ],
        'net_income_annual': [],
        'debt_to_equity_history': [],
        'shareholder_equity_history': [],
        'cash_flow_history': [],
        'cash_equivalents_history': [],
        'shares_outstanding_history': [],
        'dividend_history': [],
    }

    mixin._store_edgar_earnings('TESTCO', edgar_data)

    # Verify save_earnings_history was called with eps=3.50
    assert mixin.db.save_earnings_history.called
    call_kwargs = mixin.db.save_earnings_history.call_args
    # eps is the 3rd positional argument
    saved_eps = call_kwargs[0][2] if call_kwargs[0] else call_kwargs[1].get('eps')
    assert saved_eps == pytest.approx(3.50), f"Expected EPS 3.50, got {saved_eps}"


# ── Net Income Tag Coverage Tests ─────────────────────────────────────────────

class ConcreteIncomeMixin(IncomeMixin):
    """Concrete subclass for testing the mixin."""
    pass


class TestNetIncomeTagCoverage:

    def setup_method(self):
        self.mixin = ConcreteIncomeMixin()

    def _make_annual_ni_facts(self, tag, ni_by_year, namespace='us-gaap'):
        """Build company_facts with a specific net income tag."""
        entries = [
            {
                'form': '10-K',
                'start': f'{year}-01-01',
                'end': f'{year}-12-31',
                'val': ni,
                'fy': year,
                'fp': 'FY'
            }
            for year, ni in ni_by_year.items()
        ]
        return {'facts': {namespace: {tag: {'units': {'USD': entries}}}}}

    def test_standard_net_income_loss_tag(self):
        """NetIncomeLoss is the primary tag and must still work."""
        facts = self._make_annual_ni_facts('NetIncomeLoss', {2023: 2_000_000_000, 2022: 1_800_000_000})
        result = self.mixin.parse_net_income_history(facts)
        assert len(result) == 2
        assert result[0]['year'] == 2023
        assert result[0]['net_income'] == 2_000_000_000

    def test_preferred_stock_adjusted_ni_tag(self):
        """NetIncomeLossAvailableToCommonStockholdersBasic used by preferred-stock companies."""
        facts = self._make_annual_ni_facts(
            'NetIncomeLossAvailableToCommonStockholdersBasic',
            {2023: 800_000_000, 2022: 750_000_000}
        )
        result = self.mixin.parse_net_income_history(facts)
        assert len(result) == 2, f"Expected 2 results, got {len(result)}"
        assert result[0]['net_income'] == 800_000_000

    def test_profit_loss_us_gaap_tag(self):
        """ProfitLoss is used by some consolidated entities under US-GAAP."""
        facts = self._make_annual_ni_facts('ProfitLoss', {2023: 1_500_000_000})
        result = self.mixin.parse_net_income_history(facts)
        assert len(result) == 1, f"Expected 1 result, got {len(result)}"
        assert result[0]['net_income'] == 1_500_000_000

    def test_standard_tag_preferred_over_fallback(self):
        """NetIncomeLoss wins over NetIncomeLossAvailableToCommonStockholdersBasic."""
        facts = {
            'facts': {
                'us-gaap': {
                    'NetIncomeLoss': {
                        'units': {'USD': [
                            {'form': '10-K', 'start': '2023-01-01', 'end': '2023-12-31',
                             'val': 3_000_000_000, 'fy': 2023}
                        ]}
                    },
                    'NetIncomeLossAvailableToCommonStockholdersBasic': {
                        'units': {'USD': [
                            {'form': '10-K', 'start': '2023-01-01', 'end': '2023-12-31',
                             'val': 2_800_000_000, 'fy': 2023}
                        ]}
                    },
                }
            }
        }
        result = self.mixin.parse_net_income_history(facts)
        assert len(result) == 1
        # Standard tag should win (NetIncomeLoss is first in the list)
        assert result[0]['net_income'] == 3_000_000_000


# ── Quarterly EPS Extraction Tests ────────────────────────────────────────────

class TestQuarterlyEPSExtraction:
    """
    Test that _extract_quarterly_from_raw_xbrl finds EPS even when revenue is absent.
    The period key discovery must be independent of revenue extraction.
    """

    def setup_method(self):
        from edgar_fetcher import EdgarFetcher
        self.ef = EdgarFetcher.__new__(EdgarFetcher)

    def _make_raw_data(self, period_key, revenue=None, net_income=None, eps=None):
        """Build minimal raw_data list as returned by income_statement.get_raw_data()."""
        items = []

        if revenue is not None:
            items.append({
                'label': 'Total Revenue',
                'concept': 'us-gaap_Revenues',
                'has_values': True,
                'is_abstract': False,
                'is_dimension': False,
                'values': {period_key: revenue}
            })

        if net_income is not None:
            items.append({
                'label': 'Net Income',
                'concept': 'us-gaap_NetIncomeLoss',
                'has_values': True,
                'is_abstract': False,
                'is_dimension': False,
                'values': {period_key: net_income}
            })

        if eps is not None:
            items.append({
                'label': 'Earnings Per Share - Diluted',
                'concept': 'us-gaap_EarningsPerShareDiluted',
                'has_values': True,
                'is_abstract': False,
                'is_dimension': False,
                'values': {period_key: eps}
            })

        return items

    def _make_income_stmt_mock(self, raw_data):
        from unittest.mock import MagicMock
        stmt = MagicMock()
        stmt.get_raw_data.return_value = raw_data
        return stmt

    def test_extracts_eps_with_revenue_present(self):
        """Standard case: revenue present, period key discovered, all fields extracted."""
        period_key = 'duration_2024-01-01_2024-03-31'  # 90 days
        raw = self._make_raw_data(period_key, revenue=5e9, net_income=1e9, eps=2.50)
        stmt = self._make_income_stmt_mock(raw)

        result = self.ef._extract_quarterly_from_raw_xbrl('TEST', stmt)
        assert result['revenue'] == 5e9
        assert result['net_income'] == 1e9
        assert result['eps'] == 2.50

    def test_extracts_eps_without_revenue(self):
        """
        Key fix: EPS and NI must be extracted even when no revenue item is present.
        Covers pre-revenue companies and financial firms with non-standard revenue labels.
        """
        period_key = 'duration_2024-01-01_2024-03-31'
        raw = self._make_raw_data(period_key, revenue=None, net_income=-50_000_000, eps=-0.12)
        stmt = self._make_income_stmt_mock(raw)

        result = self.ef._extract_quarterly_from_raw_xbrl('BIOTECH', stmt)
        assert result['revenue'] is None
        assert result['net_income'] == -50_000_000, f"Expected NI, got {result['net_income']}"
        assert result['eps'] == -0.12, f"Expected EPS, got {result['eps']}"

    def test_extracts_eps_with_alternative_diluted_labels(self):
        """
        EPS must be extracted when the label uses alternative wording.
        MNST uses "Diluted (in dollar per share)", CAVA uses "Diluted (in usd per share)".
        """
        period_key = 'duration_2024-01-01_2024-03-31'
        alternative_labels = [
            'Diluted (in dollar per share)',
            'Diluted (in usd per share)',
            'Diluted net income per common share (in usd per share)',
        ]
        for label in alternative_labels:
            raw = [
                {
                    'label': 'Net Income',
                    'concept': 'us-gaap_NetIncomeLoss',
                    'has_values': True,
                    'is_abstract': False,
                    'is_dimension': False,
                    'values': {period_key: 1_000_000_000},
                },
                {
                    'label': label,
                    'concept': 'us-gaap_EarningsPerShareDiluted',
                    'has_values': True,
                    'is_abstract': False,
                    'is_dimension': False,
                    'values': {period_key: 1.23},
                },
            ]
            stmt = self._make_income_stmt_mock(raw)
            result = self.ef._extract_quarterly_from_raw_xbrl('MNST', stmt)
            assert result['eps'] == 1.23, f"EPS not extracted for label '{label}': got {result['eps']}"

    def test_period_key_uses_most_recent_90day_period(self):
        """When multiple ~90-day periods exist, pick the most recent one."""
        period_key_old = 'duration_2023-01-01_2023-03-31'
        period_key_new = 'duration_2024-01-01_2024-03-31'
        raw = [
            {
                'label': 'Net Income',
                'concept': 'us-gaap_NetIncomeLoss',
                'has_values': True,
                'is_abstract': False,
                'is_dimension': False,
                'values': {period_key_old: 800_000_000, period_key_new: 1_200_000_000}
            }
        ]
        stmt = self._make_income_stmt_mock(raw)
        result = self.ef._extract_quarterly_from_raw_xbrl('TEST', stmt)
        assert result['net_income'] == 1_200_000_000

    def test_ignores_non_quarterly_periods(self):
        """Annual (~365 day) periods must not be treated as quarterly."""
        annual_key = 'duration_2023-01-01_2023-12-31'   # 364 days - annual
        quarterly_key = 'duration_2023-10-01_2023-12-31'  # 91 days - Q4
        raw = [
            {
                'label': 'Net Income',
                'concept': 'us-gaap_NetIncomeLoss',
                'has_values': True,
                'is_abstract': False,
                'is_dimension': False,
                'values': {annual_key: 5_000_000_000, quarterly_key: 1_400_000_000}
            }
        ]
        stmt = self._make_income_stmt_mock(raw)
        result = self.ef._extract_quarterly_from_raw_xbrl('TEST', stmt)
        assert result['net_income'] == 1_400_000_000  # Q4 value, not annual


# ── Quarterly job revenue guard fix ────────────────────────────────────────────

def test_quarterly_job_processes_eps_only_company():
    """
    Quarterly cache job must store EPS/NI data even when revenue_quarterly is empty.
    Previously the guard 'if not quarterly_data.get(revenue_quarterly)' would drop
    all data for pre-revenue companies and financial firms.

    Validates the has_any_quarterly_data guard logic used in _run_quarterly_fundamentals_cache.
    """
    # Old guard: rejects any company without revenue (pre-revenue biotechs, banks)
    def old_guard(quarterly_data):
        return bool(quarterly_data.get('revenue_quarterly'))

    # New guard: accepts any company with ANY quarterly data field populated
    def new_guard(quarterly_data):
        return bool(
            quarterly_data.get('revenue_quarterly') or
            quarterly_data.get('eps_quarterly') or
            quarterly_data.get('net_income_quarterly') or
            quarterly_data.get('cash_flow_quarterly')
        )

    no_revenue_data = {
        'revenue_quarterly': [],
        'eps_quarterly': [
            {'year': 2024, 'quarter': 'Q1', 'eps': -0.45, 'fiscal_end': '2024-03-31'}
        ],
        'net_income_quarterly': [
            {'year': 2024, 'quarter': 'Q1', 'net_income': -10_000_000, 'fiscal_end': '2024-03-31'}
        ],
        'cash_flow_quarterly': [],
    }

    assert not old_guard(no_revenue_data), "Old guard incorrectly passes this case"
    assert new_guard(no_revenue_data), "New guard must accept company with EPS but no revenue"


# ── Capex label expansion tests ────────────────────────────────────────────────

class TestCapexLabelExtraction:
    """
    Tests that capital expenditures are found using expanded label patterns.
    The to_dataframe() CF extraction previously only matched 'Capital Expenditure'
    or 'Property', missing labels like 'Capital addition' or 'Purchases of equipment'.
    """

    def _make_cf_df_mock(self, label, value, quarterly_col='2024-03-31 (Q1)'):
        """Build a minimal pandas DataFrame simulating a cash flow statement row."""
        import pandas as pd
        return pd.DataFrame([
            {'label': label, quarterly_col: value, 'abstract': False}
        ])

    def test_capital_addition_label_matches(self):
        """'Capital additions' label (used by some industrials) must match."""
        import pandas as pd
        cf_df = pd.DataFrame([
            {'label': 'Capital additions', '2024-03-31 (Q1)': -25_000_000, 'abstract': False}
        ])
        capex_rows = cf_df[
            cf_df['label'].str.contains('Capital Expenditure', case=False, na=False) |
            cf_df['label'].str.contains('Capital addition', case=False, na=False) |
            cf_df['label'].str.contains('Property', case=False, na=False) |
            (cf_df['label'].str.contains('Purchases', case=False, na=False) &
             cf_df['label'].str.contains('equipment', case=False, na=False))
        ]
        assert len(capex_rows) == 1

    def test_purchases_of_equipment_label_matches(self):
        """'Purchases of equipment and furniture' must match."""
        import pandas as pd
        cf_df = pd.DataFrame([
            {'label': 'Purchases of equipment and furniture', '2024-03-31 (Q1)': -8_000_000, 'abstract': False}
        ])
        capex_rows = cf_df[
            cf_df['label'].str.contains('Capital Expenditure', case=False, na=False) |
            cf_df['label'].str.contains('Capital addition', case=False, na=False) |
            cf_df['label'].str.contains('Property', case=False, na=False) |
            (cf_df['label'].str.contains('Purchases', case=False, na=False) &
             cf_df['label'].str.contains('equipment', case=False, na=False))
        ]
        assert len(capex_rows) == 1

    def test_original_property_label_still_matches(self):
        """'Purchases of property and equipment' (most common) still matches."""
        import pandas as pd
        cf_df = pd.DataFrame([
            {'label': 'Purchases of property and equipment', '2024-03-31 (Q1)': -50_000_000, 'abstract': False}
        ])
        capex_rows = cf_df[
            cf_df['label'].str.contains('Capital Expenditure', case=False, na=False) |
            cf_df['label'].str.contains('Capital addition', case=False, na=False) |
            cf_df['label'].str.contains('Property', case=False, na=False) |
            (cf_df['label'].str.contains('Purchases', case=False, na=False) &
             cf_df['label'].str.contains('equipment', case=False, na=False))
        ]
        assert len(capex_rows) == 1


# ── CF/BS date-column and discrete-CF tests ────────────────────────────────────

class ConcreteEFMixin:
    """Minimal concrete class that includes FundamentalsMixin for direct method testing."""
    pass


def _make_ef_with_fundamentals():
    """Return a FundamentalsMixin instance for testing helper methods."""
    from edgar_fetcher.fundamentals import FundamentalsMixin

    class _Concrete(FundamentalsMixin):
        pass

    return _Concrete()


class TestFirstDateColumn:
    """_first_date_column picks the first bare YYYY-MM-DD column."""

    def setup_method(self):
        self.ef = _make_ef_with_fundamentals()

    def test_returns_first_date_column(self):
        import pandas as pd
        df = pd.DataFrame(columns=['concept', 'label', '2025-09-30', '2024-09-30', 'level'])
        assert self.ef._first_date_column(df) == '2025-09-30'

    def test_returns_none_when_no_bare_date_column(self):
        """Old-style (Q3) suffix columns should not match."""
        import pandas as pd
        df = pd.DataFrame(columns=['concept', 'label', '2025-09-30 (Q3)', 'level'])
        assert self.ef._first_date_column(df) is None

    def test_ignores_non_date_columns(self):
        import pandas as pd
        df = pd.DataFrame(columns=['concept', 'label', 'standard_concept', '2025-12-27', 'abstract'])
        assert self.ef._first_date_column(df) == '2025-12-27'


class TestComputeDiscreteCF:
    """_compute_discrete_cf converts YTD cash flow values to discrete quarterly values."""

    def setup_method(self):
        self.ef = _make_ef_with_fundamentals()

    def test_single_quarter_equals_ytd(self):
        """Q1 only: discrete = YTD (no prior quarter to subtract)."""
        staging = [
            {'year': 2024, 'quarter': 'Q1', 'fiscal_end': '2024-03-31', 'ocf_ytd': 1_000, 'capex_ytd': 200}
        ]
        result = self.ef._compute_discrete_cf(staging)
        assert len(result) == 1
        assert result[0]['operating_cash_flow'] == 1_000
        assert result[0]['capital_expenditures'] == 200
        assert result[0]['free_cash_flow'] == 800

    def test_two_quarters_subtracts_prior_ytd(self):
        """Q2 discrete = Q2 YTD - Q1 YTD."""
        staging = [
            {'year': 2024, 'quarter': 'Q1', 'fiscal_end': '2024-03-31', 'ocf_ytd': 1_000, 'capex_ytd': 200},
            {'year': 2024, 'quarter': 'Q2', 'fiscal_end': '2024-06-30', 'ocf_ytd': 2_200, 'capex_ytd': 500},
        ]
        result = self.ef._compute_discrete_cf(staging)
        assert len(result) == 2
        assert result[1]['quarter'] == 'Q2'
        assert result[1]['operating_cash_flow'] == 1_200  # 2200 - 1000
        assert result[1]['capital_expenditures'] == 300   # 500 - 200
        assert result[1]['free_cash_flow'] == 900

    def test_full_year_four_quarters(self):
        """Q1-Q4 all correctly computed by consecutive subtraction."""
        staging = [
            {'year': 2024, 'quarter': 'Q1', 'fiscal_end': '2024-03-31', 'ocf_ytd': 1_000, 'capex_ytd': 100},
            {'year': 2024, 'quarter': 'Q2', 'fiscal_end': '2024-06-30', 'ocf_ytd': 2_200, 'capex_ytd': 250},
            {'year': 2024, 'quarter': 'Q3', 'fiscal_end': '2024-09-30', 'ocf_ytd': 3_100, 'capex_ytd': 450},
            {'year': 2024, 'quarter': 'Q4', 'fiscal_end': '2024-12-31', 'ocf_ytd': 4_500, 'capex_ytd': 700},
        ]
        result = self.ef._compute_discrete_cf(staging)
        quarters = {r['quarter']: r for r in result}
        assert quarters['Q1']['operating_cash_flow'] == 1_000
        assert quarters['Q2']['operating_cash_flow'] == 1_200
        assert quarters['Q3']['operating_cash_flow'] == 900
        assert quarters['Q4']['operating_cash_flow'] == 1_400
        assert quarters['Q4']['capital_expenditures'] == 250  # 700 - 450

    def test_multiple_fiscal_years_independent(self):
        """Year boundary resets accumulation — Q1-2024 discrete must not subtract Q4-2023 YTD."""
        staging = [
            {'year': 2023, 'quarter': 'Q1', 'fiscal_end': '2023-03-31', 'ocf_ytd': 500, 'capex_ytd': 50},
            {'year': 2023, 'quarter': 'Q2', 'fiscal_end': '2023-06-30', 'ocf_ytd': 1_100, 'capex_ytd': 120},
            {'year': 2024, 'quarter': 'Q1', 'fiscal_end': '2024-03-31', 'ocf_ytd': 800, 'capex_ytd': 80},
            {'year': 2024, 'quarter': 'Q2', 'fiscal_end': '2024-06-30', 'ocf_ytd': 1_800, 'capex_ytd': 200},
        ]
        result = self.ef._compute_discrete_cf(staging)
        by_yr_q = {(r['year'], r['quarter']): r for r in result}
        # 2024 Q1 must = 800 (not 800 - 1100)
        assert by_yr_q[(2024, 'Q1')]['operating_cash_flow'] == 800
        assert by_yr_q[(2024, 'Q2')]['operating_cash_flow'] == 1_000  # 1800 - 800

    def test_none_ocf_handled_gracefully(self):
        """Missing OCF in a quarter does not raise; propagates None."""
        staging = [
            {'year': 2024, 'quarter': 'Q1', 'fiscal_end': '2024-03-31', 'ocf_ytd': 1_000, 'capex_ytd': 200},
            {'year': 2024, 'quarter': 'Q2', 'fiscal_end': '2024-06-30', 'ocf_ytd': None, 'capex_ytd': 500},
        ]
        result = self.ef._compute_discrete_cf(staging)
        assert len(result) == 2
        assert result[1]['operating_cash_flow'] is None
        assert result[1]['capital_expenditures'] == 300  # 500 - 200


class TestCFRawDataExtraction:
    """CF extraction uses get_raw_data() with ~90-day period detection, same as income statement."""

    def setup_method(self):
        from edgar_fetcher.fundamentals import FundamentalsMixin
        from unittest.mock import MagicMock
        class _Concrete(FundamentalsMixin):
            pass
        self.ef = _Concrete()
        self.mock = MagicMock

    def _make_cf_raw(self, period_key, ocf=None, capex=None):
        items = []
        if ocf is not None:
            items.append({
                'label': 'Net Cash Provided by Operating Activities',
                'concept': 'us-gaap_NetCashProvidedByUsedInOperatingActivities',
                'has_values': True,
                'is_abstract': False,
                'is_dimension': False,
                'values': {period_key: ocf},
            })
        if capex is not None:
            items.append({
                'label': 'Purchases of property and equipment',
                'concept': 'us-gaap_PaymentsToAcquirePropertyPlantAndEquipment',
                'has_values': True,
                'is_abstract': False,
                'is_dimension': False,
                'values': {period_key: capex},
            })
        return items

    def test_ytd_period_key_extracted(self):
        """YTD period key gives OCF and abs(capex) from _extract_cf_from_raw_data."""
        period_key = 'duration_2024-01-01_2024-09-30'  # 9-month YTD
        raw = self._make_cf_raw(period_key, ocf=3_000_000_000, capex=-500_000_000)
        ocf, capex = self.ef._extract_cf_from_raw_data(raw, period_key)
        assert ocf == 3_000_000_000
        assert capex == 500_000_000  # abs() applied

    def test_negative_ocf_preserved(self):
        """Negative operating cash flow is stored as-is (not abs'd)."""
        period_key = 'duration_2024-01-01_2024-09-30'
        raw = self._make_cf_raw(period_key, ocf=-200_000_000, capex=-50_000_000)
        ocf, capex = self.ef._extract_cf_from_raw_data(raw, period_key)
        assert ocf == -200_000_000
        assert capex == 50_000_000

    def test_depreciation_of_property_not_matched_as_capex(self):
        """
        'Depreciation of property and equipment' must NOT be treated as capex.
        In annual 10-K CF statements this item appears before 'Purchases of property
        and equipment', causing it to be incorrectly captured as capex.
        """
        period_key = 'duration_2025-01-01_2025-12-31'
        raw = [
            {
                'label': 'Depreciation of property and equipment',
                'concept': 'us-gaap_Depreciation',
                'has_values': True, 'is_abstract': False, 'is_dimension': False,
                'values': {period_key: 21_000_000_000},
            },
            {
                'label': 'Net cash provided by operating activities',
                'concept': 'us-gaap_NetCashProvidedByUsedInOperatingActivities',
                'has_values': True, 'is_abstract': False, 'is_dimension': False,
                'values': {period_key: 164_000_000_000},
            },
            {
                'label': 'Purchases of property and equipment',
                'concept': 'us-gaap_PaymentsToAcquirePropertyPlantAndEquipment',
                'has_values': True, 'is_abstract': False, 'is_dimension': False,
                'values': {period_key: -91_000_000_000},
            },
        ]
        ocf, capex = self.ef._extract_cf_from_raw_data(raw, period_key)
        assert ocf == 164_000_000_000, f"OCF wrong: {ocf}"
        assert capex == 91_000_000_000, f"Capex should be purchases, not depreciation: {capex}"


# ── Cover page fiscal_end fallback tests ──────────────────────────────────────

class TestCoverPageFiscalEndFallback:
    """
    edgartools 5.x cover pages use standard_concept instead of label as the row identifier.
    The fiscal period date is only available as a column header (e.g. '2025-12-31').
    _first_date_column must be used as a fallback when 'label' column is absent.

    This affects 10-K filings for GOOG, CAT, BKNG etc. where cover page cell values
    are all None, causing fiscal_end to stay None and blocking CF YTD key lookup.
    """

    def setup_method(self):
        self.ef = _make_ef_with_fundamentals()

    def test_first_date_column_finds_date_in_cover_page_header(self):
        """edgartools 5.x cover page has date as column name, not label."""
        import pandas as pd
        # This is the actual structure returned by cover_page.to_dataframe() in edgartools 5.x
        cover_df = pd.DataFrame(
            [{'standard_concept': 'DocumentFiscalYearFocus', '2025-12-31': None, 'is_breakdown': False}],
            columns=['standard_concept', '2025-12-31', 'is_breakdown']
        )
        # The 'label' column is absent — old code path is skipped
        assert 'label' not in cover_df.columns
        # But _first_date_column should find the date in the column header
        result = self.ef._first_date_column(cover_df)
        assert result == '2025-12-31'

    def test_first_date_column_returns_none_for_non_date_columns(self):
        """Standard concept column names must not be mistaken for dates."""
        import pandas as pd
        cover_df = pd.DataFrame(
            [{'standard_concept': 'DocumentFiscalYearFocus', 'is_breakdown': False}],
            columns=['standard_concept', 'is_breakdown']
        )
        result = self.ef._first_date_column(cover_df)
        assert result is None
