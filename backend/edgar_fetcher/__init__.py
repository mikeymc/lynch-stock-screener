# ABOUTME: Package that composes EdgarFetcher from mixin classes
# ABOUTME: Re-exports the composed EdgarFetcher class for backward compatibility

from edgar_fetcher.core import EdgarFetcherCore
from edgar_fetcher.eps import EPSMixin
from edgar_fetcher.revenue import RevenueMixin
from edgar_fetcher.income import IncomeMixin
from edgar_fetcher.cash_flow import CashFlowMixin
from edgar_fetcher.shares import SharesMixin
from edgar_fetcher.equity_debt import EquityDebtMixin
from edgar_fetcher.fundamentals import FundamentalsMixin
from edgar_fetcher.filings import FilingsMixin


class EdgarFetcher(EdgarFetcherCore, EPSMixin, RevenueMixin, IncomeMixin,
                   CashFlowMixin, SharesMixin, EquityDebtMixin,
                   FundamentalsMixin, FilingsMixin):
    pass
