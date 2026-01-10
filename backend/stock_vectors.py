# ABOUTME: Vectorized stock data service for batch scoring
# ABOUTME: Loads all stock metrics into a Pandas DataFrame for fast vectorized operations

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional, List
from database import Database
from earnings_analyzer import EarningsAnalyzer
import logging

logger = logging.getLogger(__name__)

# Default algorithm configuration (matches current production defaults)
# These are hardcoded to ensure consistent behavior even if DB is empty
DEFAULT_ALGORITHM_CONFIG = {
    # Weights (must sum to 1.0)
    'weight_peg': 0.50,
    'weight_consistency': 0.25,
    'weight_debt': 0.15,
    'weight_ownership': 0.10,
    
    # PEG thresholds (lower is better)
    'peg_excellent': 1.0,
    'peg_good': 1.5,
    'peg_fair': 2.0,
    
    # Debt thresholds (lower is better)
    'debt_excellent': 0.5,
    'debt_good': 1.0,
    'debt_moderate': 2.0,
    
    # Institutional ownership thresholds (sweet spot range)
    'inst_own_min': 0.20,
    'inst_own_max': 0.60,
    
    # Growth thresholds (higher is better)
    'revenue_growth_excellent': 15.0,
    'revenue_growth_good': 10.0,
    'revenue_growth_fair': 5.0,
    'income_growth_excellent': 15.0,
    'income_growth_good': 10.0,
    'income_growth_fair': 5.0,
}


