# ABOUTME: Wrapper service for fetching macroeconomic data from the FRED API
# ABOUTME: Provides methods to get series observations and metadata for economic indicators

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fredapi import Fred

logger = logging.getLogger(__name__)

# Series we support in the MVP
SUPPORTED_SERIES = {
    'GDPC1': {
        'name': 'Real GDP',
        'category': 'output',
        'frequency': 'quarterly',
        'units': 'Billions of Chained 2017 Dollars',
        'description': 'Real Gross Domestic Product, inflation-adjusted'
    },
    'UNRATE': {
        'name': 'Unemployment Rate',
        'category': 'employment',
        'frequency': 'monthly',
        'units': 'Percent',
        'description': 'Civilian unemployment rate'
    },
    'CPIAUCSL': {
        'name': 'Consumer Price Index',
        'category': 'inflation',
        'frequency': 'monthly',
        'units': 'Index 1982-1984=100',
        'description': 'CPI for All Urban Consumers: All Items'
    },
    'FEDFUNDS': {
        'name': 'Federal Funds Rate',
        'category': 'interest_rates',
        'frequency': 'monthly',
        'units': 'Percent',
        'description': 'Effective Federal Funds Rate'
    },
    'DGS10': {
        'name': '10-Year Treasury',
        'category': 'interest_rates',
        'frequency': 'daily',
        'units': 'Percent',
        'description': '10-Year Treasury Constant Maturity Rate'
    },
    'T10Y2Y': {
        'name': 'Yield Curve Spread',
        'category': 'interest_rates',
        'frequency': 'daily',
        'units': 'Percent',
        'description': '10-Year Treasury minus 2-Year Treasury spread'
    },
    'VIXCLS': {
        'name': 'VIX',
        'category': 'volatility',
        'frequency': 'daily',
        'units': 'Index',
        'description': 'CBOE Volatility Index'
    },
    'ICSA': {
        'name': 'Initial Jobless Claims',
        'category': 'employment',
        'frequency': 'weekly',
        'units': 'Number',
        'description': 'Initial Claims for Unemployment Insurance'
    },
    'HOUST': {
        'name': 'Housing Starts',
        'category': 'housing',
        'frequency': 'monthly',
        'units': 'Thousands of Units (SAAR)',
        'description': 'New privately owned housing units started'
    },
    'RSXFS': {
        'name': 'Advance Retail Sales',
        'category': 'consumer',
        'frequency': 'monthly',
        'units': 'Millions of Dollars',
        'description': 'Advance Retail Sales: Retail and Food Services'
    },
    'TOTALSA': {
        'name': 'Total Vehicle Sales',
        'category': 'consumer',
        'frequency': 'monthly',
        'units': 'Millions of Units (SAAR)',
        'description': 'Total Vehicle Sales'
    },
    'UMCSENT': {
        'name': 'Consumer Sentiment',
        'category': 'consumer',
        'frequency': 'monthly',
        'units': 'Index 1966=100',
        'description': 'University of Michigan: Consumer Sentiment'
    },
    'PSAVERT': {
        'name': 'Personal Saving Rate',
        'category': 'consumer',
        'frequency': 'monthly',
        'units': 'Percent',
        'description': 'Personal saving as a percentage of disposable personal income'
    },
    'DRCCLACBS': {
        'name': 'Credit Card Delinquency',
        'category': 'consumer',
        'frequency': 'quarterly',
        'units': 'Percent',
        'description': 'Delinquency Rate on Credit Card Loans, All Commercial Banks'
    },
    'RETAILIRSA': {
        'name': 'Retail Inventory/Sales Ratio',
        'category': 'consumer',
        'frequency': 'monthly',
        'units': 'Ratio',
        'description': 'Retailers: Inventories to Sales Ratio'
    },
    'GDP': {
        'name': 'Nominal GDP',
        'category': 'output',
        'frequency': 'quarterly',
        'units': 'Billions of Dollars',
        'description': 'Gross Domestic Product'
    },
    'CP': {
        'name': 'Corporate Profits',
        'category': 'corporate',
        'frequency': 'quarterly',
        'units': 'Billions of Dollars',
        'description': 'Corporate Profits After Tax (without IVA and CCAdj)'
    },
    'TSIFRGHT': {
        'name': 'Freight Index',
        'category': 'output',
        'frequency': 'monthly',
        'units': 'Index 2000=100',
        'description': 'Freight Transportation Services Index'
    },
    'BAA10Y': {
        'name': 'Corporate Bond Spread',
        'category': 'interest_rates',
        'frequency': 'daily',
        'units': 'Percent',
        'description': "Moody's Seasoned Baa Corporate Bond Yield Relative to 10-Year Treasury"
    },
    'M2SL': {
        'name': 'M2 Money Supply',
        'category': 'inflation',
        'frequency': 'monthly',
        'units': 'Billions of Dollars',
        'description': 'M2 Money Stock'
    },
    'PPIACO': {
        'name': 'PPI All Commodities',
        'category': 'inflation',
        'frequency': 'monthly',
        'units': 'Index 1982=100',
        'description': 'Producer Price Index by Commodity: All Commodities'
    }
}

# Category display names
CATEGORIES = {
    'output': 'Economic Output',
    'employment': 'Employment',
    'inflation': 'Inflation',
    'interest_rates': 'Interest Rates',
    'volatility': 'Market Volatility',
    'consumer': 'Consumer Health',
    'housing': 'Housing Market',
    'corporate': 'Corporate Health'
}


