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
        Optimized with groupby().apply() to avoid slow loops.
        """
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
        
        # Pre-filter for valid inputs slightly speeds up groups
        mask_valid = earnings_df['net_income'].notna() & earnings_df['revenue'].notna()
        valid_df = earnings_df[mask_valid].copy()
        
        # Calculate Metrics by Group
        # We need to process each symbol's history
        
        # 1. Take last 5 years per symbol
        # sort is guaranteed by SQL, but ensure stable
        grouped_hist = valid_df.groupby('symbol').tail(5)
        
        # Define helper to apply per group (receives DataFrame chunk for one symbol)
        def calc_group_metrics(group):
            if len(group) < 3:
                return pd.Series([None, None, None, None], 
                               index=['earnings_cagr', 'revenue_cagr', 'income_consistency_score', 'revenue_consistency_score'])
            
            # Extract lists
            net_income_values = group['net_income'].tolist()
            revenue_values = group['revenue'].tolist()
            years = len(group) - 1
            
            # CAGR
            e_cagr = self._calculate_cagr(net_income_values[0], net_income_values[-1], years)
            r_cagr = self._calculate_cagr(revenue_values[0], revenue_values[-1], years)
            
            # Consistency
            inc_const = self._calculate_consistency(net_income_values)
            rev_const = self._calculate_consistency(revenue_values)
            
            # Normalize scores
            inc_score = max(0.0, 100.0 - (inc_const * 2.0)) if inc_const is not None else None
            rev_score = max(0.0, 100.0 - (rev_const * 2.0)) if rev_const is not None else None
            
            return pd.Series([e_cagr, r_cagr, inc_score, rev_score], 
                           index=['earnings_cagr', 'revenue_cagr', 'income_consistency_score', 'revenue_consistency_score'])

        # Apply calculation (this is much faster than iterating df.loc)
        metrics_df = grouped_hist.groupby('symbol').apply(calc_group_metrics)
        
        # Merge back to original DF
        # metrics_df has symbol as index
        df = df.merge(metrics_df, left_on='symbol', right_index=True, how='left')
        
        return df

    def _calculate_cagr(self, start_value: float, end_value: float, years: int) -> Optional[float]:
        """
        Calculate average annual growth rate.
        Matches EarningsAnalyzer.calculate_cagr() exactly.
        """
        if start_value is None or end_value is None or years is None:
            return None
        if years <= 0:
            return None
        if start_value == 0:
            return None
        
        try:
            annual_growth_rate = ((end_value - start_value) / abs(start_value)) / years * 100
            return annual_growth_rate
        except ZeroDivisionError:
            return None
    
    def _calculate_consistency(self, values: List[float]) -> Optional[float]:
        """
        Calculate growth consistency as standard deviation of YoY growth rates.
        Matches EarningsAnalyzer.calculate_growth_consistency() exactly.
        """
        if len(values) < 2:
            return None
        if values[0] is None or values[0] <= 0:
            return None
        
        growth_rates = []
        negative_year_penalty = 0
        has_negative_years = False
        
        for i in range(1, len(values)):
            v_curr = values[i]
            v_prev = values[i-1]
            
            if v_curr is not None and v_prev is not None and v_prev > 0:
                growth_rate = ((v_curr - v_prev) / v_prev) * 100
                growth_rates.append(growth_rate)
            
            if v_curr is not None and v_curr < 0:
                negative_year_penalty += 10
                has_negative_years = True
        
        if has_negative_years and len(growth_rates) < 3:
            return 200  # Very high std_dev = very low consistency
        
        if len(growth_rates) < 3:
            return None
        
        # Population variance to match legacy logic
        mean = sum(growth_rates) / len(growth_rates)
        variance = sum((x - mean) ** 2 for x in growth_rates) / len(growth_rates)
        std_dev = variance ** 0.5
        
        return std_dev + negative_year_penalty
    
    def _compute_pe_ranges(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute 52-week P/E range metrics using historical EPS for parity.
        
        Matches LynchCriteria logic:
        1. For each week's price, find the corresponding Annual EPS (current year or prev year).
        2. Calculate P/E for that week.
        3. Find min/max P/E over the 52-week period.
        4. Use the most recent calculated P/E for position.
        """
        conn = self.db.get_connection()
        try:
            # 1. Load Weekly Prices (last 52 weeks)
            cutoff_date = (datetime.now() - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
            prices_query = """
                SELECT symbol, week_ending, price as close_price, 
                       EXTRACT(YEAR FROM week_ending)::INT as year
                FROM weekly_prices 
                WHERE week_ending >= %s
            """
            prices_df = pd.read_sql_query(prices_query, conn, params=(cutoff_date,))
            
            # 2. Load Earnings History (Annual EPS)
            earnings_query = """
                SELECT symbol, year, earnings_per_share as eps
                FROM earnings_history
                WHERE period = 'annual' AND earnings_per_share IS NOT NULL AND earnings_per_share > 0
            """
            earnings_df = pd.read_sql_query(earnings_query, conn)
            
        finally:
            self.db.return_connection(conn)
            
        if prices_df.empty or earnings_df.empty:
            df['pe_52_week_min'] = None
            df['pe_52_week_max'] = None
            df['pe_52_week_position'] = None
            return df
        
        # 3. Merge Prices with Earnings
        # We need to match Price Year -> Earnings Year. 
        # Fallback: If no earnings for Year, use Year-1.
        
        # Merge for Current Year
        merged = prices_df.merge(
            earnings_df.rename(columns={'eps': 'eps_curr'}), 
            on=['symbol', 'year'], 
            how='left'
        )
        
        # Merge for Previous Year (Fallback)
        # To match [price_year] with [earnings_year = price_year - 1]
        # We join where earnings_year = price_year - 1
        earnings_prev = earnings_df.copy()
        earnings_prev['join_year'] = earnings_prev['year'] + 1
        
        merged = merged.merge(
            earnings_prev[['symbol', 'join_year', 'eps']].rename(columns={'eps': 'eps_prev'}),
            left_on=['symbol', 'year'],
            right_on=['symbol', 'join_year'],
            how='left'
        )
        
        # Coalesce EPS: Current -> Prev
        merged['eps_final'] = merged['eps_curr'].fillna(merged['eps_prev'])
        
        # 4. Calculate P/E per week
        # Filter valid EPS and Price
        valid_rows = (merged['eps_final'] > 0) & (merged['close_price'] > 0)
        merged = merged[valid_rows].copy()
        
        merged['weekly_pe'] = merged['close_price'] / merged['eps_final']
        
        # Filter outliers (pe < 1000) as per legacy logic
        merged = merged[merged['weekly_pe'] < 1000]
        
        if merged.empty:
            df['pe_52_week_min'] = None
            df['pe_52_week_max'] = None
            df['pe_52_week_position'] = None
            return df
            
        # 5. Aggregate logic
        # Need Min, Max, and "Latest" P/E per symbol
        
        # Group by symbol
        grouped = merged.groupby('symbol')['weekly_pe']
        
        stats = grouped.agg(['min', 'max', 'last'])
        stats.rename(columns={'min': 'pe_min', 'max': 'pe_max', 'last': 'pe_latest'}, inplace=True)
        
        # Merge stats back to main DF
        df = df.merge(stats, left_on='symbol', right_index=True, how='left')
        
        # 6. Calculate Position
        # position = (latest - min) / (max - min) * 100
        
        # Initialize
        if 'pe_min' not in df.columns: # If merge added nothing
             df['pe_52_week_min'] = None
             df['pe_52_week_max'] = None
             df['pe_52_week_position'] = None
             return df
             
        df['pe_52_week_min'] = df['pe_min']
        df['pe_52_week_max'] = df['pe_max']
        df['pe_52_week_position'] = None
        
        pe_range = df['pe_max'] - df['pe_min']
        
        # Avoid division by zero, check for valid Live PE and Range
        has_range = (pe_range > 0) & df['pe_min'].notna() & df['pe_ratio'].notna()
        
        # Vectorized calc using Live PE
        positions = (df.loc[has_range, 'pe_ratio'] - df.loc[has_range, 'pe_min']) / pe_range.loc[has_range]
        df.loc[has_range, 'pe_52_week_position'] = (positions * 100.0).clip(0.0, 100.0)
        
        # Handle single-point data (min == max) -> 50.0 default
        zero_range = (pe_range == 0) & df['pe_min'].notna()
        df.loc[zero_range, 'pe_52_week_position'] = 50.0
        
        # Cleanup
        df.drop(columns=['pe_min', 'pe_max', 'pe_latest'], errors='ignore', inplace=True)
        
        return df

    def get_dataframe(self) -> Optional[pd.DataFrame]:

        """Return the cached DataFrame (may be None if not loaded)."""
        return self._df
    
    def get_symbols(self) -> List[str]:
        """Return list of all symbols in the cache."""
        if self._df is None:
            return []
        return self._df['symbol'].tolist()
