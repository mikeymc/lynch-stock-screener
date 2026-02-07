# ABOUTME: Stock metrics tool executors for the Smart Chat Agent
# ABOUTME: Handles individual stock data retrieval including metrics, financials, ROE, margins, etc.

from typing import Dict, Any, List


class StockToolsMixin:
    """Mixin providing stock-level tool executor methods."""

    def _get_stock_metrics(self, ticker: str) -> Dict[str, Any]:
        """Get all available stock metrics including calculated growth rates."""
        ticker = ticker.upper()
        result = self.db.get_stock_metrics(ticker)
        if not result:
            return {"error": f"No data found for {ticker}"}

        # Calculate 5-year growth rates from earnings_history (matches screener behavior)
        earnings_growth = None
        revenue_growth = None
        conn = None
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            # Get last 5 years of annual data, ordered by year
            cursor.execute("""
                SELECT year, net_income, revenue
                FROM earnings_history
                WHERE symbol = %s AND period = 'annual'
                  AND net_income IS NOT NULL AND revenue IS NOT NULL
                ORDER BY year DESC
                LIMIT 5
            """, (ticker,))
            rows = cursor.fetchall()
            if len(rows) >= 3:  # Need at least 3 years for meaningful growth
                # Rows are in DESC order, reverse to get oldest first
                rows = list(reversed(rows))
                start_income, end_income = rows[0][1], rows[-1][1]
                start_revenue, end_revenue = rows[0][2], rows[-1][2]
                years = len(rows) - 1
                # Linear growth: ((end - start) / |start|) / years * 100
                if start_income and start_income != 0 and end_income:
                    earnings_growth = round(((end_income - start_income) / abs(start_income)) / years * 100, 1)
                if start_revenue and start_revenue != 0 and end_revenue:
                    revenue_growth = round(((end_revenue - start_revenue) / abs(start_revenue)) / years * 100, 1)
        except Exception:
            pass  # Growth rates will remain None
        finally:
            if conn:
                self.db.return_connection(conn)

        # Calculate PEG ratio the same way the screener does: P/E / earnings_growth
        pe_ratio = result.get("pe_ratio")
        peg_ratio = None
        if pe_ratio and earnings_growth and earnings_growth > 0:
            peg_ratio = round(pe_ratio / earnings_growth, 2)

        # Return all available metrics organized by category
        return {
            "ticker": ticker,
            "company_name": result.get("company_name"),
            "sector": result.get("sector"),
            "country": result.get("country"),
            "exchange": result.get("exchange"),
            "ipo_year": result.get("ipo_year"),
            # Current price and market data
            "price": result.get("price"),
            "market_cap": result.get("market_cap"),
            "beta": result.get("beta"),
            # Valuation ratios
            "pe_ratio": pe_ratio,
            "forward_pe": result.get("forward_pe"),
            "peg_ratio": peg_ratio,  # Calculated: P/E / earnings_growth
            "forward_peg_ratio": result.get("forward_peg_ratio"),  # From data provider
            "forward_eps": result.get("forward_eps"),
            # Growth rates (calculated from earnings_history)
            "earnings_growth": earnings_growth,
            "revenue_growth": revenue_growth,
            # Financial ratios
            "debt_to_equity": result.get("debt_to_equity"),
            "total_debt": result.get("total_debt"),
            "interest_expense": result.get("interest_expense"),
            "effective_tax_rate": result.get("effective_tax_rate"),
            "revenue": result.get("revenue"),
            # Dividends and ownership
            "dividend_yield": result.get("dividend_yield"),
            "institutional_ownership": result.get("institutional_ownership"),
            "insider_net_buying_6m": result.get("insider_net_buying_6m"),
            # Short interest
            "short_ratio": result.get("short_ratio"),
            "short_percent_float": result.get("short_percent_float"),
            # Analyst data
            "analyst_rating": result.get("analyst_rating"),
            "analyst_rating_score": result.get("analyst_rating_score"),
            "analyst_count": result.get("analyst_count"),
            "price_target_high": result.get("price_target_high"),
            "price_target_low": result.get("price_target_low"),
            "price_target_mean": result.get("price_target_mean"),
            # Dates
            "next_earnings_date": result.get("next_earnings_date"),
            "last_updated": result.get("last_updated"),
        }

    def _get_financials(self, ticker: str, metric: str, years: List[int]) -> Dict[str, Any]:
        """Get historical financial metrics."""
        ticker = ticker.upper()
        history = self.db.get_earnings_history(ticker, period_type='annual')

        if not history:
            return {"error": f"No financial history found for {ticker}"}

        # Map metric names to database field names
        metric_field_map = {
            "revenue": "revenue",
            "eps": "eps",
            "net_income": "net_income",
            "free_cash_flow": "free_cash_flow",
            "operating_cash_flow": "operating_cash_flow",
            "capital_expenditures": "capital_expenditures",
            "dividend_amount": "dividend_amount",
            "debt_to_equity": "debt_to_equity",
            "shareholder_equity": "shareholder_equity",
            "shares_outstanding": "shares_outstanding",
            "cash_and_cash_equivalents": "cash_and_cash_equivalents",
        }

        field = metric_field_map.get(metric)
        if not field:
            return {"error": f"Unknown metric: {metric}"}

        # Filter to requested years and extract metric
        result = {"ticker": ticker, "metric": metric, "data": {}}
        for entry in history:
            year = entry.get("year")
            if year in years:
                value = entry.get(field)
                result["data"][year] = value

        return result

    def _get_roe_metrics(self, ticker: str) -> Dict[str, Any]:
        """Calculate Return on Equity (ROE) metrics."""
        ticker = ticker.upper()

        # Use MetricCalculator to compute ROE
        from metric_calculator import MetricCalculator
        calc = MetricCalculator(self.db)
        roe_data = calc.calculate_roe(ticker)

        if not roe_data or not roe_data.get('roe_history'):
            return {
                "error": f"Could not calculate ROE for {ticker}",
                "suggestion": "ROE requires historical net income and shareholder equity data. Check if the stock has complete financial history."
            }

        return {
            "ticker": ticker,
            "current_roe": roe_data.get('current_roe'),
            "avg_roe_5yr": roe_data.get('avg_roe_5yr'),
            "avg_roe_10yr": roe_data.get('avg_roe_10yr'),
            "roe_history": roe_data.get('roe_history'),
            "interpretation": (
                f"Current ROE: {roe_data.get('current_roe')}%. "
                f"Buffett typically looks for ROE consistently above 15%, ideally 20%+. "
                f"5-year average: {roe_data.get('avg_roe_5yr')}%. "
                f"{'10-year average: ' + str(roe_data.get('avg_roe_10yr')) + '%.' if roe_data.get('avg_roe_10yr') else 'Insufficient data for 10-year average.'}"
            )
        }

    def _get_owner_earnings(self, ticker: str) -> Dict[str, Any]:
        """Calculate Owner Earnings (Buffett's preferred metric)."""
        ticker = ticker.upper()

        from metric_calculator import MetricCalculator
        calc = MetricCalculator(self.db)
        owner_data = calc.calculate_owner_earnings(ticker)

        if not owner_data or owner_data.get('owner_earnings') is None:
            return {
                "error": f"Could not calculate Owner Earnings for {ticker}",
                "suggestion": "Owner Earnings requires operating cash flow and capital expenditure data."
            }

        return {
            "ticker": ticker,
            "owner_earnings_millions": owner_data.get('owner_earnings'),
            "owner_earnings_per_share": owner_data.get('owner_earnings_per_share'),
            "fcf_to_owner_earnings_ratio": owner_data.get('fcf_to_owner_earnings_ratio'),
            "interpretation": (
                f"Owner Earnings: ${owner_data.get('owner_earnings')}M. "
                f"This represents the real cash the owner could extract from the business. "
                f"Buffett prefers this over accounting earnings as it accounts for maintenance capital expenditures."
            )
        }

    def _get_debt_to_earnings_ratio(self, ticker: str) -> Dict[str, Any]:
        """Calculate years to pay off debt with current earnings."""
        ticker = ticker.upper()

        from metric_calculator import MetricCalculator
        calc = MetricCalculator(self.db)
        debt_data = calc.calculate_debt_to_earnings(ticker)

        if not debt_data or debt_data.get('debt_to_earnings_years') is None:
            return {
                "error": f"Could not calculate Debt-to-Earnings for {ticker}",
                "suggestion": "Requires total debt and net income data."
            }

        years = debt_data.get('debt_to_earnings_years')
        return {
            "ticker": ticker,
            "debt_to_earnings_years": years,
            "total_debt": debt_data.get('total_debt'),
            "net_income": debt_data.get('net_income'),
            "interpretation": (
                f"It would take {years:.1f} years to pay off all debt with current earnings. "
                f"Buffett prefers companies that can pay off debt in 3-4 years or less. "
                f"{'Excellent financial strength.' if years < 3 else 'Good.' if years < 4 else 'Acceptable.' if years < 7 else 'High debt burden - risky.'}"
            )
        }

    def _get_gross_margin(self, ticker: str) -> Dict[str, Any]:
        """Calculate Gross Margin metrics."""
        ticker = ticker.upper()

        from metric_calculator import MetricCalculator
        calc = MetricCalculator(self.db)
        margin_data = calc.calculate_gross_margin(ticker)

        if not margin_data or margin_data.get('current') is None:
            return {
                "error": f"Could not calculate Gross Margin for {ticker}",
                "suggestion": "Requires revenue and gross profit data from income statement."
            }

        current = margin_data.get('current')
        avg = margin_data.get('average')
        trend = margin_data.get('trend')

        return {
            "ticker": ticker,
            "current_margin_pct": current,
            "avg_margin_5yr_pct": avg,
            "trend": trend,
            "margin_history": margin_data.get('history', []),
            "interpretation": (
                f"Current gross margin: {current}%. "
                f"5-year average: {avg}%. "
                f"Trend: {trend}. "
                f"High margins (>40-50%) indicate pricing power and a durable moat. "
                f"{'Excellent margins, suggests strong competitive advantage.' if current > 50 else 'Good margins.' if current > 40 else 'Moderate margins.' if current > 30 else 'Low margins - commodity-like business.'}"
            )
        }

    def _get_earnings_consistency(self, ticker: str) -> Dict[str, Any]:
        """Calculate earnings consistency score."""
        ticker = ticker.upper()

        from earnings_analyzer import EarningsAnalyzer
        analyzer = EarningsAnalyzer(self.db)
        growth_data = analyzer.calculate_earnings_growth(ticker)

        if not growth_data or growth_data.get('income_consistency_score') is None:
            return {
                "error": f"Could not calculate earnings consistency for {ticker}",
                "suggestion": "Requires historical earnings data with at least 3 years of data."
            }

        # Normalize consistency score to 0-100 scale (same as stock_evaluator.py)
        raw_score = growth_data.get('income_consistency_score')
        consistency_score = max(0.0, 100.0 - (raw_score * 2.0))

        return {
            "ticker": ticker,
            "consistency_score": round(consistency_score, 1),
            "raw_consistency_score": raw_score,
            "interpretation": (
                f"Earnings consistency score: {consistency_score:.1f}/100. "
                f"{'Excellent - highly predictable earnings.' if consistency_score >= 80 else 'Good - reasonably consistent.' if consistency_score >= 60 else 'Fair - some volatility.' if consistency_score >= 40 else 'Poor - highly volatile earnings.'} "
                f"Both Lynch and Buffett value predictable earnings."
            )
        }

    def _get_price_to_book_ratio(self, ticker: str) -> Dict[str, Any]:
        """Calculate Price-to-Book ratio."""
        ticker = ticker.upper()

        # Get market cap and shareholder equity
        stock_metrics = self.db.get_stock_metrics(ticker)
        if not stock_metrics:
            return {"error": f"No data found for {ticker}"}

        market_cap = stock_metrics.get('market_cap')
        if not market_cap:
            return {"error": f"Market cap not available for {ticker}"}

        # Get latest shareholder equity
        earnings_history = self.db.get_earnings_history(ticker, 'annual')
        if not earnings_history:
            return {"error": f"No financial history found for {ticker}"}

        latest = earnings_history[0]
        equity = latest.get('shareholder_equity')

        if not equity or equity <= 0:
            return {
                "error": f"Shareholder equity not available or negative for {ticker}",
                "suggestion": "P/B ratio cannot be calculated for companies with negative book value."
            }

        pb_ratio = market_cap / equity
        book_value_per_share = None

        # Calculate book value per share if we have shares outstanding
        price = stock_metrics.get('price')
        if price and price > 0:
            shares_outstanding = market_cap / price
            book_value_per_share = equity / shares_outstanding

        return {
            "ticker": ticker,
            "price_to_book_ratio": round(pb_ratio, 2),
            "market_cap": market_cap,
            "shareholder_equity": equity,
            "book_value_per_share": round(book_value_per_share, 2) if book_value_per_share else None,
            "interpretation": (
                f"Price-to-Book ratio: {pb_ratio:.2f}. "
                f"{'Low P/B - trading below book value, potential value play.' if pb_ratio < 1 else 'Reasonable valuation.' if pb_ratio < 3 else 'Premium valuation.' if pb_ratio < 5 else 'Very high P/B - investors paying significant premium to book value.'} "
                f"Buffett uses this to assess if price is reasonable relative to assets."
            )
        }

    def _get_share_buyback_activity(self, ticker: str) -> Dict[str, Any]:
        """Analyze share buyback/issuance activity over time."""
        ticker = ticker.upper()

        # Get historical shares outstanding
        earnings_history = self.db.get_earnings_history(ticker, 'annual')
        if not earnings_history:
            return {"error": f"No financial history found for {ticker}"}

        # Extract shares_outstanding by year
        shares_by_year = []
        for entry in earnings_history:
            year = entry.get('year')
            shares = entry.get('shares_outstanding')
            if year and shares:
                shares_by_year.append({'year': year, 'shares': shares})

        if len(shares_by_year) < 2:
            return {
                "error": f"Insufficient shares outstanding data for {ticker}",
                "suggestion": "Need at least 2 years of data to calculate buyback activity. Stock may need to be refreshed with force=true to fetch EDGAR data."
            }

        # Sort by year
        shares_by_year.sort(key=lambda x: x['year'])

        # Calculate year-over-year changes
        buyback_history = []
        for i in range(1, len(shares_by_year)):
            prev_year_data = shares_by_year[i-1]
            curr_year_data = shares_by_year[i]

            prev_shares = prev_year_data['shares']
            curr_shares = curr_year_data['shares']

            change_abs = curr_shares - prev_shares
            change_pct = (change_abs / prev_shares) * 100

            buyback_history.append({
                'year': curr_year_data['year'],
                'shares_outstanding': curr_shares,
                'change_from_prior_year': change_abs,
                'change_pct': round(change_pct, 2),
                'activity': 'buyback' if change_pct < 0 else 'issuance' if change_pct > 0 else 'no change'
            })

        # Calculate statistics
        buyback_years = sum(1 for h in buyback_history if h['activity'] == 'buyback')
        issuance_years = sum(1 for h in buyback_history if h['activity'] == 'issuance')
        total_change_pct = ((shares_by_year[-1]['shares'] - shares_by_year[0]['shares']) / shares_by_year[0]['shares']) * 100

        consistent_buybacks = buyback_years >= (len(buyback_history) * 0.7)  # 70%+ of years

        return {
            "ticker": ticker,
            "years_analyzed": len(buyback_history),
            "buyback_years": buyback_years,
            "issuance_years": issuance_years,
            "total_share_change_pct": round(total_change_pct, 2),
            "consistent_buybacks": consistent_buybacks,
            "buyback_history": buyback_history[-10:],  # Last 10 years
            "interpretation": (
                f"Over {len(buyback_history)} years: {buyback_years} years of buybacks, {issuance_years} years of share issuance. "
                f"Total shares outstanding {'decreased' if total_change_pct < 0 else 'increased'} by {abs(total_change_pct):.1f}%. "
                f"{'✓ Consistent buybacks - Lynch loves this!' if consistent_buybacks and total_change_pct < 0 else '⚠ Dilution detected - issuing shares reduces ownership value.' if total_change_pct > 5 else 'Neutral - minimal share count changes.'}"
            )
        }

    def _get_cash_position(self, ticker: str) -> Dict[str, Any]:
        """Get cash and cash equivalents position for a company.

        Lynch says: 'The cash position. That's the floor on the stock.'
        High cash provides downside protection and flexibility.
        """
        ticker = ticker.upper()

        # Get historical cash positions
        earnings_history = self.db.get_earnings_history(ticker)
        if not earnings_history:
            return {
                "error": f"No earnings history found for {ticker}",
                "suggestion": "Cash position data requires EDGAR filings."
            }

        # Filter for entries with cash data and sort by year
        cash_history = [
            entry for entry in earnings_history
            if entry.get('cash_and_cash_equivalents') is not None
        ]

        if not cash_history:
            return {
                "error": f"No cash position data available for {ticker}",
                "suggestion": "Cash data may need to be refreshed from EDGAR filings."
            }

        cash_history.sort(key=lambda x: x['year'])

        # Get latest cash position
        latest = cash_history[-1]
        latest_cash_dollars = latest['cash_and_cash_equivalents']
        latest_cash = latest_cash_dollars / 1_000_000  # Convert to millions
        latest_year = latest['year']

        # Build historical cash data
        cash_by_year = [
            {
                "year": entry['year'],
                "cash_millions": round(entry['cash_and_cash_equivalents'] / 1_000_000, 2),
                "period": entry.get('period', 'annual')
            }
            for entry in cash_history[-10:]  # Last 10 periods
        ]

        # Get current stock info for cash per share and cash/market cap
        conn = None
        cash_per_share = None
        cash_to_market_cap_pct = None

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # Get current price and market cap
            cursor.execute("""
                SELECT m.price, m.market_cap
                FROM stock_metrics m
                WHERE m.symbol = %s
            """, (ticker,))

            metrics_row = cursor.fetchone()
            if metrics_row:
                current_price = metrics_row[0]
                market_cap = metrics_row[1]

                # Calculate cash per share using shares outstanding
                shares_outstanding = latest.get('shares_outstanding')
                if shares_outstanding and shares_outstanding > 0:
                    cash_per_share = (latest_cash_dollars / shares_outstanding)
                elif market_cap and market_cap > 0 and current_price and current_price > 0:
                    # Fallback: estimate shares from market cap / price
                    estimated_shares = market_cap / current_price
                    cash_per_share = (latest_cash_dollars / estimated_shares)

                # Calculate cash as % of market cap
                if market_cap and market_cap > 0:
                    cash_to_market_cap_pct = (latest_cash_dollars / market_cap) * 100

        except Exception as e:
            print(f"Error calculating cash metrics: {e}")
        finally:
            if conn:
                conn.close()

        # Calculate cash trend (increasing, decreasing, stable)
        if len(cash_history) >= 3:
            recent_cash_values = [entry['cash_and_cash_equivalents'] for entry in cash_history[-3:]]
            if recent_cash_values[-1] > recent_cash_values[0] * 1.1:
                cash_trend = "increasing"
            elif recent_cash_values[-1] < recent_cash_values[0] * 0.9:
                cash_trend = "decreasing"
            else:
                cash_trend = "stable"
        else:
            cash_trend = "insufficient_data"

        # Lynch-style interpretation
        interpretation_parts = [
            f"Cash Position ({latest_year}): ${latest_cash:.0f}M."
        ]

        if cash_per_share:
            interpretation_parts.append(f"Cash per share: ${cash_per_share:.2f}.")

        if cash_to_market_cap_pct:
            if cash_to_market_cap_pct > 20:
                interpretation_parts.append(f"Cash is {cash_to_market_cap_pct:.1f}% of market cap - substantial downside protection! This is Lynch's 'floor' on the stock.")
            elif cash_to_market_cap_pct > 10:
                interpretation_parts.append(f"Cash is {cash_to_market_cap_pct:.1f}% of market cap - good downside protection.")
            else:
                interpretation_parts.append(f"Cash is {cash_to_market_cap_pct:.1f}% of market cap - moderate cash position.")

        if cash_trend == "increasing":
            interpretation_parts.append("Cash position is growing - building financial strength.")
        elif cash_trend == "decreasing":
            interpretation_parts.append("Cash position is declining - monitor for financial stress or strategic investments.")

        return {
            "ticker": ticker,
            "latest_cash_millions": round(latest_cash, 2),
            "latest_year": latest_year,
            "cash_per_share": round(cash_per_share, 2) if cash_per_share else None,
            "cash_to_market_cap_pct": round(cash_to_market_cap_pct, 2) if cash_to_market_cap_pct else None,
            "cash_trend": cash_trend,
            "cash_history": cash_by_year,
            "interpretation": " ".join(interpretation_parts)
        }
