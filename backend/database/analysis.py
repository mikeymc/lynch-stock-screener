# ABOUTME: AI analysis storage for stock theses, chart narratives, and DCF recommendations
# ABOUTME: Manages analyst estimates, earnings transcripts, and forward metrics

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import json

logger = logging.getLogger(__name__)



class AnalysisMixin:
    
    SYSTEM_USER_ID = 0

    def save_lynch_analysis(self, user_id: int, symbol: str, analysis_text: str, model_version: str, character_id: str = 'lynch'):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lynch_analyses
                (user_id, symbol, character_id, analysis_text, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol, character_id) DO UPDATE SET
                    analysis_text = EXCLUDED.analysis_text,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, character_id, analysis_text, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_lynch_analysis(self, user_id: int, symbol: str, character_id: Optional[str] = None, allow_fallback: bool = False) -> Optional[Dict[str, Any]]:
        if character_id is None:
            character_id = self.get_user_character(user_id)

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Try specific user first
            cursor.execute("""
                SELECT symbol, analysis_text, generated_at, model_version, character_id
                FROM lynch_analyses
                WHERE user_id = %s AND symbol = %s AND character_id = %s
            """, (user_id, symbol, character_id))
            row = cursor.fetchone()

            # Fallback to system user if allowed and not found
            if not row and allow_fallback and user_id != self.SYSTEM_USER_ID:
                cursor.execute("""
                    SELECT symbol, analysis_text, generated_at, model_version, character_id
                    FROM lynch_analyses
                    WHERE user_id = %s AND symbol = %s AND character_id = %s
                """, (self.SYSTEM_USER_ID, symbol, character_id))
                row = cursor.fetchone()

            if not row:
                return None

            return {
                'symbol': row[0],
                'analysis_text': row[1],
                'generated_at': row[2],
                'model_version': row[3],
                'character_id': row[4]
            }
        finally:
            self.return_connection(conn)

    def save_deliberation(self, user_id: int, symbol: str, deliberation_text: str, final_verdict: str, model_version: str):
        """Save or update a deliberation between Lynch and Buffett."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO deliberations
                (user_id, symbol, deliberation_text, final_verdict, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol) DO UPDATE SET
                    deliberation_text = EXCLUDED.deliberation_text,
                    final_verdict = EXCLUDED.final_verdict,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, deliberation_text, final_verdict, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_deliberation(self, user_id: int, symbol: str, allow_fallback: bool = False) -> Optional[Dict[str, Any]]:
        """Get cached deliberation for a stock."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, deliberation_text, final_verdict, generated_at, model_version
                FROM deliberations
                WHERE user_id = %s AND symbol = %s
            """, (user_id, symbol))
            row = cursor.fetchone()

            # Fallback to system user if allowed and not found
            if not row and allow_fallback and user_id != self.SYSTEM_USER_ID:
                cursor.execute("""
                    SELECT symbol, deliberation_text, final_verdict, generated_at, model_version
                    FROM deliberations
                    WHERE user_id = %s AND symbol = %s
                """, (self.SYSTEM_USER_ID, symbol))
                row = cursor.fetchone()

            if not row:
                return None

            return {
                'symbol': row[0],
                'deliberation_text': row[1],
                'final_verdict': row[2],
                'generated_at': row[3],
                'model_version': row[4]
            }
        finally:
            self.return_connection(conn)

    def get_recent_theses(self, user_id: int, days: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch the most recent investment theses for the dashboard.
        
        Args:
            user_id: User requesting the data
            days: Period window (default 1 day)
            limit: Max items to return (default 10)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Logic:
            # 1. Fetch from lynch_analyses (character generated)
            # 2. Join with stocks to get company name
            # 3. Filter by date and user (or system user if allowed)
            # 4. Order by generated_at DESC
            
            cursor.execute("""
                SELECT DISTINCT ON (a.symbol)
                    a.symbol, 
                    s.company_name, 
                    a.analysis_text, 
                    a.generated_at, 
                    a.character_id
                FROM lynch_analyses a
                JOIN stocks s ON a.symbol = s.symbol
                WHERE (a.user_id = %s OR a.user_id = %s)
                  AND a.generated_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                ORDER BY a.symbol, a.generated_at DESC
                LIMIT %s
            """, (user_id, self.SYSTEM_USER_ID, days, limit))
            
            rows = cursor.fetchall()
            
            # Re-sort by date since DISTINCT ON requires ORDER BY symbol first
            rows.sort(key=lambda x: x[3], reverse=True)
            rows = rows[:limit]
            
            results = []
            for row in rows:
                text = row[2]
                text_upper = text.upper()
                verdict = 'UNKNOWN'
                
                # Robust extraction logic (matches ThesisMixin fallback)
                if '**BUY**' in text or 'VERDICT: BUY' in text_upper:
                    verdict = 'BUY'
                elif '**WATCH**' in text or 'VERDICT: WATCH' in text_upper:
                    verdict = 'WATCH'
                elif '**AVOID**' in text or 'VERDICT: AVOID' in text_upper:
                    verdict = 'AVOID'
                else:
                    # Fallback to keyword search in first 500 chars
                    first_500 = text_upper[:500]
                    if 'BUY' in first_500 and 'AVOID' not in first_500:
                        verdict = 'BUY'
                    elif 'AVOID' in first_500:
                        verdict = 'AVOID'
                    elif 'WATCH' in first_500 or 'HOLD' in first_500:
                        verdict = 'WATCH'
                
                results.append({
                    'symbol': row[0],
                    'name': row[1],
                    'verdict': verdict,
                    'generated_at': row[3].isoformat() if row[3] else None,
                    'character_id': row[4]
                })
                
            # Also get total count for the last 24 hours for the "+n more" message
            cursor.execute("""
                SELECT COUNT(DISTINCT symbol)
                FROM lynch_analyses
                WHERE (user_id = %s OR user_id = %s)
                  AND generated_at >= CURRENT_TIMESTAMP - INTERVAL '1 day'
            """, (user_id, self.SYSTEM_USER_ID))
            total_today_count = cursor.fetchone()[0]
            
            return {
                'theses': results,
                'total_count': total_today_count
            }
        finally:
            self.return_connection(conn)

    def set_chart_analysis(self, user_id: int, symbol: str, section: str, analysis_text: str, model_version: str, character_id: str = 'lynch'):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chart_analyses
                (user_id, symbol, section, character_id, analysis_text, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol, section, character_id) DO UPDATE SET
                    analysis_text = EXCLUDED.analysis_text,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, section, character_id, analysis_text, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_chart_analysis(self, user_id: int, symbol: str, section: str, character_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if character_id is None:
            character_id = self.get_user_character(user_id)

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, section, analysis_text, generated_at, model_version, character_id
                FROM chart_analyses
                WHERE user_id = %s AND symbol = %s AND section = %s AND character_id = %s
            """, (user_id, symbol, section, character_id))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'symbol': row[0],
                'section': row[1],
                'analysis_text': row[2],
                'generated_at': row[3],
                'model_version': row[4],
                'character_id': row[5]
            }
        finally:
            self.return_connection(conn)

    def set_dcf_recommendations(self, user_id: int, symbol: str, recommendations: Dict[str, Any], model_version: str):
        """Save DCF recommendations for a user/symbol"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Store scenarios and reasoning as JSON
            recommendations_json = json.dumps(recommendations)
            cursor.execute("""
                INSERT INTO dcf_recommendations
                (user_id, symbol, recommendations_json, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol) DO UPDATE SET
                    recommendations_json = EXCLUDED.recommendations_json,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, recommendations_json, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_dcf_recommendations(self, user_id: int, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached DCF recommendations for a user/symbol"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, recommendations_json, generated_at, model_version
                FROM dcf_recommendations
                WHERE user_id = %s AND symbol = %s
            """, (user_id, symbol))
            row = cursor.fetchone()

            if not row:
                return None

            recommendations = json.loads(row[1])
            return {
                'symbol': row[0],
                'scenarios': recommendations.get('scenarios', {}),
                'reasoning': recommendations.get('reasoning', ''),
                'generated_at': row[2],
                'model_version': row[3]
            }
        finally:
            self.return_connection(conn)

    def save_earnings_transcript(self, symbol: str, transcript_data: Dict[str, Any]):
        """
        Save an earnings call transcript.

        Args:
            symbol: Stock symbol
            transcript_data: Dict containing quarter, fiscal_year, earnings_date,
                           transcript_text, has_qa, participants, source_url
        """
        sql = """
            INSERT INTO earnings_transcripts
            (symbol, quarter, fiscal_year, earnings_date, transcript_text, has_qa,
             participants, source_url, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (symbol, quarter, fiscal_year) DO UPDATE SET
                earnings_date = EXCLUDED.earnings_date,
                transcript_text = EXCLUDED.transcript_text,
                has_qa = EXCLUDED.has_qa,
                participants = EXCLUDED.participants,
                source_url = EXCLUDED.source_url,
                last_updated = NOW()
        """

        params = (
            symbol.upper(),
            transcript_data.get('quarter'),
            transcript_data.get('fiscal_year'),
            transcript_data.get('earnings_date'),
            transcript_data.get('transcript_text'),
            transcript_data.get('has_qa', False),
            transcript_data.get('participants', []),
            transcript_data.get('source_url'),
        )

        self.write_queue.put((sql, params))
        logger.info(f"Saved transcript for {symbol} {transcript_data.get('quarter')} {transcript_data.get('fiscal_year')}")

    def get_latest_earnings_transcript(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent earnings transcript for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Transcript dict or None if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, symbol, quarter, fiscal_year, earnings_date, transcript_text,
                   summary, has_qa, participants, source_url, last_updated
            FROM earnings_transcripts
            WHERE symbol = %s
            ORDER BY fiscal_year DESC, quarter DESC
            LIMIT 1
        """, (symbol.upper(),))

        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return None

        return {
            'id': row[0],
            'symbol': row[1],
            'quarter': row[2],
            'fiscal_year': row[3],
            'earnings_date': row[4].isoformat() if row[4] else None,
            'transcript_text': row[5],
            'summary': row[6],
            'has_qa': row[7],
            'participants': row[8] or [],
            'source_url': row[9],
            'last_updated': row[10].isoformat() if row[10] else None
        }

    def save_analyst_estimates(self, symbol: str, estimates_data: Dict[str, Any]):
        """
        Save analyst estimates for EPS and revenue.

        Args:
            symbol: Stock symbol
            estimates_data: Dict with period keys ('0q', '+1q', '0y', '+1y') containing:
                - eps_avg, eps_low, eps_high, eps_growth, eps_year_ago, eps_num_analysts
                - revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_year_ago, revenue_num_analysts
                - period_end_date (optional): The fiscal period end date
        """
        for period, data in estimates_data.items():
            if not data:
                continue

            sql = """
                INSERT INTO analyst_estimates
                (symbol, period, eps_avg, eps_low, eps_high, eps_growth, eps_year_ago, eps_num_analysts,
                 revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_year_ago, revenue_num_analysts,
                 period_end_date, fiscal_quarter, fiscal_year, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period) DO UPDATE SET
                    eps_avg = EXCLUDED.eps_avg,
                    eps_low = EXCLUDED.eps_low,
                    eps_high = EXCLUDED.eps_high,
                    eps_growth = EXCLUDED.eps_growth,
                    eps_year_ago = EXCLUDED.eps_year_ago,
                    eps_num_analysts = EXCLUDED.eps_num_analysts,
                    revenue_avg = EXCLUDED.revenue_avg,
                    revenue_low = EXCLUDED.revenue_low,
                    revenue_high = EXCLUDED.revenue_high,
                    revenue_growth = EXCLUDED.revenue_growth,
                    revenue_year_ago = EXCLUDED.revenue_year_ago,
                    revenue_num_analysts = EXCLUDED.revenue_num_analysts,
                    period_end_date = EXCLUDED.period_end_date,
                    fiscal_quarter = EXCLUDED.fiscal_quarter,
                    fiscal_year = EXCLUDED.fiscal_year,
                    last_updated = NOW()
            """

            params = (
                symbol.upper(),
                period,
                data.get('eps_avg'),
                data.get('eps_low'),
                data.get('eps_high'),
                data.get('eps_growth'),
                data.get('eps_year_ago'),
                data.get('eps_num_analysts'),
                data.get('revenue_avg'),
                data.get('revenue_low'),
                data.get('revenue_high'),
                data.get('revenue_growth'),
                data.get('revenue_year_ago'),
                data.get('revenue_num_analysts'),
                data.get('period_end_date'),
                data.get('fiscal_quarter'),
                data.get('fiscal_year'),
            )

            self.write_queue.put((sql, params))

    def get_analyst_estimates(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all analyst estimates for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Dict keyed by period ('0q', '+1q', '0y', '+1y') with estimate data
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT period, eps_avg, eps_low, eps_high, eps_growth, eps_year_ago, eps_num_analysts,
                       revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_year_ago,
                       revenue_num_analysts, period_end_date, fiscal_quarter, fiscal_year, last_updated
                FROM analyst_estimates
                WHERE symbol = %s
            """, (symbol.upper(),))

            rows = cursor.fetchall()

            result = {}
            for row in rows:
                result[row[0]] = {
                    'eps_avg': row[1],
                    'eps_low': row[2],
                    'eps_high': row[3],
                    'eps_growth': row[4],
                    'eps_year_ago': row[5],
                    'eps_num_analysts': row[6],
                    'revenue_avg': row[7],
                    'revenue_low': row[8],
                    'revenue_high': row[9],
                    'revenue_growth': row[10],
                    'revenue_year_ago': row[11],
                    'revenue_num_analysts': row[12],
                    'period_end_date': row[13].isoformat() if row[13] else None,
                    'fiscal_quarter': row[14],
                    'fiscal_year': row[15],
                    'last_updated': row[16].isoformat() if row[16] else None
                }

            return result
        finally:
            self.return_connection(conn)

    def save_eps_trends(self, symbol: str, trends_data: Dict[str, Any]):
        """
        Save EPS trend data showing how estimates changed over 7/30/60/90 days.

        Args:
            symbol: Stock symbol
            trends_data: Dict with period keys ('0q', '+1q', '0y', '+1y') containing:
                - current, 7daysAgo, 30daysAgo, 60daysAgo, 90daysAgo
        """
        for period, data in trends_data.items():
            if not data:
                continue

            sql = """
                INSERT INTO eps_trends
                (symbol, period, current_est, days_7_ago, days_30_ago, days_60_ago, days_90_ago, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period) DO UPDATE SET
                    current_est = EXCLUDED.current_est,
                    days_7_ago = EXCLUDED.days_7_ago,
                    days_30_ago = EXCLUDED.days_30_ago,
                    days_60_ago = EXCLUDED.days_60_ago,
                    days_90_ago = EXCLUDED.days_90_ago,
                    last_updated = NOW()
            """

            params = (
                symbol.upper(),
                period,
                data.get('current'),
                data.get('7daysAgo'),
                data.get('30daysAgo'),
                data.get('60daysAgo'),
                data.get('90daysAgo'),
            )

            self.write_queue.put((sql, params))

    def save_eps_revisions(self, symbol: str, revisions_data: Dict[str, Any]):
        """
        Save EPS revision counts (upward/downward revisions).

        Args:
            symbol: Stock symbol
            revisions_data: Dict with period keys ('0q', '+1q', '0y', '+1y') containing:
                - upLast7days, upLast30days, downLast7Days, downLast30days
        """
        for period, data in revisions_data.items():
            if not data:
                continue

            sql = """
                INSERT INTO eps_revisions
                (symbol, period, up_7d, up_30d, down_7d, down_30d, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period) DO UPDATE SET
                    up_7d = EXCLUDED.up_7d,
                    up_30d = EXCLUDED.up_30d,
                    down_7d = EXCLUDED.down_7d,
                    down_30d = EXCLUDED.down_30d,
                    last_updated = NOW()
            """

            params = (
                symbol.upper(),
                period,
                data.get('upLast7days'),
                data.get('upLast30days'),
                data.get('downLast7Days'),
                data.get('downLast30days'),
            )

            self.write_queue.put((sql, params))

    def save_growth_estimates(self, symbol: str, growth_data: Dict[str, Any]):
        """
        Save growth estimates (stock vs index comparison).

        Args:
            symbol: Stock symbol
            growth_data: Dict with period keys ('0q', '+1q', '0y', '+1y', 'LTG') containing:
                - stockTrend, indexTrend
        """
        for period, data in growth_data.items():
            if not data:
                continue

            sql = """
                INSERT INTO growth_estimates
                (symbol, period, stock_trend, index_trend, last_updated)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period) DO UPDATE SET
                    stock_trend = EXCLUDED.stock_trend,
                    index_trend = EXCLUDED.index_trend,
                    last_updated = NOW()
            """

            params = (
                symbol.upper(),
                period,
                data.get('stockTrend'),
                data.get('indexTrend'),
            )

            self.write_queue.put((sql, params))

    def save_analyst_recommendations(self, symbol: str, recommendations_data: List[Dict[str, Any]]):
        """
        Save monthly analyst buy/hold/sell distribution.

        Args:
            symbol: Stock symbol
            recommendations_data: List of dicts with:
                - period (0m, -1m, -2m, -3m), strongBuy, buy, hold, sell, strongSell
        """
        for data in recommendations_data:
            if not data:
                continue

            period = data.get('period')
            if period is None:
                continue

            sql = """
                INSERT INTO analyst_recommendations
                (symbol, period_month, strong_buy, buy, hold, sell, strong_sell, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period_month) DO UPDATE SET
                    strong_buy = EXCLUDED.strong_buy,
                    buy = EXCLUDED.buy,
                    hold = EXCLUDED.hold,
                    sell = EXCLUDED.sell,
                    strong_sell = EXCLUDED.strong_sell,
                    last_updated = NOW()
            """

            params = (
                symbol.upper(),
                period,
                data.get('strongBuy'),
                data.get('buy'),
                data.get('hold'),
                data.get('sell'),
                data.get('strongSell'),
            )

            self.write_queue.put((sql, params))

    def update_forward_metrics(self, symbol: str, forward_data: Dict[str, Any]):
        """
        Update forward metrics columns in stock_metrics table.

        Args:
            symbol: Stock symbol
            forward_data: Dict containing forward metrics from yfinance info:
                - forward_pe, forward_eps, forward_peg_ratio
                - price_target_high, price_target_low, price_target_mean, price_target_median
                - analyst_rating, analyst_rating_score, analyst_count, recommendation_key
                - earnings_growth, earnings_quarterly_growth, revenue_growth
        """
        sql = """
            UPDATE stock_metrics SET
                forward_pe = COALESCE(%s, forward_pe),
                forward_eps = COALESCE(%s, forward_eps),
                forward_peg_ratio = COALESCE(%s, forward_peg_ratio),
                price_target_high = COALESCE(%s, price_target_high),
                price_target_low = COALESCE(%s, price_target_low),
                price_target_mean = COALESCE(%s, price_target_mean),
                price_target_median = COALESCE(%s, price_target_median),
                analyst_rating = COALESCE(%s, analyst_rating),
                analyst_rating_score = COALESCE(%s, analyst_rating_score),
                analyst_count = COALESCE(%s, analyst_count),
                recommendation_key = COALESCE(%s, recommendation_key),
                earnings_growth = COALESCE(%s, earnings_growth),
                earnings_quarterly_growth = COALESCE(%s, earnings_quarterly_growth),
                revenue_growth = COALESCE(%s, revenue_growth),
                last_updated = NOW()
            WHERE symbol = %s
        """

        params = (
            forward_data.get('forward_pe'),
            forward_data.get('forward_eps'),
            forward_data.get('forward_peg_ratio'),
            forward_data.get('price_target_high'),
            forward_data.get('price_target_low'),
            forward_data.get('price_target_mean'),
            forward_data.get('price_target_median'),
            forward_data.get('analyst_rating'),
            forward_data.get('analyst_rating_score'),
            forward_data.get('analyst_count'),
            forward_data.get('recommendation_key'),
            forward_data.get('earnings_growth'),
            forward_data.get('earnings_quarterly_growth'),
            forward_data.get('revenue_growth'),
            symbol.upper(),
        )

        self.write_queue.put((sql, params))

    def get_eps_trends(self, symbol: str) -> Dict[str, Any]:
        """Get EPS trend data for a symbol."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period, current_est, days_7_ago, days_30_ago, days_60_ago, days_90_ago
                FROM eps_trends WHERE symbol = %s
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            return {
                row[0]: {
                    'current': row[1],
                    '7_days_ago': row[2],
                    '30_days_ago': row[3],
                    '60_days_ago': row[4],
                    '90_days_ago': row[5],
                } for row in rows
            }
        finally:
            self.return_connection(conn)

    def get_eps_revisions(self, symbol: str) -> Dict[str, Any]:
        """Get EPS revision data for a symbol."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period, up_7d, up_30d, down_7d, down_30d
                FROM eps_revisions WHERE symbol = %s
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            return {
                row[0]: {
                    'up_7d': row[1],
                    'up_30d': row[2],
                    'down_7d': row[3],
                    'down_30d': row[4],
                } for row in rows
            }
        finally:
            self.return_connection(conn)

    def get_growth_estimates(self, symbol: str) -> Dict[str, Any]:
        """Get growth estimate data for a symbol."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period, stock_trend, index_trend
                FROM growth_estimates WHERE symbol = %s
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            return {
                row[0]: {
                    'stock_trend': row[1],
                    'index_trend': row[2],
                } for row in rows
            }
        finally:
            self.return_connection(conn)

    def get_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        """Get analyst recommendation history for a symbol."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period_month, strong_buy, buy, hold, sell, strong_sell
                FROM analyst_recommendations
                WHERE symbol = %s
                ORDER BY period_month DESC
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            return [
                {
                    'period': row[0],
                    'strong_buy': row[1],
                    'buy': row[2],
                    'hold': row[3],
                    'sell': row[4],
                    'strong_sell': row[5],
                } for row in rows
            ]
        finally:
            self.return_connection(conn)

    def save_transcript_summary(self, symbol: str, quarter: str, fiscal_year: int, summary: str):
        """
        Save an AI-generated summary for an earnings transcript.

        Args:
            symbol: Stock symbol
            quarter: Quarter (e.g., "Q4")
            fiscal_year: Fiscal year
            summary: AI-generated summary text
        """
        sql = """
            UPDATE earnings_transcripts
            SET summary = %s, last_updated = NOW()
            WHERE symbol = %s AND quarter = %s AND fiscal_year = %s
        """
        params = (summary, symbol.upper(), quarter, fiscal_year)

        self.write_queue.put((sql, params))
        logger.info(f"Saved transcript summary for {symbol} {quarter} {fiscal_year}")

    def get_earnings_transcripts(self, symbol: str, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Get recent earnings transcripts for a symbol.

        Args:
            symbol: Stock symbol
            limit: Maximum number of transcripts to return (default 4 = 1 year)

        Returns:
            List of transcript dicts
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, symbol, quarter, fiscal_year, earnings_date, transcript_text,
                   has_qa, participants, source_url, last_updated
            FROM earnings_transcripts
            WHERE symbol = %s
            ORDER BY fiscal_year DESC, quarter DESC
            LIMIT %s
        """, (symbol.upper(), limit))

        rows = cursor.fetchall()
        self.return_connection(conn)

        return [
            {
                'id': row[0],
                'symbol': row[1],
                'quarter': row[2],
                'fiscal_year': row[3],
                'earnings_date': row[4].isoformat() if row[4] else None,
                'transcript_text': row[5],
                'has_qa': row[6],
                'participants': row[7] or [],
                'source_url': row[8],
                'last_updated': row[9].isoformat() if row[9] else None
            }
            for row in rows
        ]
