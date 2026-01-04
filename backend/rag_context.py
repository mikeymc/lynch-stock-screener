# ABOUTME: Assembles stock context for RAG chat from database
# ABOUTME: Provides smart section selection based on user queries and formats context for Gemini

from typing import Dict, Any, List, Optional, Tuple
from database import Database
import re
import json


class RAGContext:
    """Assembles and formats stock context for conversational RAG"""

    # Context types corresponding to frontend pages
    CONTEXT_TYPES = {
        'brief': 'brief',          # AnalysisChat full mode (default)
        'filings': 'filings',      # StockReports page
        'news': 'news',            # StockNews page
        'events': 'events',        # MaterialEvents page
        'dcf': 'dcf',              # DCFAnalysis page
        'charts': 'charts',        # StockCharts page
        'outlook': 'outlook',      # FutureOutlook page
        'transcript': 'transcript', # TranscriptViewer page
        'reddit': 'reddit',        # WordOnTheStreet page
    }

    # Keywords for smart section selection
    SECTION_KEYWORDS = {
        'business': ['business', 'products', 'services', 'customers', 'operations', 'what does', 'company do'],
        'risk_factors': ['risk', 'risks', 'concerns', 'problems', 'challenges', 'threats', 'vulnerabilities'],
        'mda': ['management', 'outlook', 'trends', 'performance', 'results', 'operations', 'strategy'],
        'market_risk': ['market risk', 'interest rate', 'currency', 'commodity', 'hedging']
    }

    def __init__(self, db: Database):
        """
        Initialize RAG context assembler

        Args:
            db: Database instance
        """
        self.db = db

    def get_stock_context(self, symbol: str, user_query: Optional[str] = None, context_type: str = 'brief') -> Dict[str, Any]:
        """
        Assemble complete stock context for RAG

        Args:
            symbol: Stock ticker symbol
            user_query: Optional user question to guide section selection
            context_type: Type of page context ('brief', 'news', 'events', 'filings', 'dcf', etc.)

        Returns:
            Dict containing context data specific to the requested type
        """
        # Base context always included
        context = {
            'stock_data': self._get_stock_data(symbol),
            'earnings_history': self._get_earnings_history(symbol),
        }
        
        if not context['stock_data']:
            return None

        # Add earnings transcript to all contexts where deeper analysis might be needed
        context['earnings_transcript'] = self._get_earnings_transcript(symbol)
        
        # Primary context based on page
        if context_type == 'news':
            context['news_articles'] = self._get_news_articles(symbol, limit=10)
            context['events_summary'] = self._get_events_summary(symbol, limit=3)
            context['filings_summary'] = self._get_filings_summary(symbol)
            context['insider_summary'] = self._get_insider_summary(symbol)
            context['outlook_summary'] = self._get_outlook_summary(symbol)
            
        elif context_type == 'events':
            context['material_events'] = self._get_material_events(symbol, limit=10)
            context['news_summary'] = self._get_news_summary(symbol, limit=3)
            context['filings_summary'] = self._get_filings_summary(symbol)
            context['insider_summary'] = self._get_insider_summary(symbol)
            context['outlook_summary'] = self._get_outlook_summary(symbol)
            
        elif context_type == 'filings':
            filing_sections, selected = self._get_filing_sections(symbol, user_query, 3)
            context['filing_sections'] = filing_sections
            context['selected_sections'] = selected
            context['news_summary'] = self._get_news_summary(symbol, limit=3)
            context['events_summary'] = self._get_events_summary(symbol, limit=3)
            context['insider_summary'] = self._get_insider_summary(symbol)
            context['outlook_summary'] = self._get_outlook_summary(symbol)
            
        elif context_type == 'dcf':
            context['dcf_data'] = self._get_dcf_data(symbol)
            filing_sections, selected = self._get_filing_sections(symbol, user_query, 2)
            context['filing_sections'] = filing_sections
            context['selected_sections'] = selected
            context['news_summary'] = self._get_news_summary(symbol, limit=3)
            context['outlook_summary'] = self._get_outlook_summary(symbol)
            
        elif context_type == 'charts' or context_type == 'outlook':
            filing_sections, selected = self._get_filing_sections(symbol, user_query, 2)
            context['filing_sections'] = filing_sections
            context['selected_sections'] = selected
            context['news_summary'] = self._get_news_summary(symbol, limit=3)
            context['outlook_data'] = self._get_outlook_data(symbol)
            context['insider_summary'] = self._get_insider_summary(symbol)

        elif context_type == 'transcript':
            # Transcript page: full transcript is already in base context, add supporting data
            context['news_summary'] = self._get_news_summary(symbol, limit=3)
            context['events_summary'] = self._get_events_summary(symbol, limit=3)
            context['filings_summary'] = self._get_filings_summary(symbol)
            context['outlook_summary'] = self._get_outlook_summary(symbol)

        elif context_type == 'reddit':
            # Reddit page: social sentiment data is primary
            context['social_sentiment'] = self._get_social_sentiment(symbol, limit=10)
            context['news_summary'] = self._get_news_summary(symbol, limit=3)
            context['events_summary'] = self._get_events_summary(symbol, limit=3)
            context['insider_summary'] = self._get_insider_summary(symbol)
            context['outlook_summary'] = self._get_outlook_summary(symbol)

        else:  # 'brief' or default
            filing_sections, selected = self._get_filing_sections(symbol, user_query, 3)
            context['filing_sections'] = filing_sections
            context['selected_sections'] = selected
            context['news_articles'] = self._get_news_articles(symbol, limit=5)
            context['insider_summary'] = self._get_insider_summary(symbol)
            context['outlook_summary'] = self._get_outlook_summary(symbol)

        return context

    def _get_stock_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current stock metrics from database"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                s.symbol, s.company_name, s.exchange, s.sector, s.country, s.ipo_year,
                sm.price, sm.pe_ratio, sm.market_cap, sm.debt_to_equity,
                sm.institutional_ownership, sm.revenue, sm.dividend_yield
            FROM stocks s
            LEFT JOIN stock_metrics sm ON s.symbol = sm.symbol
            WHERE s.symbol = %s
        """, (symbol,))

        row = cursor.fetchone()
        self.db.return_connection(conn)

        if not row:
            return None

        return {
            'symbol': row[0],
            'company_name': row[1],
            'exchange': row[2],
            'sector': row[3],
            'country': row[4],
            'ipo_year': row[5],
            'price': row[6],
            'pe_ratio': row[7],
            'market_cap': row[8],
            'debt_to_equity': row[9],
            'institutional_ownership': row[10],
            'revenue': row[11],
            'dividend_yield': row[12]
        }

    def _get_earnings_history(self, symbol: str) -> List[Dict[str, Any]]:
        """Get historical earnings data"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT year, earnings_per_share, revenue, debt_to_equity, fiscal_end
            FROM earnings_history
            WHERE symbol = %s AND period = 'annual'
            ORDER BY year DESC
            LIMIT 10
        """, (symbol,))

        rows = cursor.fetchall()
        self.db.return_connection(conn)

        return [{
            'year': row[0],
            'eps': row[1],
            'revenue': row[2],
            'debt_to_equity': row[3],
            'fiscal_end': row[4]
        } for row in rows]

    def _get_news_articles(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent news articles for the stock"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT headline, summary, source, url, published_date
            FROM news_articles
            WHERE symbol = %s
            ORDER BY published_date DESC
            LIMIT %s
        """, (symbol, limit))

        rows = cursor.fetchall()
        self.db.return_connection(conn)

        return [{
            'headline': row[0],
            'summary': row[1],
            'source': row[2],
            'url': row[3],
            'published_date': row[4]
        } for row in rows]

    # --- New Data Fetchers for Dynamic Context ---

    def _get_news_summary(self, symbol: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get just headlines and dates for news (lightweight)"""
        return self._get_news_articles(symbol, limit=limit)

    def _get_material_events(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get material events (8-Ks) with full details"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT event_type, headline, description, filing_date, url
            FROM material_events
            WHERE symbol = %s
            ORDER BY filing_date DESC
            LIMIT %s
        """, (symbol, limit))
        
        rows = cursor.fetchall()
        self.db.return_connection(conn)
        
        return [{
            'event_type': row[0],
            'headline': row[1],
            'description': row[2],
            'filing_date': row[3],
            'url': row[4]
        } for row in rows]

    def _get_earnings_transcript(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest earnings call transcript"""
        return self.db.get_latest_earnings_transcript(symbol)

    def _get_events_summary(self, symbol: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get just headlines/types for events (lightweight)"""
        return self._get_material_events(symbol, limit=limit)

    def _get_filings_summary(self, symbol: str) -> List[Dict[str, Any]]:
        """Get list of available filing sections (names/dates only)"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT section_name, filing_type, filing_date
            FROM filing_sections
            WHERE symbol = %s
            GROUP BY section_name, filing_type, filing_date
            ORDER BY filing_date DESC
            LIMIT 10
        """, (symbol,))
        
        rows = cursor.fetchall()
        self.db.return_connection(conn)
        
        return [{
            'section_name': row[0],
            'filing_type': row[1],
            'filing_date': row[2]
        } for row in rows]

    def _get_dcf_data(self, symbol: str) -> Dict[str, Any]:
        """Get DCF-related data (FCF history, WACC, recommendations)"""
        # Get FCF history
        earnings = self._get_earnings_history(symbol)
        fcf_history = [{'year': e['year'], 'free_cash_flow': e.get('free_cash_flow')} 
                      for e in earnings if e.get('free_cash_flow') is not None]
        
        # Get cached recommendations
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT recommendations_json, generated_at 
            FROM dcf_recommendations 
            WHERE symbol = %s
        """, (symbol,))
        row = cursor.fetchone()
        self.db.return_connection(conn)
        
        recs = None
        if row and row[0]:
            try:
                recs = json.loads(row[0])
            except:
                pass
                
        return {
            'fcf_history': fcf_history,
            'recommendations': recs,
            'rec_date': row[1] if row else None
        }

    def _get_insider_trades(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get insider trades, filtered to open market interactions"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Filter for P (Purchase) or S (Sale) transaction codes
        cursor.execute("""
            SELECT name, position, transaction_date, transaction_type, shares, value, 
                   price_per_share, transaction_code
            FROM insider_trades
            WHERE symbol = %s 
            AND transaction_code IN ('P', 'S')
            ORDER BY transaction_date DESC
            LIMIT %s
        """, (symbol, limit))
        
        rows = cursor.fetchall()
        self.db.return_connection(conn)
        
        return [{
            'name': row[0],
            'position': row[1],
            'transaction_date': row[2],
            'transaction_type': row[3],
            'shares': row[4],
            'value': row[5],
            'price': row[6],
            'code': row[7]
        } for row in rows]

    def _get_insider_summary(self, symbol: str) -> Dict[str, Any]:
        """Get summary of insider activity (counts/totals)"""
        trades = self._get_insider_trades(symbol, limit=50)
        
        buys = [t for t in trades if t['code'] == 'P']
        sells = [t for t in trades if t['code'] == 'S']
        
        return {
            'recent_buy_count': len(buys),
            'recent_sell_count': len(sells),
            'last_trade_date': trades[0]['transaction_date'] if trades else None
        }

    def _get_outlook_data(self, symbol: str) -> Dict[str, Any]:
        """Get forward-looking metrics"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT forward_pe, forward_peg_ratio, forward_eps
            FROM stock_metrics
            WHERE symbol = %s
        """, (symbol,))
        
        row = cursor.fetchone()
        self.db.return_connection(conn)
        
        if not row:
            return {}
            
        return {
            'forward_pe': row[0],
            'forward_peg': row[1],
            'forward_eps': row[2]
        }

    def _get_outlook_summary(self, symbol: str) -> Dict[str, Any]:
        """Same as data for now, lightweight enough"""
        return self._get_outlook_data(symbol)
    
    def _get_social_sentiment(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get Reddit posts and comments from social_sentiment table"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT title, selftext, subreddit, author, score, num_comments,
                   sentiment_score, published_at, url
            FROM social_sentiment
            WHERE symbol = %s
            ORDER BY published_at DESC
            LIMIT %s
        """, (symbol, limit))
        
        rows = cursor.fetchall()
        self.db.return_connection(conn)
        
        return [{
            'title': row[0],
            'body': row[1],
            'subreddit': row[2],
            'author': row[3],
            'score': row[4],
            'num_comments': row[5],
            'sentiment_score': row[6],
            'published_at': row[7],
            'url': row[8]
        } for row in rows]

    def _get_filing_sections(self, symbol: str, user_query: Optional[str], max_sections: int) -> Tuple[Dict[str, Any], List[str]]:
        """
        Get filing sections with smart selection based on user query

        Returns:
            Tuple of (sections_dict, selected_section_names)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Get all available sections
        cursor.execute("""
            SELECT section_name, content, filing_type, filing_date
            FROM filing_sections
            WHERE symbol = %s
            ORDER BY filing_date DESC
        """, (symbol,))

        rows = cursor.fetchall()
        self.db.return_connection(conn)

        if not rows:
            return {}, []

        # Group by section name (keep most recent)
        sections_by_name = {}
        for row in rows:
            section_name = row[0]
            if section_name not in sections_by_name:
                sections_by_name[section_name] = {
                    'content': row[1],
                    'filing_type': row[2],
                    'filing_date': row[3]
                }

        # Smart selection based on user query
        if user_query:
            selected_names = self._select_relevant_sections(user_query, list(sections_by_name.keys()), max_sections)
        else:
            # Default: include most useful sections
            priority_order = ['business', 'mda', 'risk_factors', 'market_risk']
            selected_names = [name for name in priority_order if name in sections_by_name][:max_sections]

        # Build result dict
        selected_sections = {name: sections_by_name[name] for name in selected_names if name in sections_by_name}

        return selected_sections, selected_names

    def _select_relevant_sections(self, query: str, available_sections: List[str], max_sections: int) -> List[str]:
        """
        Select most relevant sections based on query keywords

        Args:
            query: User's question
            available_sections: List of available section names
            max_sections: Maximum sections to return

        Returns:
            List of selected section names, ordered by relevance
        """
        query_lower = query.lower()

        # Score each section based on keyword matches
        section_scores = {}
        for section_name in available_sections:
            if section_name not in self.SECTION_KEYWORDS:
                continue

            score = 0
            keywords = self.SECTION_KEYWORDS[section_name]

            for keyword in keywords:
                if keyword in query_lower:
                    # Longer keywords get higher weight
                    score += len(keyword.split())

            if score > 0:
                section_scores[section_name] = score

        # Sort by score and return top N
        sorted_sections = sorted(section_scores.items(), key=lambda x: x[1], reverse=True)
        selected = [name for name, score in sorted_sections[:max_sections]]

        # If we don't have enough sections, add defaults
        if len(selected) < max_sections:
            defaults = ['business', 'mda', 'risk_factors']
            for default in defaults:
                if default in available_sections and default not in selected:
                    selected.append(default)
                    if len(selected) >= max_sections:
                        break

        return selected

    def format_for_llm(self, context: Dict[str, Any], user_query: str, conversation_history: Optional[List[Dict[str, str]]] = None, lynch_analysis: Optional[str] = None) -> str:
        """
        Format assembled context into a prompt for the LLM

        Args:
            context: Context dict from get_stock_context()
            user_query: Current user question
            conversation_history: Optional list of previous messages
            lynch_analysis: Optional Lynch-style analysis text to include as context

        Returns:
            Formatted prompt string
        """
        stock_data = context['stock_data']
        earnings_history = context['earnings_history']
        filing_sections = context.get('filing_sections', {})
        
        # New context items
        news_items = context.get('news_articles') or context.get('news_summary', [])
        event_items = context.get('material_events') or context.get('events_summary', [])
        dcf_data = context.get('dcf_data')
        insider_summary = context.get('insider_summary')
        outlook_data = context.get('outlook_data') or context.get('outlook_summary')
        filings_summary = context.get('filings_summary')
        earnings_transcript = context.get('earnings_transcript')
        social_sentiment = context.get('social_sentiment', [])

        # Build the prompt
        prompt_parts = []

        prompt_parts.append("You are a stock analyst applying Peter Lynch's investment methodology from 'One Up on Wall Street'. ")
        prompt_parts.append("Answer questions about stocks using this methodology. ")
        prompt_parts.append("Be clear, direct, and professional. ")
        prompt_parts.append("Do not explicitly reference Peter Lynch or other investors by name unless the user asks. ")
        prompt_parts.append("Keep responses concise (250-500 words) unless the user explicitly asks for more detail.\n\n")

        # Stock overview
        prompt_parts.append(f"## Stock: {stock_data['company_name']} ({stock_data['symbol']})\n\n")
        prompt_parts.append(f"**Sector:** {stock_data['sector']}\n")
        prompt_parts.append(f"**Exchange:** {stock_data['exchange']}\n")
        if stock_data['country']:
            prompt_parts.append(f"**Country:** {stock_data['country']}\n")
        prompt_parts.append("\n")

        # Current metrics
        prompt_parts.append("### Current Metrics\n\n")
        if stock_data['price']:
            prompt_parts.append(f"- **Price:** ${stock_data['price']:.2f}\n")
        if stock_data['market_cap']:
            prompt_parts.append(f"- **Market Cap:** ${stock_data['market_cap']/1e9:.2f}B\n")
        if stock_data['pe_ratio']:
            prompt_parts.append(f"- **P/E Ratio:** {stock_data['pe_ratio']:.2f}\n")
        if stock_data['debt_to_equity']:
            prompt_parts.append(f"- **Debt/Equity:** {stock_data['debt_to_equity']:.2f}\n")
        if stock_data['institutional_ownership']:
            prompt_parts.append(f"- **Institutional Ownership:** {stock_data['institutional_ownership']*100:.1f}%\n")
        if stock_data['dividend_yield']:
            prompt_parts.append(f"- **Dividend Yield:** {stock_data['dividend_yield']*100:.2f}%\n")
            
        # Add Outlook Metrics if available
        if outlook_data:
            if outlook_data.get('forward_pe'):
                 prompt_parts.append(f"- **Forward P/E:** {outlook_data['forward_pe']:.2f}\n")
            if outlook_data.get('forward_peg'):
                 prompt_parts.append(f"- **Forward PEG:** {outlook_data['forward_peg']:.2f}\n")
            if outlook_data.get('forward_eps'):
                 prompt_parts.append(f"- **Forward EPS:** ${outlook_data['forward_eps']:.2f}\n")

        prompt_parts.append("\n")

        # Historical performance
        if earnings_history:
            prompt_parts.append("### Historical Performance (Annual)\n\n")
            for year_data in sorted(earnings_history, key=lambda x: x['year']):
                year = year_data['year']
                eps = year_data['eps']
                revenue = year_data['revenue']
                de = year_data['debt_to_equity']

                line = f"- **{year}:** EPS=${eps:.2f}, Revenue=${revenue/1e9:.2f}B"
                if de:
                    line += f", D/E={de:.2f}"
                prompt_parts.append(line + "\n")
            prompt_parts.append("\n")

        # DCF Data (if available)
        if dcf_data:
            prompt_parts.append("### DCF Analysis Data\n\n")
            if dcf_data.get('recommendations'):
                prompt_parts.append("**DCF Scenarios:**\n")
                recs = dcf_data['recommendations'].get('scenarios', {})
                for case, val in recs.items():
                    prompt_parts.append(f"- {case.title()}: ${val}\n")
                prompt_parts.append("\n")
            
            if dcf_data.get('fcf_history'):
                prompt_parts.append("**Free Cash Flow History:**\n")
                for item in dcf_data['fcf_history']:
                    if item.get('free_cash_flow'):
                        prompt_parts.append(f"- {item['year']}: ${item['free_cash_flow']/1e6:.1f}M\n")
                prompt_parts.append("\n")

        # Material Events (if available)
        if event_items:
            prompt_parts.append("### Material Events (8-K)\n\n")
            for event in event_items:
                headline = event.get('headline', 'Untitled')
                date_val = event.get('filing_date')
                summary = event.get('summary')  # AI-generated summary
                desc = event.get('description')
                url = event.get('url')
                
                if url:
                    prompt_parts.append(f"- [{headline}]({url}) ({date_val})\n")
                else:
                    prompt_parts.append(f"- **{headline}** ({date_val})\n")
                
                # Prefer AI summary over raw description
                if summary:
                    prompt_parts.append(f"  **AI Summary:** {summary}\n")
                elif desc:
                    # Truncate description slightly for context saving if it's super long
                    if len(desc) > 500:
                        desc = desc[:500] + "..."
                    prompt_parts.append(f"  {desc}\n")
            prompt_parts.append("\n")
            
        # Insider Trading Summary
        if insider_summary:
            prompt_parts.append("### Insider Trading (Last 6 Months)\n\n")
            prompt_parts.append(f"- **Recent Buys (Open Market):** {insider_summary.get('recent_buy_count', 0)}\n")
            prompt_parts.append(f"- **Recent Sells (Open Market):** {insider_summary.get('recent_sell_count', 0)}\n")
            if insider_summary.get('last_trade_date'):
                 prompt_parts.append(f"- **Last Trade Date:** {insider_summary['last_trade_date']}\n")
            prompt_parts.append("\n")

        # Earnings Call Transcript (High Priority)
        if earnings_transcript:
            prompt_parts.append("### Latest Earnings Call Transcript (VERBATIM)\n\n")
            
            # Add metadata
            meta = []
            if earnings_transcript.get('quarter'):
                meta.append(f"**Period:** {earnings_transcript['quarter']} {earnings_transcript.get('fiscal_year', '')}")
            if earnings_transcript.get('earnings_date'):
                meta.append(f"**Date:** {earnings_transcript['earnings_date']}")
            prompt_parts.append(" | ".join(meta) + "\n\n")
            
            # Add transcript content (truncated if too long to fit context window safely)
            # Assuming we have large context window, but being safe
            text = earnings_transcript.get('transcript_text', '')
            if len(text) > 100000:
                text = text[:100000] + "... [TRUNCATED]"
            
            prompt_parts.append(f"{text}\n\n")
            
            # Check for Q&A
            if earnings_transcript.get('has_qa'):
                prompt_parts.append("**Note:** This transcript includes the full Question & Answer session with analysts.\n\n")

        # SEC Filing sections
        if filing_sections:
            prompt_parts.append("### SEC Filing Excerpts\n\n")

            section_labels = {
                'business': 'Business Description (Item 1)',
                'risk_factors': 'Risk Factors (Item 1A)',
                'mda': "Management's Discussion & Analysis",
                'market_risk': 'Market Risk Disclosures'
            }

            for section_name, section_data in filing_sections.items():
                label = section_labels.get(section_name, section_name.replace('_', ' ').title())
                filing_type = section_data['filing_type']
                filing_date = section_data['filing_date']
                content = section_data['content']

                prompt_parts.append(f"#### {label} ({filing_type}, filed {filing_date})\n\n")
                prompt_parts.append(f"{content}\n\n")

        # Recent news articles
        if news_items:
            prompt_parts.append("### Recent News\n\n")
            for article in news_items:
                headline = article.get('headline', 'No headline')
                summary = article.get('summary', '')
                source = article.get('source', 'Unknown')
                url = article.get('url', '')
                pub_date = article.get('published_date')
                
                # Format date
                date_str = ''
                if pub_date:
                    try:
                        if hasattr(pub_date, 'strftime'):
                            date_str = pub_date.strftime('%b %d, %Y')
                        else:
                            from datetime import datetime
                            dt = datetime.fromisoformat(str(pub_date).replace('Z', '+00:00'))
                            date_str = dt.strftime('%b %d, %Y')
                    except:
                        date_str = str(pub_date)[:10]
                
                # Format with deep link
                if url:
                    prompt_parts.append(f"- [{headline}]({url}) ({source}, {date_str})\n")
                else:
                    prompt_parts.append(f"- **{headline}** ({source}, {date_str})\n")
                
                if summary:
                    prompt_parts.append(f"  {summary}\n")
            prompt_parts.append("\n")
        
        # Social Sentiment (Reddit)
        if social_sentiment:
            prompt_parts.append("### Reddit Discussions (Social Sentiment)\n\n")
            for post in social_sentiment:
                title = post.get('title', 'Untitled')
                subreddit = post.get('subreddit', 'unknown')
                score = post.get('score', 0)
                num_comments = post.get('num_comments', 0)
                sentiment = post.get('sentiment_score', 0)
                body = post.get('body', '')
                url = post.get('url', '')
                pub_date = post.get('published_at')
                
                # Format date
                date_str = ''
                if pub_date:
                    try:
                        if hasattr(pub_date, 'strftime'):
                            date_str = pub_date.strftime('%b %d, %Y')
                        else:
                            from datetime import datetime
                            dt = datetime.fromisoformat(str(pub_date).replace('Z', '+00:00'))
                            date_str = dt.strftime('%b %d, %Y')
                    except:
                        date_str = str(pub_date)[:10]
                
                # Sentiment label
                sent_label = 'Neutral'
                if sentiment > 0.2:
                    sent_label = 'Bullish'
                elif sentiment < -0.2:
                    sent_label = 'Bearish'
                
                # Format post
                if url:
                    prompt_parts.append(f"- **[{title}]({url})** (r/{subreddit}, {date_str})\n")
                else:
                    prompt_parts.append(f"- **{title}** (r/{subreddit}, {date_str})\n")
                prompt_parts.append(f"  ⬆ {score} | 💬 {num_comments} | Sentiment: {sent_label}\n")
                
                if body:
                    # Include full body for context
                    prompt_parts.append(f"  {body}\n")
            prompt_parts.append("\n")
            
        # Filings Summary (Fallback)
        if filings_summary:
             prompt_parts.append("### Available Filings (Summary)\n\n")
             for f in filings_summary:
                 prompt_parts.append(f"- {f['section_name']} ({f['filing_type']}, {f['filing_date']})\n")
             prompt_parts.append("\n")

        # Lynch-Style Analysis (if provided)
        if lynch_analysis:
            prompt_parts.append("### Stock Analysis\n\n")
            prompt_parts.append(f"{lynch_analysis}\n\n")

        # Conversation history
        if conversation_history:
            prompt_parts.append("### Previous Conversation\n\n")
            for msg in conversation_history[-5:]:  # Last 5 messages
                role_label = "User" if msg['role'] == 'user' else "Analyst"
                prompt_parts.append(f"**{role_label}:** {msg['content']}\n\n")

        # Current question
        prompt_parts.append("---\n\n")
        prompt_parts.append(f"**User Question:** {user_query}\n\n")
        prompt_parts.append("**Your Response:**\n")

        return "".join(prompt_parts)
