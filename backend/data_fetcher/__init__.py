# ABOUTME: Composes DataFetcher from mixin classes and re-exports public API
# ABOUTME: DataFetcher combines core fetching, earnings, and financials functionality

from data_fetcher.core import DataFetcherCore, retry_on_rate_limit
from data_fetcher.earnings import EarningsMixin
from data_fetcher.financials import FinancialsMixin


class DataFetcher(DataFetcherCore, EarningsMixin, FinancialsMixin):
    pass
