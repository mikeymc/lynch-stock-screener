# ABOUTME: Assembles stock context for RAG chat from database
# ABOUTME: Provides smart section selection based on user queries and formats context for Gemini

from typing import Dict, Any, List, Optional, Tuple
from database_sqlite import Database
import re


class RAGContext:
    """Assembles and formats stock context for conversational RAG"""

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

    def get_stock_context(self, symbol: str, user_query: Optional[str] = None, max_sections: int = 3) -> Dict[str, Any]:
        """
        Assemble complete stock context for RAG

        Args:
            symbol: Stock ticker symbol
            user_query: Optional user question to guide section selection
            max_sections: Maximum number of filing sections to include

        Returns:
            Dict containing:
                - stock_data: Current metrics
                - earnings_history: Historical performance
                - filing_sections: Relevant SEC filing sections
                - selected_sections: List of section names that were selected
        """
        # Get stock data
        stock_data = self._get_stock_data(symbol)
        if not stock_data:
            return None

        # Get earnings history
        earnings_history = self._get_earnings_history(symbol)

        # Get filing sections (smart selection based on query)
        filing_sections, selected_section_names = self._get_filing_sections(
            symbol,
            user_query,
            max_sections
        )

        return {
            'stock_data': stock_data,
            'earnings_history': earnings_history,
            'filing_sections': filing_sections,
            'selected_sections': selected_section_names
        }

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
            WHERE s.symbol = ?
        """, (symbol,))

        row = cursor.fetchone()
        conn.close()

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
            WHERE symbol = ? AND period = 'annual'
            ORDER BY year DESC
            LIMIT 10
        """, (symbol,))

        rows = cursor.fetchall()
        conn.close()

        return [{
            'year': row[0],
            'eps': row[1],
            'revenue': row[2],
            'debt_to_equity': row[3],
            'fiscal_end': row[4]
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
            WHERE symbol = ?
            ORDER BY filing_date DESC
        """, (symbol,))

        rows = cursor.fetchall()
        conn.close()

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
            lynch_analysis: Optional Peter Lynch analysis text to include as context

        Returns:
            Formatted prompt string
        """
        stock_data = context['stock_data']
        earnings_history = context['earnings_history']
        filing_sections = context['filing_sections']

        # Build the prompt
        prompt_parts = []

        # System context
        prompt_parts.append("You are Peter Lynch, the legendary investor and author of 'One Up on Wall Street'. ")
        prompt_parts.append("Answer questions about stocks using your investment methodology. ")
        prompt_parts.append("Be conversational, insightful, and use analogies when helpful.\n\n")

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

        # Peter Lynch Analysis (if provided)
        if lynch_analysis:
            prompt_parts.append("### Peter Lynch Analysis\n\n")
            prompt_parts.append(f"{lynch_analysis}\n\n")

        # Conversation history
        if conversation_history:
            prompt_parts.append("### Previous Conversation\n\n")
            for msg in conversation_history[-5:]:  # Last 5 messages
                role_label = "User" if msg['role'] == 'user' else "Peter Lynch"
                prompt_parts.append(f"**{role_label}:** {msg['content']}\n\n")

        # Current question
        prompt_parts.append("---\n\n")
        prompt_parts.append(f"**User Question:** {user_query}\n\n")
        prompt_parts.append("**Your Response (as Peter Lynch):**\n")

        return "".join(prompt_parts)
