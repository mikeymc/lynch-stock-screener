# ABOUTME: Database package composing domain-specific mixins into a single Database class
# ABOUTME: Re-exports Database for backward-compatible imports across the codebase

from database.core import DatabaseCore
from database.schema import SchemaMixin
from database.alerts import AlertsMixin
from database.stocks import StocksMixin
from database.analysis import AnalysisMixin
from database.filings import FilingsMixin
from database.users import UsersMixin
from database.portfolios import PortfoliosMixin
from database.screening import ScreeningMixin
from database.jobs import JobsMixin
from database.settings import SettingsMixin
from database.social import SocialMixin
from database.strategies import StrategiesMixin
from database.watchlist import WatchlistMixin
from database.briefings import BriefingsMixin


class Database(DatabaseCore, SchemaMixin, AlertsMixin, StocksMixin, AnalysisMixin,
               FilingsMixin, UsersMixin, PortfoliosMixin, ScreeningMixin,
               JobsMixin, SettingsMixin, SocialMixin, StrategiesMixin, WatchlistMixin,
               BriefingsMixin):
    pass