class StockVectors:
    """
    Service for loading and scoring stocks using vectorized operations.
    
    Maintains a DataFrame with all required metrics for batch scoring.
    Designed for fast screening without per-stock database queries.
    """
    
    def __init__(self, db: Database):
        self.db = db
        self._df: Optional[pd.DataFrame] = None
        self._last_loaded: Optional[datetime] = None
    
    def load_vectors(self, country_filter: str = 'US') -> pd.DataFrame:
        """
        Load all stocks with their raw metrics into a DataFrame.
        
        Args:
            country_filter: Filter by country code (default 'US', None for all)
            
        Returns:
            DataFrame with columns: symbol, price, market_cap, pe_ratio, 
            debt_to_equity, dividend_yield, institutional_ownership,
            sector, company_name, country, earnings_cagr, revenue_cagr,
            income_consistency_score, revenue_consistency_score, peg_ratio
        """
        start_time = datetime.now()
        
        # Step 1: Bulk load from stock_metrics
        df = self._load_stock_metrics(country_filter)
        logger.info(f"[StockVectors] Loaded {len(df)} stocks from stock_metrics")
        
        # Step 2: Compute growth rates from earnings_history
        df = self._compute_growth_metrics(df)
        
        # Step 3: Compute P/E 52-week ranges
        df = self._compute_pe_ranges(df)
        
        # Step 3: Compute PEG ratio (pe_ratio / earnings_cagr)
        df['peg_ratio'] = df.apply(
            lambda row: row['pe_ratio'] / row['earnings_cagr'] 
            if row['pe_ratio'] and row['earnings_cagr'] and row['earnings_cagr'] > 0 
            else None, 
            axis=1
        )
        
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"[StockVectors] Load complete in {elapsed:.0f}ms")
        
        self._df = df
        self._last_loaded = datetime.now()
        return df
    
    def _load_stock_metrics(self, country_filter: str = None) -> pd.DataFrame:
        """
        Bulk load stock metrics from database.
        
        Returns DataFrame with columns from stock_metrics + stocks tables.
        """
        conn = self.db.get_connection()
        try:
            # Build query with optional country filter
            query = """
                SELECT 
                    sm.symbol,
                    sm.price,
                    sm.market_cap,
                    sm.pe_ratio,
                    sm.debt_to_equity,
                    sm.dividend_yield,
                    sm.institutional_ownership,
                    s.sector,
                    s.company_name,
                    s.country,
                    s.ipo_year
                FROM stock_metrics sm
                JOIN stocks s ON sm.symbol = s.symbol
            """
            params = []
            
            if country_filter:
                query += " WHERE s.country = %s"
                params.append(country_filter)
            
            df = pd.read_sql_query(query, conn, params=params if params else None)
            return df
            
        finally:
            self.db.return_connection(conn)
    
    def _compute_growth_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute 5Y CAGRs and consistency scores from earnings_history.
        
        Uses same formulas as EarningsAnalyzer.calculate_earnings_growth()
        to ensure parity with evaluate_stock().
        """
        # Bulk load all earnings history
        conn = self.db.get_connection()
        try:
            earnings_query = """
                SELECT symbol, year, net_income, revenue
                FROM earnings_history
                WHERE period = 'annual'
                ORDER BY symbol, year
            """
            earnings_df = pd.read_sql_query(earnings_query, conn)
        finally:
            self.db.return_connection(conn)
        
        # Initialize new columns
        df['earnings_cagr'] = None
        df['revenue_cagr'] = None
        df['income_consistency_score'] = None
        df['revenue_consistency_score'] = None
        
        # Group earnings by symbol and compute metrics
        for symbol in df['symbol'].unique():
            symbol_earnings = earnings_df[earnings_df['symbol'] == symbol].copy()
            
            if len(symbol_earnings) < 3:
                continue
            
            # Filter to valid rows (non-null net_income and revenue)
            valid_earnings = symbol_earnings[
                symbol_earnings['net_income'].notna() & 
                symbol_earnings['revenue'].notna()
            ].copy()
            
            if len(valid_earnings) < 3:
                continue
            
            # Limit to most recent 5 years
            valid_earnings = valid_earnings.sort_values('year').tail(5)
            
            net_income_values = valid_earnings['net_income'].tolist()
            revenue_values = valid_earnings['revenue'].tolist()
            years = len(valid_earnings) - 1
            
            # Calculate CAGRs using same formula as EarningsAnalyzer
            earnings_cagr = self._calculate_cagr(
                net_income_values[0], net_income_values[-1], years
            )
            revenue_cagr = self._calculate_cagr(
                revenue_values[0], revenue_values[-1], years
            )
            
            # Calculate consistency scores
            income_consistency = self._calculate_consistency(net_income_values)
            revenue_consistency = self._calculate_consistency(revenue_values)
            
            # Normalize consistency to 0-100 scale (100 = best)
            # Formula: 100 - (std_dev * 2), capped at 0
            income_consistency_score = max(0.0, 100.0 - (income_consistency * 2.0)) if income_consistency is not None else None
            revenue_consistency_score = max(0.0, 100.0 - (revenue_consistency * 2.0)) if revenue_consistency is not None else None
            
            # Update DataFrame
            mask = df['symbol'] == symbol
            df.loc[mask, 'earnings_cagr'] = earnings_cagr
            df.loc[mask, 'revenue_cagr'] = revenue_cagr
            df.loc[mask, 'income_consistency_score'] = income_consistency_score
            df.loc[mask, 'revenue_consistency_score'] = revenue_consistency_score
        
        return df
    
    def _calculate_cagr(self, start_value: float, end_value: float, years: int) -> Optional[float]:
        """
        Calculate average annual growth rate.
        
        Formula: ((end - start) / |start|) / years × 100
        
        Matches EarningsAnalyzer.calculate_cagr() exactly.
        """
        if start_value is None or end_value is None or years is None:
            return None
        if years <= 0:
            return None
        if start_value == 0:
            return None
        
        annual_growth_rate = ((end_value - start_value) / abs(start_value)) / years * 100
        return annual_growth_rate
    
    def _calculate_consistency(self, values: List[float]) -> Optional[float]:
        """
        Calculate growth consistency as standard deviation of YoY growth rates.
        
        Matches EarningsAnalyzer.calculate_growth_consistency() exactly.
        Returns raw std_dev (lower = more consistent).
        """
        if len(values) < 2:
            return None
        if values[0] is None or values[0] <= 0:
            return None
        
        growth_rates = []
        negative_year_penalty = 0
        has_negative_years = False
        
        for i in range(1, len(values)):
            if values[i] is not None and values[i-1] is not None and values[i-1] > 0:
                growth_rate = ((values[i] - values[i-1]) / values[i-1]) * 100
                growth_rates.append(growth_rate)
            
            if values[i] is not None and values[i] < 0:
                negative_year_penalty += 10
                has_negative_years = True
        
        if has_negative_years and len(growth_rates) < 3:
            return 200  # Very high std_dev = very low consistency
        
        if len(growth_rates) < 3:
            return None
        
        mean = sum(growth_rates) / len(growth_rates)
        variance = sum((x - mean) ** 2 for x in growth_rates) / len(growth_rates)
        std_dev = variance ** 0.5
        
        return std_dev + negative_year_penalty
    
    def _compute_pe_ranges(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute 52-week P/E range metrics.
        
        Mirrors LynchCriteria._calculate_pe_52_week_range logic.
        Uses weekly_prices to find min/max price over last year.
        """
        conn = self.db.get_connection()
        try:
            # Load last 52 weeks of prices (approx 1 year)
            cutoff_date = (datetime.now() - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
            query = """
                SELECT symbol, price as close_price 
                FROM weekly_prices 
                WHERE week_ending >= %s
            """
            prices_df = pd.read_sql_query(query, conn, params=(cutoff_date,))
        finally:
            self.db.return_connection(conn)
            
        if prices_df.empty:
            df['pe_52_week_min'] = None
            df['pe_52_week_max'] = None
            df['pe_52_week_position'] = None
            return df
        
        # Compute min/max price per symbol
        stats = prices_df.groupby('symbol')['close_price'].agg(['min', 'max']).reset_index()
        stats.rename(columns={'min': 'min_52w', 'max': 'max_52w'}, inplace=True)
        
        # Merge stats into main df
        df = df.merge(stats, on='symbol', how='left')
        
        # Calculate implied EPS and P/E ranges
        # implied_eps = price / pe_ratio
        
        def calculate_range_metrics(row):
            price = row.get('price')
            pe = row.get('pe_ratio')
            min_price = row.get('min_52w')
            max_price = row.get('max_52w')
            
            if pd.isna(price) or pd.isna(pe) or pd.isna(min_price) or pd.isna(max_price):
                return pd.Series([None, None, None], index=['min_pe', 'max_pe', 'position'])
                
            if pe <= 0 or price <= 0:
                 return pd.Series([None, None, None], index=['min_pe', 'max_pe', 'position'])
            
            implied_eps = price / pe
            
            pe_min = min_price / implied_eps
            pe_max = max_price / implied_eps
            
            # Position (0.0 to 1.0)
            if pe_max > pe_min:
                position = (pe - pe_min) / (pe_max - pe_min)
                # Clamp to 0-1
                position = max(0.0, min(1.0, position))
            else:
                position = None
                
            return pd.Series([pe_min, pe_max, position], index=['min_pe', 'max_pe', 'position'])

        range_metrics = df.apply(calculate_range_metrics, axis=1)
        
        df['pe_52_week_min'] = range_metrics['min_pe']
        df['pe_52_week_max'] = range_metrics['max_pe']
        df['pe_52_week_position'] = range_metrics['position']
        
        # Drop temp columns
        df.drop(columns=['min_52w', 'max_52w'], errors='ignore', inplace=True)
        
        return df

    def get_dataframe(self) -> Optional[pd.DataFrame]:

        """Return the cached DataFrame (may be None if not loaded)."""
        return self._df
    
    def get_symbols(self) -> List[str]:
        """Return list of all symbols in the cache."""
        if self._df is None:
            return []
        return self._df['symbol'].tolist()