class FredService:
    def __init__(self):
        api_key = os.environ.get('FRED_API_KEY')
        if not api_key:
            logger.warning("FRED_API_KEY not set - FRED features will not work")
            self.fred = None
        else:
            self.fred = Fred(api_key=api_key)
            logger.info("FRED service initialized")

    def is_available(self) -> bool:
        return self.fred is not None

    def get_series(self, series_id: str, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        Fetch observations for a FRED series.

        Args:
            series_id: FRED series ID (e.g., 'UNRATE')
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)

        Returns:
            Dict with series metadata and observations
        """
        if not self.fred:
            return {'error': 'FRED API key not configured'}

        series_id = series_id.upper()

        try:
            # Fetch observations
            data = self.fred.get_series(
                series_id,
                observation_start=start_date,
                observation_end=end_date
            )

            # Convert pandas Series to list of observations
            observations = []
            for date, value in data.items():
                if value is not None and not (isinstance(value, float) and value != value):  # Check for NaN
                    observations.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'value': float(value)
                    })

            # Get metadata if it's a known series
            metadata = SUPPORTED_SERIES.get(series_id, {})

            return {
                'series_id': series_id,
                'name': metadata.get('name', series_id),
                'frequency': metadata.get('frequency', 'unknown'),
                'units': metadata.get('units', ''),
                'description': metadata.get('description', ''),
                'observations': observations,
                'observation_count': len(observations),
                'latest': observations[-1] if observations else None
            }

        except Exception as e:
            logger.error(f"Error fetching FRED series {series_id}: {e}")
            return {'error': str(e), 'series_id': series_id}

    def get_series_info(self, series_id: str) -> Dict[str, Any]:
        """Get metadata for a FRED series."""
        if not self.fred:
            return {'error': 'FRED API key not configured'}

        series_id = series_id.upper()

        # Return cached metadata for known series
        if series_id in SUPPORTED_SERIES:
            info = SUPPORTED_SERIES[series_id].copy()
            info['series_id'] = series_id
            return info

        # For unknown series, try to fetch from FRED
        try:
            info = self.fred.get_series_info(series_id)
            return {
                'series_id': series_id,
                'name': info.get('title', series_id),
                'frequency': info.get('frequency_short', 'unknown'),
                'units': info.get('units', ''),
                'description': info.get('notes', '')
            }
        except Exception as e:
            logger.error(f"Error fetching FRED series info {series_id}: {e}")
            return {'error': str(e), 'series_id': series_id}

    def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Fetch current values and recent history for all dashboard indicators.
        Returns data for all 8 MVP series.
        """
        if not self.fred:
            return {'error': 'FRED API key not configured'}

        # Fetch last 2 years of data for charts
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)
        start_str = start_date.strftime('%Y-%m-%d')

        indicators = []
        by_category = {}

        for series_id, metadata in SUPPORTED_SERIES.items():
            result = self.get_series(series_id, start_date=start_str)

            if 'error' not in result:
                # Calculate change from previous observation
                change = None
                change_percent = None
                if len(result['observations']) >= 2:
                    current = result['observations'][-1]['value']
                    previous = result['observations'][-2]['value']
                    change = current - previous
                    if previous != 0:
                        change_percent = (change / previous) * 100

                indicator = {
                    'series_id': series_id,
                    'name': metadata['name'],
                    'category': metadata['category'],
                    'frequency': metadata['frequency'],
                    'units': metadata['units'],
                    'description': metadata['description'],
                    'current_value': result['latest']['value'] if result['latest'] else None,
                    'current_date': result['latest']['date'] if result['latest'] else None,
                    'change': change,
                    'change_percent': change_percent,
                    'observations': result['observations']
                }
                indicators.append(indicator)

                # Group by category
                cat = metadata['category']
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(indicator)

        return {
            'indicators': indicators,
            'by_category': by_category,
            'categories': CATEGORIES,
            'fetched_at': datetime.now().isoformat()
        }

    def get_economic_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current economic conditions.
        Returns just the latest values without full history.
        """
        if not self.fred:
            return {'error': 'FRED API key not configured'}

        summary = {}

        for series_id, metadata in SUPPORTED_SERIES.items():
            try:
                # Fetch just the last few observations for change calculation
                data = self.fred.get_series(series_id, observation_start=(datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'))

                if data is not None and len(data) > 0:
                    # Get last non-NaN value
                    valid_data = data.dropna()
                    if len(valid_data) > 0:
                        current = float(valid_data.iloc[-1])
                        current_date = valid_data.index[-1].strftime('%Y-%m-%d')

                        change = None
                        if len(valid_data) >= 2:
                            previous = float(valid_data.iloc[-2])
                            change = current - previous

                        summary[series_id] = {
                            'name': metadata['name'],
                            'value': current,
                            'date': current_date,
                            'change': change,
                            'units': metadata['units'],
                            'category': metadata['category']
                        }
            except Exception as e:
                logger.error(f"Error fetching {series_id} for summary: {e}")
                continue

        return {
            'indicators': summary,
            'fetched_at': datetime.now().isoformat()
        }


# Singleton instance
_fred_service = None


def get_fred_service() -> FredService:
    global _fred_service
    if _fred_service is None:
        _fred_service = FredService()
    return _fred_service
