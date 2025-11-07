# ABOUTME: Schwab API client for fetching historical stock prices
# ABOUTME: Handles OAuth authentication and price history requests

import os
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Try to load environment variables from .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, will use system environment variables only


class SchwabClient:
    """Client for interacting with Schwab API to fetch historical stock prices"""

    def __init__(self):
        """Initialize Schwab client with OAuth credentials"""
        self.api_key = os.getenv('SCHWAB_API_KEY')
        self.api_secret = os.getenv('SCHWAB_API_SECRET')
        self.redirect_uri = os.getenv('SCHWAB_REDIRECT_URI', 'https://localhost')
        self.token_path = os.getenv('SCHWAB_TOKEN_PATH', './tokens/schwab_tokens.json')

        self.client = None
        self._authenticated = False

    def authenticate(self) -> bool:
        """
        Authenticate with Schwab API using OAuth

        Returns:
            bool: True if authentication successful, False otherwise
        """
        if not self.api_key or not self.api_secret:
            logger.warning("Schwab API credentials not configured")
            return False

        try:
            # Try to import schwab-py
            try:
                from schwab import auth, client as schwab_client
            except ImportError:
                logger.error("schwab-py library not installed. Run: pip install schwab-py")
                return False

            # Ensure token directory exists
            token_dir = os.path.dirname(self.token_path)
            if token_dir and not os.path.exists(token_dir):
                os.makedirs(token_dir)

            # Try to load existing token or create new one
            if os.path.exists(self.token_path):
                self.client = auth.client_from_token_file(
                    self.token_path,
                    self.api_key,
                    self.api_secret
                )
            else:
                # First time auth - will open browser for OAuth
                self.client = auth.client_from_manual_flow(
                    self.api_key,
                    self.api_secret,
                    self.redirect_uri,
                    self.token_path
                )

            logger.info("Schwab API authentication successful")
            self._authenticated = True
            return True
        except Exception as e:
            logger.error(f"Schwab API authentication failed: {type(e).__name__}: {e}")
            self._authenticated = False
            return False

    def get_historical_price(self, symbol: str, target_date: str) -> Optional[float]:
        """
        Fetch closing price for a stock on a specific date

        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL')
            target_date: Date in YYYY-MM-DD format

        Returns:
            Closing price as float, or None if unavailable
        """
        if not self._authenticated:
            if not self.authenticate():
                return None

        try:
            # Parse target date
            date_obj = datetime.strptime(target_date, '%Y-%m-%d')

            # Try to import schwab-py Client
            try:
                from schwab.client import Client
            except ImportError:
                logger.error("schwab-py library not installed")
                return None

            # Fetch price history for a range around the target date
            # We fetch a few days before and after to handle weekends/holidays
            start_date = date_obj - timedelta(days=7)
            end_date = date_obj + timedelta(days=3)

            # Get price history
            response = self.client.get_price_history(
                symbol,
                period_type=Client.PriceHistory.PeriodType.MONTH,
                frequency_type=Client.PriceHistory.FrequencyType.DAILY,
                frequency=Client.PriceHistory.Frequency.DAILY,
                start_datetime=start_date,
                end_datetime=end_date
            )

            if response.status_code != 200:
                logger.error(f"Schwab API returned status {response.status_code} for {symbol}")
                return None

            data = response.json()
            candles = data.get('candles', [])

            if not candles:
                logger.warning(f"No price data found for {symbol} around {target_date}")
                return None

            # Find the candle closest to target date
            target_timestamp = int(date_obj.timestamp() * 1000)  # Schwab uses milliseconds
            closest_candle = None
            min_diff = float('inf')

            for candle in candles:
                candle_time = candle.get('datetime', 0)
                diff = abs(candle_time - target_timestamp)
                if diff < min_diff:
                    min_diff = diff
                    closest_candle = candle

            if closest_candle:
                closing_price = closest_candle.get('close')
                logger.info(f"Fetched price for {symbol} on {target_date}: ${closing_price}")
                return float(closing_price) if closing_price else None

            logger.warning(f"No suitable price data found for {symbol} on {target_date}")
            return None

        except ValueError as e:
            logger.error(f"Invalid date format for {symbol}: {target_date}")
            return None
        except Exception as e:
            logger.error(f"Error fetching price for {symbol} on {target_date}: {type(e).__name__}: {e}")
            return None

    def is_available(self) -> bool:
        """Check if Schwab API is configured and available"""
        return bool(self.api_key and self.api_secret)
