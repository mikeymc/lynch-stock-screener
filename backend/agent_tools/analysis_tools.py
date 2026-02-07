# ABOUTME: Analysis tool executors for the Smart Chat Agent
# ABOUTME: Handles growth rates, cash flow, dividends, estimates, comparisons, and sector analysis

from typing import Dict, Any


class AnalysisToolsMixin:
    """Mixin providing analysis-oriented tool executor methods."""

    def _get_growth_rates(self, ticker: str) -> Dict[str, Any]:
        """Calculate revenue and earnings growth rates (CAGR)."""
        ticker = ticker.upper()

        earnings = self.db.get_earnings_history(ticker, period_type='annual')
        if not earnings or len(earnings) < 2:
            return {
                "error": f"Insufficient data for {ticker}",
                "suggestion": "Need at least 2 years of data to calculate growth rates."
            }

        # Sort by year descending (most recent first)
        earnings.sort(key=lambda x: x['year'], reverse=True)

        def calculate_cagr(start_val, end_val, years):
            """Calculate compound annual growth rate."""
            if not start_val or not end_val or start_val <= 0:
                return None
            return ((end_val / start_val) ** (1 / years) - 1) * 100

        # Get most recent year
        latest = earnings[0]

        # Calculate growth rates for different periods
        growth_data = {
            "ticker": ticker,
            "latest_year": latest['year'],
            "revenue_growth": {},
            "earnings_growth": {}
        }

        for period, years_back in [("1_year", 1), ("3_year", 3), ("5_year", 5)]:
            if len(earnings) > years_back:
                past = earnings[years_back]

                rev_cagr = calculate_cagr(past.get('revenue'), latest.get('revenue'), years_back)
                eps_cagr = calculate_cagr(past.get('eps'), latest.get('eps'), years_back)

                growth_data["revenue_growth"][period] = {
                    "cagr_pct": round(rev_cagr, 1) if rev_cagr else None,
                    "start_year": past['year'],
                    "end_year": latest['year']
                }
                growth_data["earnings_growth"][period] = {
                    "cagr_pct": round(eps_cagr, 1) if eps_cagr else None,
                    "start_year": past['year'],
                    "end_year": latest['year']
                }

        return growth_data

    def _get_cash_flow_analysis(self, ticker: str, years: int = 5) -> Dict[str, Any]:
        """Analyze cash flow trends over multiple years."""
        ticker = ticker.upper()

        earnings = self.db.get_earnings_history(ticker, period_type='annual')
        if not earnings:
            return {
                "error": f"No earnings history for {ticker}",
                "suggestion": "Try using get_financials for current cash flow data."
            }

        cash_flow_data = []
        current_year = 2025

        for record in earnings:
            year = record.get('year')
            if not year or year < current_year - years:
                continue

            revenue = record.get('revenue')
            ocf = record.get('operating_cash_flow')
            capex = record.get('capital_expenditures')
            fcf = record.get('free_cash_flow')

            # Calculate metrics
            fcf_margin = (fcf / revenue * 100) if fcf and revenue else None
            capex_pct = (abs(capex) / revenue * 100) if capex and revenue else None

            cash_flow_data.append({
                "year": year,
                "operating_cash_flow_b": round(ocf / 1e9, 2) if ocf else None,  # Billions
                "capital_expenditures_b": round(abs(capex) / 1e9, 2) if capex else None,
                "free_cash_flow_b": round(fcf / 1e9, 2) if fcf else None,
                "fcf_margin_pct": round(fcf_margin, 1) if fcf_margin else None,
                "capex_as_pct_revenue": round(capex_pct, 1) if capex_pct else None,
            })

        # Sort by year ascending
        cash_flow_data.sort(key=lambda x: x['year'])

        if not cash_flow_data:
            return {
                "ticker": ticker,
                "cash_flow_trends": [],
                "message": "No cash flow data available for the specified period."
            }

        return {
            "ticker": ticker,
            "years_of_data": len(cash_flow_data),
            "cash_flow_trends": cash_flow_data
        }

    def _get_dividend_analysis(self, ticker: str, years: int = 5) -> Dict[str, Any]:
        """Analyze dividend history, trends, and FCF coverage."""
        ticker = ticker.upper()

        # Get current stock metrics (price, market cap for shares calculation)
        stock_metrics = self.db.get_stock_metrics(ticker)
        current_yield = stock_metrics.get('dividend_yield') if stock_metrics else None
        price = stock_metrics.get('price') if stock_metrics else None
        market_cap = stock_metrics.get('market_cap') if stock_metrics else None

        # Calculate shares outstanding for total dividend computation
        shares_outstanding = None
        if price and market_cap and price > 0:
            shares_outstanding = market_cap / price

        # Get historical dividend data
        earnings = self.db.get_earnings_history(ticker, period_type='annual')
        if not earnings:
            return {
                "error": f"No earnings history for {ticker}",
                "suggestion": "This stock may not pay dividends or data is unavailable."
            }

        dividend_data = []
        current_year = 2026  # Updated for current year

        for record in earnings:
            year = record.get('year')
            if not year or year < current_year - years:
                continue

            dividend = record.get('dividend_amount')
            eps = record.get('eps')
            fcf = record.get('free_cash_flow')

            # Calculate payout ratio vs EPS
            eps_payout_ratio = (dividend / eps * 100) if dividend and eps and eps > 0 else None

            # Calculate payout ratio vs FCF (using total dividends)
            fcf_payout_ratio = None
            total_dividend = None
            if dividend and shares_outstanding and fcf:
                total_dividend = dividend * shares_outstanding
                if fcf > 0:
                    fcf_payout_ratio = (total_dividend / fcf) * 100

            if dividend:  # Only include years with dividend data
                entry = {
                    "year": year,
                    "dividend_per_share": round(dividend, 2),
                    "eps": round(eps, 2) if eps else None,
                    "payout_ratio_vs_eps_pct": round(eps_payout_ratio, 1) if eps_payout_ratio else None,
                }

                # Add FCF coverage data if available
                if fcf:
                    entry["free_cash_flow"] = fcf
                    entry["free_cash_flow_formatted"] = f"${fcf/1e9:.2f}B" if abs(fcf) >= 1e9 else f"${fcf/1e6:.0f}M"
                if total_dividend:
                    entry["total_dividend_paid"] = total_dividend
                    entry["total_dividend_formatted"] = f"${total_dividend/1e9:.2f}B" if total_dividend >= 1e9 else f"${total_dividend/1e6:.0f}M"
                if fcf_payout_ratio is not None:
                    entry["dividend_to_fcf_ratio_pct"] = round(fcf_payout_ratio, 1)
                elif fcf and fcf < 0:
                    entry["dividend_to_fcf_ratio_pct"] = "N/A (Negative FCF)"

                dividend_data.append(entry)

        # Sort by year ascending
        dividend_data.sort(key=lambda x: x['year'])

        if not dividend_data:
            return {
                "ticker": ticker,
                "current_yield_pct": round(current_yield, 2) if current_yield else None,
                "dividend_history": [],
                "message": "No dividend payments found in the specified period."
            }

        # Calculate dividend growth rates
        def calculate_cagr(start_val, end_val, years):
            if not start_val or not end_val or start_val <= 0:
                return None
            return ((end_val / start_val) ** (1 / years) - 1) * 100

        growth_rates = {}
        latest = dividend_data[-1]

        for period, years_back in [("1_year", 1), ("3_year", 3), ("5_year", 5)]:
            if len(dividend_data) > years_back:
                past = dividend_data[-(years_back + 1)]
                cagr = calculate_cagr(
                    past['dividend_per_share'],
                    latest['dividend_per_share'],
                    years_back
                )
                if cagr is not None:
                    growth_rates[period] = {
                        "cagr_pct": round(cagr, 1),
                        "start_year": past['year'],
                        "end_year": latest['year']
                    }

        # Add FCF coverage summary for most recent year with positive FCF
        fcf_coverage_summary = None
        for entry in reversed(dividend_data):
            if entry.get('dividend_to_fcf_ratio_pct') and isinstance(entry['dividend_to_fcf_ratio_pct'], (int, float)):
                fcf_coverage_summary = {
                    "year": entry['year'],
                    "total_dividend_paid": entry.get('total_dividend_formatted'),
                    "free_cash_flow": entry.get('free_cash_flow_formatted'),
                    "payout_ratio_pct": entry['dividend_to_fcf_ratio_pct'],
                    "assessment": "Sustainable" if entry['dividend_to_fcf_ratio_pct'] < 70 else "High" if entry['dividend_to_fcf_ratio_pct'] < 100 else "Unsustainable (>100%)"
                }
                break

        return {
            "ticker": ticker,
            "current_yield_pct": round(current_yield, 2) if current_yield else None,
            "shares_outstanding": f"{shares_outstanding/1e9:.2f}B" if shares_outstanding else None,
            "years_of_data": len(dividend_data),
            "dividend_history": dividend_data,
            "dividend_growth": growth_rates,
            "fcf_coverage_summary": fcf_coverage_summary
        }

    def _get_analyst_estimates(self, ticker: str) -> Dict[str, Any]:
        """Get analyst consensus estimates for future earnings and revenue."""
        ticker = ticker.upper()

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT period, eps_avg, eps_low, eps_high, eps_growth, eps_num_analysts,
                       revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_num_analysts
                FROM analyst_estimates
                WHERE symbol = %s
                ORDER BY period
            """, (ticker,))

            estimates = {}
            for row in cursor.fetchall():
                period = row[0]
                estimates[period] = {
                    "eps": {
                        "avg": round(row[1], 2) if row[1] else None,
                        "low": round(row[2], 2) if row[2] else None,
                        "high": round(row[3], 2) if row[3] else None,
                        "growth_pct": round(row[4], 1) if row[4] else None,
                        "num_analysts": row[5]
                    },
                    "revenue": {
                        "avg_b": round(row[6] / 1e9, 2) if row[6] else None,
                        "low_b": round(row[7] / 1e9, 2) if row[7] else None,
                        "high_b": round(row[8] / 1e9, 2) if row[8] else None,
                        "growth_pct": round(row[9], 1) if row[9] else None,
                        "num_analysts": row[10]
                    }
                }

            if not estimates:
                return {"error": f"No analyst estimates found for {ticker}"}

            return {
                "ticker": ticker,
                "estimates": estimates
            }
        finally:
            self.db.return_connection(conn)

    def _compare_stocks(self, tickers: list) -> Dict[str, Any]:
        """Compare multiple stocks side-by-side."""
        if not tickers or len(tickers) < 2:
            return {"error": "Need at least 2 tickers to compare"}
        if len(tickers) > 5:
            return {"error": "Maximum 5 stocks can be compared at once"}

        tickers = [t.upper() for t in tickers]
        comparison = {"tickers": tickers, "metrics": {}}

        # Get metrics for each stock
        for ticker in tickers:
            metrics = self.db.get_stock_metrics(ticker)
            if not metrics:
                comparison["metrics"][ticker] = {"error": "Not found"}
                continue

            comparison["metrics"][ticker] = {
                "company_name": metrics.get('company_name'),
                "sector": metrics.get('sector'),
                "price": round(metrics.get('price'), 2) if metrics.get('price') else None,
                "market_cap_b": round(metrics.get('market_cap') / 1e9, 2) if metrics.get('market_cap') else None,
                "pe_ratio": round(metrics.get('pe_ratio'), 1) if metrics.get('pe_ratio') else None,
                "forward_pe": round(metrics.get('forward_pe'), 1) if metrics.get('forward_pe') else None,
                "peg_ratio": round(metrics.get('forward_peg_ratio'), 2) if metrics.get('forward_peg_ratio') else None,
                "debt_to_equity": round(metrics.get('debt_to_equity'), 2) if metrics.get('debt_to_equity') else None,
                "dividend_yield_pct": round(metrics.get('dividend_yield'), 2) if metrics.get('dividend_yield') else None,
                "beta": round(metrics.get('beta'), 2) if metrics.get('beta') else None,
            }

        return comparison

    def _find_similar_stocks(self, ticker: str, limit: int = 5) -> Dict[str, Any]:
        """Find stocks similar to the given ticker based on sector and market cap."""
        ticker = ticker.upper()

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

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Get reference stock info
            cursor.execute("""
                SELECT s.symbol, s.company_name, s.sector, m.market_cap, m.pe_ratio
                FROM stocks s
                LEFT JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.symbol = %s
            """, (ticker,))
            ref_row = cursor.fetchone()

            if not ref_row:
                return {"error": f"Stock {ticker} not found"}

            ref_sector = ref_row[2]
            ref_market_cap = ref_row[3]

            if not ref_sector:
                return {"error": f"Sector information not available for {ticker}"}
            if not ref_market_cap:
                return {"error": f"Market cap not available for {ticker}"}

            # Find stocks in same sector with similar market cap (0.3x - 3x range)
            cursor.execute("""
                SELECT s.symbol, s.company_name, m.market_cap, m.pe_ratio,
                       m.forward_peg_ratio, m.debt_to_equity, m.dividend_yield
                FROM stocks s
                JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.sector = %s
                  AND s.symbol != %s
                  AND m.market_cap BETWEEN %s AND %s
                  AND m.pe_ratio IS NOT NULL
                ORDER BY ABS(m.market_cap - %s) ASC
                LIMIT %s
            """, (
                ref_sector,
                ticker,
                ref_market_cap * 0.3,
                ref_market_cap * 3.0,
                ref_market_cap,
                limit
            ))

            similar_stocks = []
            for row in cursor.fetchall():
                similar_stocks.append({
                    "symbol": row[0],
                    "company_name": row[1],
                    "market_cap_b": safe_round(row[2] / 1e9, 1) if row[2] else None,
                    "pe_ratio": safe_round(row[3]),
                    "peg_ratio": safe_round(row[4]),
                    "debt_to_equity": safe_round(row[5]),
                    "dividend_yield": safe_round(row[6]),
                })

            return {
                "reference_ticker": ticker,
                "reference_sector": ref_sector,
                "reference_market_cap_b": safe_round(ref_market_cap / 1e9, 1),
                "similar_stocks": similar_stocks,
                "count": len(similar_stocks)
            }
        except Exception as e:
            import traceback
            return {
                "error": f"Failed to find similar stocks for {ticker}: {str(e)}",
                "details": traceback.format_exc()
            }
        finally:
            self.db.return_connection(conn)

    def _search_company(self, company_name: str, limit: int = 5) -> Dict[str, Any]:
        """Search for companies by name using fuzzy matching."""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Use ILIKE for case-insensitive partial matching
            cursor.execute("""
                SELECT symbol, company_name, sector, exchange
                FROM stocks
                WHERE company_name ILIKE %s
                ORDER BY
                    CASE
                        WHEN company_name ILIKE %s THEN 1  -- Exact match first
                        WHEN company_name ILIKE %s THEN 2  -- Starts with
                        ELSE 3                              -- Contains
                    END,
                    company_name
                LIMIT %s
            """, (
                f'%{company_name}%',  # Contains
                company_name,          # Exact
                f'{company_name}%',   # Starts with
                limit
            ))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "ticker": row[0],
                    "company_name": row[1],
                    "sector": row[2],
                    "exchange": row[3]
                })

            if not results:
                return {
                    "error": f"No companies found matching '{company_name}'",
                    "suggestion": "Try a different spelling or use the ticker symbol directly"
                }

            return {
                "query": company_name,
                "matches": results,
                "count": len(results)
            }
        finally:
            self.db.return_connection(conn)

    def _get_sector_comparison(self, ticker: str) -> Dict[str, Any]:
        """Compare a stock's metrics to its sector averages."""
        ticker = ticker.upper()

        def safe_round(val, digits=2):
            """Safely round a value, handling None, NaN, and Decimal types."""
            if val is None:
                return None
            try:
                float_val = float(val)
                if float_val != float_val:  # NaN check
                    return None
                return round(float_val, digits)
            except (TypeError, ValueError):
                return None

        conn = None
        try:
            # Get stock details from stocks + stock_metrics tables
            stock_query = """
                SELECT s.symbol, s.company_name, s.sector,
                       m.pe_ratio, m.forward_peg_ratio, m.dividend_yield,
                       m.debt_to_equity, m.forward_pe, m.market_cap
                FROM stocks s
                LEFT JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.symbol = %s
            """
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(stock_query, (ticker,))
            stock_row = cursor.fetchone()

            if not stock_row:
                return {"error": f"Stock {ticker} not found in database"}

            company_name = stock_row[1]
            sector = stock_row[2]

            if not sector:
                return {"error": f"Sector information not available for {ticker}"}

            stock_metrics = {
                "pe_ratio": safe_round(stock_row[3]),
                "peg_ratio": safe_round(stock_row[4]),
                "dividend_yield": safe_round(stock_row[5]),
                "debt_to_equity": safe_round(stock_row[6]),
                "forward_pe": safe_round(stock_row[7]),
                "market_cap_b": safe_round(stock_row[8] / 1e9, 1) if stock_row[8] else None
            }

            # Calculate sector statistics from stock_metrics
            sector_stats_query = """
                SELECT
                    COUNT(*) as stock_count,
                    AVG(m.pe_ratio) FILTER (WHERE m.pe_ratio > 0 AND m.pe_ratio < 200) as avg_pe,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.pe_ratio)
                        FILTER (WHERE m.pe_ratio > 0 AND m.pe_ratio < 200) as median_pe,
                    AVG(m.forward_peg_ratio) FILTER (WHERE m.forward_peg_ratio > 0 AND m.forward_peg_ratio < 10) as avg_peg,
                    AVG(m.dividend_yield) FILTER (WHERE m.dividend_yield IS NOT NULL) as avg_yield,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY m.dividend_yield)
                        FILTER (WHERE m.dividend_yield IS NOT NULL) as median_yield,
                    AVG(m.debt_to_equity) FILTER (WHERE m.debt_to_equity >= 0 AND m.debt_to_equity < 50) as avg_debt_equity,
                    AVG(m.forward_pe) FILTER (WHERE m.forward_pe > 0 AND m.forward_pe < 200) as avg_forward_pe
                FROM stocks s
                JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.sector = %s AND s.symbol != %s
            """

            cursor.execute(sector_stats_query, (sector, ticker))
            stats = cursor.fetchone()

            if not stats or stats[0] < 3:
                return {
                    "ticker": ticker,
                    "company_name": company_name,
                    "sector": sector,
                    "peer_count": stats[0] if stats else 0,
                    "message": f"Only {stats[0] if stats else 0} peers found in {sector} sector. Need at least 3 for meaningful comparison.",
                    "stock_metrics": stock_metrics
                }

            # Calculate percentage differences safely
            pe_diff = None
            if stock_metrics["pe_ratio"] and stats[1]:
                try:
                    pe_diff = round((float(stock_metrics["pe_ratio"]) - float(stats[1])) / float(stats[1]) * 100, 1)
                except (TypeError, ValueError, ZeroDivisionError):
                    pe_diff = None

            return {
                "ticker": ticker,
                "company_name": company_name,
                "sector": sector,
                "peer_count": stats[0],
                "comparison": {
                    "pe_ratio": {
                        "stock": stock_metrics["pe_ratio"],
                        "sector_avg": safe_round(stats[1]),
                        "sector_median": safe_round(stats[2]),
                        "diff_percent": pe_diff
                    },
                    "peg_ratio": {
                        "stock": stock_metrics["peg_ratio"],
                        "sector_avg": safe_round(stats[3])
                    },
                    "dividend_yield": {
                        "stock": stock_metrics["dividend_yield"],
                        "sector_avg": safe_round(stats[4]),
                        "sector_median": safe_round(stats[5])
                    },
                    "debt_to_equity": {
                        "stock": stock_metrics["debt_to_equity"],
                        "sector_avg": safe_round(stats[6])
                    },
                    "forward_pe": {
                        "stock": stock_metrics["forward_pe"],
                        "sector_avg": safe_round(stats[7])
                    }
                }
            }

        except Exception as e:
            import traceback
            return {
                "error": f"Failed to get sector comparison for {ticker}: {str(e)}",
                "details": traceback.format_exc()
            }
        finally:
            if conn:
                self.db.return_connection(conn)
