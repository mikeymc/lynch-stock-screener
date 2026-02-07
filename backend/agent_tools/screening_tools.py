# ABOUTME: Stock screening tool executors for the Smart Chat Agent
# ABOUTME: Handles earnings history queries and multi-criteria stock screening

from typing import Dict, Any


class ScreeningToolsMixin:
    """Mixin providing stock screening tool executor methods."""

    def _get_earnings_history(self, ticker: str, period_type: str = "quarterly", limit: int = 12) -> Dict[str, Any]:
        """Get historical earnings and revenue data."""
        ticker = ticker.upper()
        limit = min(limit or 12, 40)

        conditions = ["symbol = %s"]
        params = [ticker]

        if period_type == "quarterly":
            conditions.append("period != 'annual'")
        elif period_type == "annual":
            conditions.append("period = 'annual'")

        where_clause = " AND ".join(conditions)

        # Sort by year descending, then period (Annual > Q4 > Q3 > Q2 > Q1)
        # Note: We treat 'annual' as coming after Q4 of the same year
        order_case = """
            CASE period
                WHEN 'annual' THEN 5
                WHEN 'Q4' THEN 4
                WHEN 'Q3' THEN 3
                WHEN 'Q2' THEN 2
                WHEN 'Q1' THEN 1
                ELSE 0
            END DESC
        """
        query = f"""
            SELECT
                year, period, earnings_per_share, revenue, net_income,
                free_cash_flow, operating_cash_flow, capital_expenditures
            FROM earnings_history
            WHERE {where_clause}
            ORDER BY year DESC, {order_case}
            LIMIT %s
        """
        params.append(limit)

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))

            history = []
            for row in cursor.fetchall():
                # Only include rows with meaningful data
                if row[2] is None and row[3] is None and row[4] is None:
                    continue

                history.append({
                    "year": row[0],
                    "period": row[1],
                    "eps": float(row[2]) if row[2] is not None else None,
                    "revenue": float(row[3]) if row[3] is not None else None,
                    "net_income": float(row[4]) if row[4] is not None else None,
                    "free_cash_flow": float(row[5]) if row[5] is not None else None,
                    "operating_cash_flow": float(row[6]) if row[6] is not None else None,
                    "capex": float(row[7]) if row[7] is not None else None
                })

            if not history:
                return {
                    "ticker": ticker,
                    "message": "No earnings history found."
                }

            # Check if quarterly FCF is all null - if so, fetch annual FCF for context
            annual_fcf_context = None
            if period_type == "quarterly":
                has_quarterly_fcf = any(h.get("free_cash_flow") is not None for h in history)
                if not has_quarterly_fcf:
                    # Fetch latest annual FCF for context
                    cursor.execute("""
                        SELECT year, free_cash_flow, operating_cash_flow, capital_expenditures
                        FROM earnings_history
                        WHERE symbol = %s AND period = 'annual' AND free_cash_flow IS NOT NULL
                        ORDER BY year DESC
                        LIMIT 2
                    """, (ticker,))
                    annual_rows = cursor.fetchall()
                    if annual_rows:
                        annual_fcf_context = [
                            {
                                "year": r[0],
                                "free_cash_flow": float(r[1]) if r[1] else None,
                                "operating_cash_flow": float(r[2]) if r[2] else None,
                                "capex": float(r[3]) if r[3] else None
                            }
                            for r in annual_rows
                        ]

            result = {
                "ticker": ticker,
                "period_type": period_type,
                "count": len(history),
                "history": history
            }

            if annual_fcf_context:
                result["annual_fcf_context"] = annual_fcf_context
                result["note"] = "Quarterly Free Cash Flow data is unavailable. Annual FCF provided for context."

            return result
        finally:
            self.db.return_connection(conn)

    def _screen_stocks(
        self,
        pe_max: float = None,
        pe_min: float = None,
        forward_pe_max: float = None,
        forward_pe_min: float = None,
        dividend_yield_min: float = None,
        market_cap_min: float = None,
        market_cap_max: float = None,
        revenue_growth_min: float = None,
        eps_growth_min: float = None,
        short_interest_min: float = None,
        analyst_rating_min: float = None,
        analyst_upside_min: float = None,
        revisions_up_min: int = None,
        revisions_down_min: int = None,
        sector: str = None,
        peg_max: float = None,
        peg_min: float = None,
        debt_to_equity_max: float = None,
        profit_margin_min: float = None,
        target_upside_min: float = None,
        has_transcript: bool = None,
        has_fcf: bool = None,
        has_recent_insider_activity: bool = None,
        sort_by: str = "market_cap",
        sort_order: str = "desc",
        top_n_by_market_cap: int = None,
        limit: int = 20,
        exclude_tickers: list = None
    ) -> Dict[str, Any]:
        """Screen stocks based on various criteria."""

        def safe_round(val, digits=2):
            if val is None:
                return None
            try:
                float_val = float(val)
                if float_val != float_val:
                    return None
                return round(float_val, digits)
            except (TypeError, ValueError):
                return None

        # Cap limit at 50
        limit = min(limit or 20, 50)

        # Build dynamic WHERE clause
        conditions = []
        params = []

        # Track if we need growth CTE or Revisions Join
        needs_growth_cte = (revenue_growth_min is not None or eps_growth_min is not None or
                           sort_by in ('revenue_growth', 'eps_growth'))

        needs_revisions_join = (revisions_up_min is not None or revisions_down_min is not None or
                               sort_by in ('revisions_up', 'revisions_down'))

        # Exclude tickers
        if exclude_tickers:
            excluded = [t.upper() for t in exclude_tickers if isinstance(t, str)]
            if excluded:
                placeholders = ', '.join(['%s'] * len(excluded))
                conditions.append(f"s.symbol NOT IN ({placeholders})")
                params.extend(excluded)

        # P/E filters
        if pe_max is not None:
            conditions.append("m.pe_ratio <= %s")
            params.append(pe_max)
        if pe_min is not None:
            conditions.append("m.pe_ratio >= %s")
            params.append(pe_min)

        # Forward P/E filters
        if forward_pe_max is not None:
            conditions.append("m.forward_pe <= %s")
            params.append(forward_pe_max)
        if forward_pe_min is not None:
            conditions.append("m.forward_pe >= %s")
            params.append(forward_pe_min)

        # Dividend yield filter
        if dividend_yield_min is not None:
            conditions.append("m.dividend_yield >= %s")
            params.append(dividend_yield_min)

        # Market cap filters (convert billions to actual value)
        if market_cap_min is not None:
            conditions.append("m.market_cap >= %s")
            params.append(market_cap_min * 1_000_000_000)
        if market_cap_max is not None:
            conditions.append("m.market_cap <= %s")
            params.append(market_cap_max * 1_000_000_000)

        # Growth filters (calculated from earnings_history)
        if revenue_growth_min is not None:
            conditions.append("g.revenue_growth >= %s")
            params.append(revenue_growth_min)
        if eps_growth_min is not None:
            conditions.append("g.eps_growth >= %s")
            params.append(eps_growth_min)

        # Short Interest Filter (m.short_percent_float is e.g. 0.15 for 15%)
        # Tool input is expected as percentage (e.g. 15 for 15%)
        if short_interest_min is not None:
            conditions.append("m.short_percent_float >= %s")
            params.append(short_interest_min / 100.0)

        # Analyst Rating (1.0 = Strong Buy, 5.0 = Sell)
        # "Better" rating means LOWER score.
        # If user asks for "rating < 2.0" (better than Buy), we use the input directly.
        if analyst_rating_min is not None:
            conditions.append("m.analyst_rating_score <= %s")
            params.append(analyst_rating_min)

        # Analyst Upside (Using target_mean_price vs current price)
        # Implementation: (price_target_mean - price) / price
        if analyst_upside_min is not None or target_upside_min is not None:
             # Merge the two params if both provided (prefer analyst_upside_min)
             min_upside = analyst_upside_min if analyst_upside_min is not None else target_upside_min
             conditions.append("""
                 (m.price_target_mean > 0 AND m.price > 0 AND
                  ((m.price_target_mean - m.price) / m.price) * 100 >= %s)
             """)
             params.append(min_upside)

        # Revision Filters
        if revisions_up_min is not None:
            conditions.append("r.up_30d >= %s")
            params.append(revisions_up_min)
        if revisions_down_min is not None:
            conditions.append("r.down_30d >= %s")
            params.append(revisions_down_min)

        # Sector filter with aliasing for common synonyms
        if sector:
            sector_lower = sector.lower().strip()
            if 'financ' in sector_lower:
                conditions.append("(LOWER(s.sector) = 'finance' OR LOWER(s.sector) = 'financial services')")
            else:
                conditions.append("LOWER(s.sector) LIKE LOWER(%s)")
                params.append(f"%{sector}%")

        # PEG filter (using forward_peg_ratio from stock_metrics)
        if peg_max is not None:
            conditions.append("m.forward_peg_ratio <= %s")
            params.append(peg_max)
        if peg_min is not None:
            conditions.append("m.forward_peg_ratio >= %s")
            params.append(peg_min)

        # Debt to equity filter
        if debt_to_equity_max is not None:
            conditions.append("m.debt_to_equity <= %s")
            params.append(debt_to_equity_max)

        # Profit margin filter
        if profit_margin_min is not None:
            conditions.append("m.profit_margin >= %s")
            params.append(profit_margin_min)

        # Transcript filter
        if has_transcript:
            conditions.append("""EXISTS (
                SELECT 1 FROM earnings_transcripts et
                WHERE et.symbol = s.symbol
                AND et.transcript_text IS NOT NULL
                AND LENGTH(et.transcript_text) > 100
            )""")

        # FCF filter
        if has_fcf:
            conditions.append("""EXISTS (
                SELECT 1 FROM earnings_history eh
                WHERE eh.symbol = s.symbol
                AND eh.free_cash_flow IS NOT NULL
                AND eh.free_cash_flow > 0
            )""")

        # Insider Activity Filter
        if has_recent_insider_activity:
            conditions.append("""EXISTS (
                SELECT 1 FROM insider_trades it
                WHERE it.symbol = s.symbol
                AND (it.transaction_type = 'Buy' OR it.transaction_type = 'Purchase')
                AND it.transaction_date >= (CURRENT_DATE - INTERVAL '90 days')
            )""")

        # Profit Margin Filter
        join_clause = ""
        if profit_margin_min is not None:
            join_clause = """
                JOIN (
                    SELECT DISTINCT ON (symbol) symbol, net_income, revenue
                    FROM earnings_history
                    WHERE period='annual' AND revenue > 0
                    ORDER BY symbol, year DESC
                ) eh ON s.symbol = eh.symbol
            """
            conditions.append("(eh.net_income::float / eh.revenue::float * 100) >= %s")
            params.append(profit_margin_min)

        # Target Upside Filter
        if target_upside_min is not None:
            conditions.append("""
                m.price > 0
                AND m.price_target_mean IS NOT NULL
                AND ((m.price_target_mean - m.price) / m.price * 100) >= %s
            """)
            params.append(target_upside_min)

        # Always require valid P/E and market cap
        conditions.append("m.pe_ratio IS NOT NULL")
        conditions.append("m.pe_ratio > 0")
        conditions.append("m.market_cap > 0")

        # Ensure company has quarterly earnings history
        conditions.append("""EXISTS (
            SELECT 1 FROM earnings_history eh
            WHERE eh.symbol = s.symbol
            AND eh.period != 'annual'
            AND eh.net_income IS NOT NULL
        )""")

        query_conditions = " AND ".join(conditions) if conditions else "1=1"

        # Build ORDER BY clause
        sort_columns = {
            "pe": "m.pe_ratio",
            "forward_pe": "m.forward_pe",
            "dividend_yield": "m.dividend_yield",
            "market_cap": "m.market_cap",
            "revenue_growth": "g.revenue_growth",
            "eps_growth": "g.eps_growth",
            "peg": "m.forward_peg_ratio",
            "debt_to_equity": "m.debt_to_equity",
            "target_upside": "((m.price_target_mean - m.price) / m.price)",
            "short_percent_float": "m.short_percent_float",
            "analyst_rating_score": "m.analyst_rating_score",
            "revisions_up": "r.up_30d",
            "revisions_down": "r.down_30d"
        }
        order_col = sort_columns.get(sort_by, "m.market_cap")

        # Determine sort order
        order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"
        null_handling = "NULLS LAST" if order_dir == "DESC" else "NULLS FIRST"

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Base tables
            tables_clause = "stocks s JOIN stock_metrics m ON s.symbol = m.SYMBOL"

            # Add joins if needed
            if needs_revisions_join:
                # Revisions table is keyed by symbol and period='0q' (current quarter) usually
                # We'll Left Join explicitly
                tables_clause += " LEFT JOIN eps_revisions r ON s.symbol = r.symbol AND r.period = '0q'"

            # Construct Query
            # Note: We select many fields for context
            select_fields = """
                s.symbol, s.company_name, s.sector,
                m.price, m.market_cap, m.pe_ratio, m.forward_pe, m.dividend_yield,
                m.forward_peg_ratio, m.debt_to_equity,
                m.analyst_rating_score, m.price_target_mean, m.short_percent_float
            """

            # Add revision fields if joined
            if needs_revisions_join:
                select_fields += ", r.up_30d, r.down_30d"
            else:
                select_fields += ", NULL as up_30d, NULL as down_30d"

            if needs_growth_cte:
                # CTE to calculate CAGR from earnings history
                # (This is expensive, so only do it if requested)
                query = f"""
                    WITH growth_metrics AS (
                        SELECT
                            h.symbol,
                            (POWER(MAX(h.revenue) / NULLIF(MIN(h.revenue), 0), 1.0/NULLIF(COUNT(*)-1, 0)) - 1) * 100 as revenue_growth,
                            (POWER(MAX(h.eps) / NULLIF(MIN(h.eps), 0), 1.0/NULLIF(COUNT(*)-1, 0)) - 1) * 100 as eps_growth
                        FROM earnings_history h
                        WHERE h.period_type = 'annual'
                        AND h.year >= (EXTRACT(YEAR FROM CURRENT_DATE) - 5)
                        GROUP BY h.symbol
                        HAVING COUNT(*) >= 4
                    )
                    SELECT {select_fields}, g.revenue_growth, g.eps_growth
                    FROM {tables_clause}
                    LEFT JOIN growth_metrics g ON s.symbol = g.symbol
                    WHERE {query_conditions}
                    ORDER BY {order_col} {order_dir} {null_handling}
                    LIMIT %s
                """
            else:
                # No growth CTE needed
                query = f"""
                    SELECT {select_fields}, NULL as revenue_growth, NULL as eps_growth
                    FROM {tables_clause}
                    WHERE {query_conditions}
                    ORDER BY {order_col} {order_dir} {null_handling}
                    LIMIT %s
                """

            params.append(limit)

            # Execute
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()

            results = []
            for row in rows:
                # Unpack row
                (symbol, name, sector, price, mcap, pe, fwd_pe, div_yield,
                 peg, de, rating_score, target_mean,
                 short_float, up_30d, down_30d, rev_growth, eps_growth) = row

                # Calculate specific return fields
                upside = None
                if target_mean and price:
                    upside = ((target_mean - price) / price) * 100

                # Format market cap
                if mcap:
                    if mcap >= 1_000_000_000_000:
                        mcap_str = f"${mcap / 1_000_000_000_000:.1f}T"
                    elif mcap >= 1_000_000_000:
                        mcap_str = f"${mcap / 1_000_000_000:.1f}B"
                    else:
                        mcap_str = f"${mcap / 1_000_000:.0f}M"
                else:
                    mcap_str = "N/A"

                entry = {
                    "symbol": symbol,
                    "company_name": name,
                    "sector": sector,
                    "market_cap": mcap_str,
                    "price": safe_round(price),
                    "pe_ratio": safe_round(pe),
                    "forward_pe": safe_round(fwd_pe),
                    "dividend_yield": safe_round(div_yield),
                    "peg_ratio": safe_round(peg),
                    "debt_to_equity": safe_round(de),
                    "gross_margin": None,
                    "short_interest_pct": safe_round(short_float * 100) if short_float else None,
                    "analyst_rating": safe_round(rating_score, 1) if rating_score is not None else None,
                    "target_upside": safe_round(upside, 1),
                    "revisions_up_30d": up_30d,
                    "revisions_down_30d": down_30d
                }

                # Add conditional fields
                if rev_growth is not None:
                    entry["revenue_growth"] = safe_round(rev_growth, 1)
                if eps_growth is not None:
                    entry["eps_growth"] = safe_round(eps_growth, 1)

                results.append(entry)

            # Build filter summary
            filters_applied = []
            if pe_max is not None:
                filters_applied.append(f"P/E <= {pe_max}")
            if pe_min is not None:
                filters_applied.append(f"P/E >= {pe_min}")
            if forward_pe_max is not None:
                filters_applied.append(f"Fwd P/E <= {forward_pe_max}")
            if forward_pe_min is not None:
                filters_applied.append(f"Fwd P/E >= {forward_pe_min}")
            if dividend_yield_min is not None:
                filters_applied.append(f"Div Yield >= {dividend_yield_min}%")
            if market_cap_min is not None:
                filters_applied.append(f"Market Cap >= ${market_cap_min}B")
            if market_cap_max is not None:
                filters_applied.append(f"Market Cap <= ${market_cap_max}B")
            if revenue_growth_min is not None:
                filters_applied.append(f"Revenue Growth >= {revenue_growth_min}%")
            if eps_growth_min is not None:
                filters_applied.append(f"EPS Growth >= {eps_growth_min}%")
            if short_interest_min is not None:
                filters_applied.append(f"Short Interest >= {short_interest_min}%")
            if analyst_rating_min is not None:
                filters_applied.append(f"Rating <= {analyst_rating_min}")
            if analyst_upside_min is not None:
                filters_applied.append(f"Upside >= {analyst_upside_min}%")
            if revisions_up_min is not None:
                filters_applied.append(f"Up Revisions >= {revisions_up_min}")
            if revisions_down_min is not None:
                filters_applied.append(f"Down Revisions >= {revisions_down_min}")
            if sector:
                filters_applied.append(f"Sector: {sector}")
            if peg_max is not None:
                filters_applied.append(f"PEG <= {peg_max}")
            if target_upside_min is not None:
                filters_applied.append(f"Target Upside >= {target_upside_min}%")

            return {
                "filters_applied": filters_applied if filters_applied else ["None (showing all stocks)"],
                "sort": f"{sort_by} {sort_order}",
                "count": len(results),
                "stocks": results
            }
        except Exception as e:
            import traceback
            return {
                "error": f"Failed to screen stocks: {str(e)}",
                "details": traceback.format_exc()
            }
        finally:
            self.db.return_connection(conn)
