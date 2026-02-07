# ABOUTME: Research tool executors for the Smart Chat Agent
# ABOUTME: Handles peers, insider activity, news, filings, transcripts, price history, and P/E analysis

from typing import Dict, Any


class ResearchToolsMixin:
    """Mixin providing research-oriented tool executor methods."""

    def _get_peers(self, ticker: str, limit: int = 10) -> Dict[str, Any]:
        """Get peer companies in the same sector with their financial metrics."""
        ticker = ticker.upper()
        limit = min(limit or 10, 25)

        def safe_round(val, digits=2):
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
            # Get target stock info from stocks + stock_metrics tables
            target_query = """
                SELECT s.symbol, s.company_name, s.sector,
                       m.price, m.pe_ratio, m.market_cap, m.debt_to_equity,
                       m.dividend_yield, m.forward_pe, m.forward_peg_ratio
                FROM stocks s
                LEFT JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.symbol = %s
            """
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(target_query, (ticker,))
            target_row = cursor.fetchone()

            if not target_row:
                return {"error": f"Stock {ticker} not found in database"}

            sector = target_row[2]

            if not sector:
                return {"error": f"Sector information not available for {ticker}"}

            target_market_cap = target_row[5]
            target_metrics = {
                "symbol": target_row[0],
                "company_name": target_row[1],
                "sector": sector,
                "price": safe_round(target_row[3]),
                "pe_ratio": safe_round(target_row[4]),
                "market_cap_b": safe_round(target_row[5] / 1e9, 1) if target_row[5] else None,
                "debt_to_equity": safe_round(target_row[6]),
                "dividend_yield": safe_round(target_row[7]),
                "forward_pe": safe_round(target_row[8]),
                "forward_peg": safe_round(target_row[9])
            }

            # Find peers in the same sector with valid metrics
            # Order by market cap proximity to target
            peers_query = """
                SELECT s.symbol, s.company_name,
                       m.price, m.pe_ratio, m.market_cap, m.debt_to_equity,
                       m.dividend_yield, m.forward_pe, m.forward_peg_ratio
                FROM stocks s
                JOIN stock_metrics m ON s.symbol = m.symbol
                WHERE s.sector = %s
                  AND s.symbol != %s
                  AND m.market_cap IS NOT NULL
                  AND m.pe_ratio IS NOT NULL
                ORDER BY ABS(m.market_cap - COALESCE(%s, 0)) ASC
                LIMIT %s
            """
            cursor.execute(peers_query, (sector, ticker, target_market_cap, limit))
            peer_rows = cursor.fetchall()

            if not peer_rows:
                return {
                    "ticker": ticker,
                    "target": target_metrics,
                    "peers": [],
                    "message": f"No peers found in {sector} sector"
                }

            peers = []
            for row in peer_rows:
                peers.append({
                    "symbol": row[0],
                    "company_name": row[1],
                    "price": safe_round(row[2]),
                    "pe_ratio": safe_round(row[3]),
                    "market_cap_b": safe_round(row[4] / 1e9, 1) if row[4] else None,
                    "debt_to_equity": safe_round(row[5]),
                    "dividend_yield": safe_round(row[6]),
                    "forward_pe": safe_round(row[7]),
                    "forward_peg": safe_round(row[8])
                })

            return {
                "ticker": ticker,
                "sector": sector,
                "target": target_metrics,
                "peers": peers,
                "peer_count": len(peers)
            }

        except Exception as e:
            import traceback
            return {
                "error": f"Failed to get peers for {ticker}: {str(e)}",
                "details": traceback.format_exc()
            }
        finally:
            if conn:
                self.db.return_connection(conn)

    def _get_insider_activity(self, ticker: str, limit: int = 20) -> Dict[str, Any]:
        """Get insider trading activity."""
        ticker = ticker.upper()
        trades = self.db.get_insider_trades(ticker, limit=limit)

        if not trades:
            return {"ticker": ticker, "trades": [], "message": "No insider trades found"}

        # Filter to open market transactions (P=Purchase, S=Sale) or explicit Buy/Sell types
        open_market_trades = []
        for t in trades:
            code = t.get("transaction_code")
            type_label = t.get("transaction_type") or ""

            # Check for P/S code OR explicit Buy/Sell/Purchase/Sale type
            if code in ("P", "S"):
                open_market_trades.append(t)
            elif type_label.lower() in ("buy", "purchase", "sell", "sale"):
                open_market_trades.append(t)

        # Summarize
        buys = [t for t in open_market_trades if t.get("transaction_code") == "P" or t.get("transaction_type", "").lower() in ("buy", "purchase")]
        sells = [t for t in open_market_trades if t.get("transaction_code") == "S" or t.get("transaction_type", "").lower() in ("sell", "sale")]

        return {
            "ticker": ticker,
            "summary": {
                "total_buys": len(buys),
                "total_sells": len(sells),
                "buy_value": sum(t.get("value") or 0 for t in buys),
                "sell_value": sum(t.get("value") or 0 for t in sells),
            },
            "recent_trades": open_market_trades[:10],  # Top 10 most recent
        }

    def _search_news(self, ticker: str, limit: int = 10) -> Dict[str, Any]:
        """Search for news articles."""
        ticker = ticker.upper()

        if not self.stock_context:
            return {"error": "News search not available: StockContext not configured"}

        articles = self.stock_context._get_news_articles(ticker, limit=limit)

        if not articles:
            return {"ticker": ticker, "articles": [], "message": "No news articles found"}

        return {
            "ticker": ticker,
            "articles": articles,
        }

    def _get_filing_section(self, ticker: str, section: str) -> Dict[str, Any]:
        """Read a section from SEC filings."""
        ticker = ticker.upper()

        if not self.stock_context:
            return {"error": "Filing sections not available: StockContext not configured"}

        # Get filing sections (returns dict keyed by section name)
        sections, selected = self.stock_context._get_filing_sections(ticker, user_query=None, max_sections=4)

        if section not in sections:
            return {
                "error": f"Section '{section}' not found for {ticker}",
                "available_sections": list(sections.keys()),
            }

        section_data = sections[section]

        # Truncate content if very long (for context window management)
        content = section_data.get("content", "")
        if len(content) > 10000:
            content = content[:10000] + "\n... [TRUNCATED]"

        return {
            "ticker": ticker,
            "section": section,
            "filing_type": section_data.get("filing_type"),
            "filing_date": section_data.get("filing_date"),
            "content": content,
        }

    def _get_earnings_transcript(self, ticker: str) -> Dict[str, Any]:
        """Get the most recent earnings call transcript."""
        ticker = ticker.upper()

        transcript = self.db.get_latest_earnings_transcript(ticker)

        if not transcript:
            return {
                "error": f"No earnings transcript found for {ticker}",
                "suggestion": "Try using get_filing_section to read the 10-K or 10-Q instead."
            }

        # Return transcript with truncated text if very long
        text = transcript.get('transcript_text', '')
        if len(text) > 15000:
            text = text[:15000] + "\n... [TRUNCATED - see full transcript for more]"

        return {
            "ticker": ticker,
            "quarter": transcript.get('quarter'),
            "fiscal_year": transcript.get('fiscal_year'),
            "earnings_date": transcript.get('earnings_date'),
            "has_qa": transcript.get('has_qa'),
            "participants": transcript.get('participants', []),
            "summary": transcript.get('summary'),
            "transcript_text": text,
        }

    def _get_material_events(self, ticker: str, limit: int = 10) -> Dict[str, Any]:
        """Get recent material events (8-K filings)."""
        ticker = ticker.upper()

        events = self.db.get_material_events(ticker, limit=limit)

        if not events:
            return {
                "ticker": ticker,
                "events": [],
                "message": "No material events (8-K filings) found for this stock."
            }

        # Clean up events for output (exclude very long content_text)
        cleaned_events = []
        for event in events:
            cleaned_events.append({
                "event_type": event.get('event_type'),
                "headline": event.get('headline'),
                "description": event.get('description'),
                "filing_date": event.get('filing_date'),
                "sec_item_codes": event.get('sec_item_codes', []),
                "summary": event.get('summary'),  # AI-generated summary if available
            })

        return {
            "ticker": ticker,
            "event_count": len(cleaned_events),
            "events": cleaned_events,
        }

    def _get_price_history(self, ticker: str, start_year: int = None) -> Dict[str, Any]:
        """Get historical weekly stock prices."""
        ticker = ticker.upper()

        price_data = self.db.get_weekly_prices(ticker, start_year=start_year)

        if not price_data or not price_data.get('dates'):
            return {
                "error": f"No price history found for {ticker}",
                "suggestion": "Price data may not be available for this symbol."
            }

        dates = price_data.get('dates', [])
        prices = price_data.get('prices', [])

        # Calculate some basic stats
        if prices:
            current_price = prices[-1]
            first_price = prices[0]
            pct_change = ((current_price - first_price) / first_price * 100) if first_price else 0
            high = max(prices)
            low = min(prices)
        else:
            current_price = pct_change = high = low = None

        return {
            "ticker": ticker,
            "data_points": len(dates),
            "date_range": {"start": dates[0] if dates else None, "end": dates[-1] if dates else None},
            "summary": {
                "current_price": current_price,
                "period_high": high,
                "period_low": low,
                "total_return_pct": round(pct_change, 2) if pct_change else None,
            },
            # Return sampled data if too many points
            "prices": prices[-52:] if len(prices) > 52 else prices,  # Last 52 weeks
            "dates": dates[-52:] if len(dates) > 52 else dates,
        }

    def _get_historical_pe(self, ticker: str, years: int = 5) -> Dict[str, Any]:
        """Get historical annual P/E ratios."""
        ticker = ticker.upper()

        # Get earnings history (annual EPS)
        earnings = self.db.get_earnings_history(ticker, period_type='annual')

        if not earnings:
            return {
                "error": f"No earnings history found for {ticker}",
                "suggestion": "Try using get_stock_metrics for current P/E ratio."
            }

        # Get price history
        price_data = self.db.get_weekly_prices(ticker)

        if not price_data or not price_data.get('dates'):
            return {
                "error": f"No price history found for {ticker}",
            }

        # Build a dict of year -> year-end price (use last week of December)
        year_end_prices = {}
        for date_str, price in zip(price_data['dates'], price_data['prices']):
            # Parse date (format: YYYY-MM-DD)
            year = int(date_str[:4])
            month = int(date_str[5:7])
            # Use December prices as year-end
            if month == 12:
                year_end_prices[year] = price

        # Calculate P/E for each year
        pe_data = []
        current_year = 2025  # Current year

        for record in earnings:
            year = record.get('year')
            eps = record.get('eps')

            if not year or not eps or year < current_year - years:
                continue

            # Get year-end price (use previous year for annual EPS announced in Q1)
            price = year_end_prices.get(year)

            if price and eps and eps > 0:
                pe = round(price / eps, 2)
                pe_data.append({
                    "year": year,
                    "eps": eps,
                    "year_end_price": round(price, 2),
                    "pe_ratio": pe
                })

        # Sort by year ascending
        pe_data.sort(key=lambda x: x['year'])

        if not pe_data:
            return {
                "ticker": ticker,
                "pe_history": [],
                "message": "Could not calculate P/E ratios - missing price or EPS data for matched years."
            }

        return {
            "ticker": ticker,
            "years_of_data": len(pe_data),
            "pe_history": pe_data,
        }

    def _get_average_pe_ratio(self, ticker: str, period_type: str = 'annual', periods: int = None) -> Dict[str, Any]:
        """Calculate average P/E ratios over time (quarterly or annual)."""
        ticker = ticker.upper()

        # Set default periods based on period_type
        if periods is None:
            periods = 12 if period_type == 'quarterly' else 5

        # Get earnings history (quarterly or annual)
        earnings = self.db.get_earnings_history(ticker, period_type=period_type)

        if not earnings:
            return {
                "error": f"No {period_type} earnings history found for {ticker}",
                "suggestion": "Try using get_stock_metrics for current P/E ratio."
            }

        # Get price history
        price_data = self.db.get_weekly_prices(ticker)

        if not price_data or not price_data.get('dates'):
            return {
                "error": f"No price history found for {ticker}",
            }

        # Build a dict of date -> price for lookup
        price_by_date = {}
        for date_str, price in zip(price_data['dates'], price_data['prices']):
            price_by_date[date_str] = price

        # Calculate P/E for each period
        pe_data = []

        for record in earnings[:periods]:  # Limit to requested number of periods
            year = record.get('year')
            period = record.get('period')
            eps = record.get('eps')
            fiscal_end = record.get('fiscal_end')

            if not year or not eps or eps <= 0:
                continue

            # Find the appropriate price for this period
            price = None

            if period_type == 'annual':
                # For annual: use year-end price (December of that year)
                for date_str in price_by_date:
                    if date_str.startswith(f"{year}-12"):
                        price = price_by_date[date_str]
                        break
                # If no December price, try fiscal_end date or closest date
                if not price and fiscal_end:
                    fiscal_year = fiscal_end[:4]
                    fiscal_month = fiscal_end[5:7]
                    for date_str in price_by_date:
                        if date_str.startswith(f"{fiscal_year}-{fiscal_month}"):
                            price = price_by_date[date_str]
                            break
            else:  # quarterly
                # For quarterly: use price at quarter end
                # Q1 = March (03), Q2 = June (06), Q3 = September (09), Q4 = December (12)
                quarter_months = {'Q1': '03', 'Q2': '06', 'Q3': '09', 'Q4': '12'}
                target_month = quarter_months.get(period)

                if target_month:
                    for date_str in price_by_date:
                        if date_str.startswith(f"{year}-{target_month}"):
                            price = price_by_date[date_str]
                            break

                # Fallback to fiscal_end if available
                if not price and fiscal_end:
                    fiscal_year = fiscal_end[:4]
                    fiscal_month = fiscal_end[5:7]
                    for date_str in price_by_date:
                        if date_str.startswith(f"{fiscal_year}-{fiscal_month}"):
                            price = price_by_date[date_str]
                            break

            if price and eps > 0:
                pe = round(price / eps, 2)
                period_label = f"{year}" if period_type == 'annual' else f"{year} {period}"
                pe_data.append({
                    "period": period_label,
                    "year": year,
                    "quarter": period if period_type == 'quarterly' else None,
                    "eps": round(eps, 2),
                    "price": round(price, 2),
                    "pe_ratio": pe
                })

        if not pe_data:
            return {
                "ticker": ticker,
                "period_type": period_type,
                "pe_data": [],
                "message": f"Could not calculate P/E ratios - missing price or EPS data for {period_type} periods."
            }

        # Sort by year and period (most recent first)
        pe_data.sort(key=lambda x: (x['year'], x.get('quarter') or ''), reverse=True)

        # Calculate average P/E
        pe_values = [entry['pe_ratio'] for entry in pe_data]
        average_pe = round(sum(pe_values) / len(pe_values), 2)

        # Calculate min, max, and median
        min_pe = round(min(pe_values), 2)
        max_pe = round(max(pe_values), 2)
        sorted_pe = sorted(pe_values)
        median_pe = round(sorted_pe[len(sorted_pe) // 2], 2) if sorted_pe else None

        return {
            "ticker": ticker,
            "period_type": period_type,
            "periods_analyzed": len(pe_data),
            "average_pe": average_pe,
            "min_pe": min_pe,
            "max_pe": max_pe,
            "median_pe": median_pe,
            "pe_data": pe_data,
        }
