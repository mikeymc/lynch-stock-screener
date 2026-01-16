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
        
        # Step 2: Load Annual Earnings History (Used by Growth & Buffett metrics)
        earnings_df = self._load_annual_earnings(df['symbol'].tolist())
        
        # Step 3: Compute growth rates
        df = self._compute_growth_metrics(df, earnings_df)
        
        # Step 4: Compute Buffett metrics (ROE, Owner Earnings, Debt/Earnings)
        df = self._compute_buffett_metrics(df, earnings_df)

        # Step 5: Compute P/E 52-week ranges
        df = self._compute_pe_ranges(df)
        
        # Step 6: Compute PEG ratio (pe_ratio / earnings_cagr)
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

    def _load_annual_earnings(self, symbols: List[str]) -> pd.DataFrame:
        """Bulk load annual earnings history for provided symbols."""
        conn = self.db.get_connection()
        try:
            # We fetch all necessary columns for both growth and buffett metrics
            query = """
                SELECT 
                    symbol, year, net_income, revenue, 
                    operating_cash_flow, capital_expenditures
                FROM earnings_history
                WHERE period = 'annual'
                ORDER BY symbol, year
            """
            return pd.read_sql_query(query, conn)
        finally:
            self.db.return_connection(conn)
    
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
                    sm.total_debt,
                    sm.gross_margin,
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
    
    def _compute_growth_metrics(self, df: pd.DataFrame, earnings_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute 5Y CAGRs and consistency scores from earnings_history.
        Optimized with groupby().apply() to avoid slow loops.
        """
        if earnings_df.empty:
             return df
        
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
    
    def _compute_buffett_metrics(self, df: pd.DataFrame, earnings_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute Buffett-specific metrics:
        - ROE (Return on Equity)
        - Owner Earnings (OCF - Maintenance CapEx)
        - Debt to Earnings (Total Debt / Net Income)
        """
        if earnings_df.empty:
            df['roe'] = None
            df['owner_earnings'] = None
            df['debt_to_earnings'] = None
            return df

        # Get latest annual earnings (last row per symbol since it's sorted by year)
        # groupby().last() is efficient
        latest_earnings = earnings_df.groupby('symbol').last().reset_index()

        # Merge earnings data with main DF
        merged = df.merge(latest_earnings, on='symbol', how='left')

        # 1. Calculate Debt to Earnings
        # Total Debt / Net Income
        # Handle division by zero and negative income cases
        def calc_debt_to_earnings(row):
            debt = row['total_debt']
            income = row['net_income']
            
            if pd.isna(debt) or pd.isna(income) or income <= 0:
                return None
            return debt / income

        merged['debt_to_earnings'] = merged.apply(calc_debt_to_earnings, axis=1)

        # 2. Calculate Owner Earnings
        # OCF - (Abs(CapEx) * 0.7)
        # Note: CapEx is usually negative in DB, ensuring abs() handles it correctly
        def calc_owner_earnings(row):
            ocf = row['operating_cash_flow']
            capex = row['capital_expenditures']
            
            if pd.isna(ocf) or pd.isna(capex):
                return None
            
            # Estimate maintenance capex as 70% of total capex
            maintenance_capex = abs(capex) * 0.7
            return (ocf - maintenance_capex) / 1_000_000  # Convert to millions to match scalar version

        merged['owner_earnings'] = merged.apply(calc_owner_earnings, axis=1)

        # 3. Calculate ROE
        # ROE = Net Income / Equity
        # Since we don't store equity directly in stock_metrics, we derive it:
        # Equity = Total Debt / Debt_to_Equity
        # ROE = Net Income / (Total Debt / Debt_to_Equity) = (Net Income * Debt_to_Equity) / Total Debt
        def calc_roe(row):
            income = row['net_income']
            debt = row['total_debt']
            de_ratio = row['debt_to_equity']
            
            if pd.isna(income):
                return None
            
            # Case 1: We have valid debt and D/E ratio
            if pd.notna(debt) and pd.notna(de_ratio) and debt > 0 and de_ratio > 0:
                equity = debt / de_ratio
                return (income / equity) * 100
            
            # Case 2: Debt is 0. 
            # If Debt is 0, D/E is 0. We can't derive equity from this.
            # However, high quality companies often have low debt.
            # We are stuck without direct Equity data.
            # For now, return None. 
            # TODO: Add 'shareholder_equity' to stock_metrics in future migration
            return None

        merged['roe'] = merged.apply(calc_roe, axis=1)

        # Update columns in original DF
        df['roe'] = merged['roe']
        df['owner_earnings'] = merged['owner_earnings']
        df['debt_to_earnings'] = merged['debt_to_earnings']

        return df

    def _compute_pe_ranges(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute 52-week P/E range metrics using Quarterly TTM EPS (Vectorized).
        
        Logic:
        1. Fetch all weekly prices (last 52 weeks).
        2. Fetch all quarterly net income.
        3. Compute Rolling TTM Net Income (Sum of last 4 quarters) for each symbol-date.
        4. Merge TTM NI onto Weekly Prices using merge_asof (backward fill).
        5. Calculate Shares Outstanding from current MarketCap/Price (assumed valid for Adjusted Prices).
        6. Calculate Weekly PE = WeeklyPrice / (TTM_NI / Shares).
        7. Agg Min/Max.
        8. Compare against Live P/E (pe_ratio column) for position.
        """
        conn = self.db.get_connection()
        try:
            # 1. Load Weekly Prices (last 52 weeks) 
            cutoff_date = (datetime.now() - pd.Timedelta(weeks=52)).strftime('%Y-%m-%d')
            prices_query = """
                SELECT symbol, week_ending, price as close_price
                FROM weekly_prices 
                WHERE week_ending >= %s
                ORDER BY symbol, week_ending
            """
            prices_df = pd.read_sql_query(prices_query, conn, params=(cutoff_date,))
            
            # 2. Load Quarterly Net Income (fetch enough history for rolling sum)
            # Fetching last 15 years to ensure we capture stocks with stale data (e.g. RBB last updated 2019)
            cutoff_earnings = (datetime.now() - pd.Timedelta(weeks=15*52)).strftime('%Y-%m-%d')
            earnings_query = """
                SELECT symbol, fiscal_end, net_income
                FROM earnings_history
                WHERE period IN ('Q1', 'Q2', 'Q3', 'Q4') 
                  AND net_income IS NOT NULL
                  AND fiscal_end >= %s
                ORDER BY symbol, fiscal_end
            """
            earnings_df = pd.read_sql_query(earnings_query, conn, params=(cutoff_earnings,))
            
        finally:
            self.db.return_connection(conn)
            
        if prices_df.empty or earnings_df.empty:
            df['pe_52_week_min'] = None
            df['pe_52_week_max'] = None
            df['pe_52_week_position'] = None
            return df
            
        # 3. Compute TTM Net Income
        # Needs to be sorted by symbol, fiscal_end
        earnings_df['fiscal_end'] = pd.to_datetime(earnings_df['fiscal_end'])
        
        # Calculate Rolling 4Q Sum
        # Groupby preserves order if sort=False, but we already sorted in SQL
        earnings_df['ttm_net_income'] = (
            earnings_df.groupby('symbol')['net_income']
            .rolling(4, min_periods=4)
            .sum()
            .reset_index(0, drop=True)
        )
        
        # Drop rows with NaN TTM (first 3 quarters)
        ttm_df = earnings_df.dropna(subset=['ttm_net_income']).copy()
        
        # 4. Merge TTM NI onto Weekly Prices
        # Ensure key types match
        prices_df['week_ending'] = pd.to_datetime(prices_df['week_ending'])
        
        # merge_asof requires sorting
        prices_df = prices_df.sort_values(['week_ending'])
        ttm_df = ttm_df.sort_values(['fiscal_end'])
        
        # Perform merge_asof
        # For each price date, find the latest TTM NI on or before that date
        merged = pd.merge_asof(
            prices_df,
            ttm_df[['symbol', 'fiscal_end', 'ttm_net_income']],
            left_on='week_ending',
            right_on='fiscal_end',
            by='symbol',
            direction='backward'
        )
        
        # 5. Calculate Shares Outstanding (Current)
        # Using current MarketCap / Price. Assume df has these columns.
        # Create a mapping dataframe
        shares_map = df[['symbol', 'market_cap', 'price']].copy()
        shares_map['shares'] = shares_map['market_cap'] / shares_map['price']
        
        # Fill Inf/NaN
        shares_map['shares'] = shares_map['shares'].replace([np.inf, -np.inf], np.nan)
        
        # Merge Shares onto Merged Data
        merged = merged.merge(shares_map[['symbol', 'shares']], on='symbol', how='inner')
        
        # 6. Calculate Weekly PE
        # Avoid division by zero
        valid_rows = (merged['shares'] > 0) & (merged['ttm_net_income'] > 0) & (merged['close_price'] > 0)
        calc_df = merged[valid_rows].copy()
        
        calc_df['ttm_eps'] = calc_df['ttm_net_income'] / calc_df['shares']
        calc_df['weekly_pe'] = calc_df['close_price'] / calc_df['ttm_eps']
        
        # Filter Outliers (< 1000)
        calc_df = calc_df[calc_df['weekly_pe'] < 1000]
        
        if calc_df.empty:
            df['pe_52_week_min'] = None
            df['pe_52_week_max'] = None
            df['pe_52_week_position'] = None
            return df
            
        # 7. Aggregate Min/Max
        stats = calc_df.groupby('symbol')['weekly_pe'].agg(['min', 'max'])
        stats.rename(columns={'min': 'pe_min', 'max': 'pe_max'}, inplace=True)
        
        # Merge back to Main DF
        df = df.merge(stats, left_on='symbol', right_index=True, how='left')
        
        # 8. Calculate Position
        df['pe_52_week_min'] = df['pe_min']
        df['pe_52_week_max'] = df['pe_max']
        df['pe_52_week_position'] = None
        
        pe_range = df['pe_max'] - df['pe_min']
        has_range = (pe_range > 0) & df['pe_min'].notna() & df['pe_ratio'].notna()
        
        # Vectorized Position Check
        if has_range.any():
            current_pe = df.loc[has_range, 'pe_ratio']
            pe_min = df.loc[has_range, 'pe_min']
            pe_max = df.loc[has_range, 'pe_max']
            
            # Cases: < Min (0), > Max (100), Inside
            # We can calculate raw percent and clamp
            raw_pos = (current_pe - pe_min) / (pe_max - pe_min) * 100.0
            
            # Apply clamp logic:
            # If current < min -> 0
            # If current > max -> 100
            # Implicitly handled by clip(0, 100)
            df.loc[has_range, 'pe_52_week_position'] = raw_pos.clip(0.0, 100.0)
            
        # Zero range case
        zero_range = (pe_range == 0) & df['pe_min'].notna()
        df.loc[zero_range, 'pe_52_week_position'] = 50.0
        
        # Cleanup
        df.drop(columns=['pe_min', 'pe_max'], inplace=True, errors='ignore')

        return df

    def get_dataframe(self) -> Optional[pd.DataFrame]:

        """Return the cached DataFrame (may be None if not loaded)."""
        return self._df
    
    def get_symbols(self) -> List[str]:
        """Return list of all symbols in the cache."""
        if self._df is None:
            return []
        return self._df['symbol'].tolist()
