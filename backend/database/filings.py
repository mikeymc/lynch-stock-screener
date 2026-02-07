# ABOUTME: SEC filing storage, news articles, and material event persistence
# ABOUTME: Manages filing sections, summaries, and cache validity checks

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import json

logger = logging.getLogger(__name__)


class FilingsMixin:

    def save_sec_filing(self, symbol: str, filing_type: str, filing_date: str, document_url: str, accession_number: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sec_filings
            (symbol, filing_type, filing_date, document_url, accession_number, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, accession_number) DO UPDATE SET
                filing_type = EXCLUDED.filing_type,
                filing_date = EXCLUDED.filing_date,
                document_url = EXCLUDED.document_url,
                last_updated = EXCLUDED.last_updated
        """, (symbol, filing_type, filing_date, document_url, accession_number, datetime.now()))
        conn.commit()
        self.return_connection(conn)

    def get_sec_filings(self, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT filing_date, document_url, accession_number
            FROM sec_filings
            WHERE symbol = %s AND filing_type = '10-K'
            ORDER BY filing_date DESC
            LIMIT 1
        """, (symbol,))
        ten_k_row = cursor.fetchone()

        cursor.execute("""
            SELECT filing_date, document_url, accession_number
            FROM sec_filings
            WHERE symbol = %s AND filing_type = '10-Q'
            ORDER BY filing_date DESC
            LIMIT 3
        """, (symbol,))
        ten_q_rows = cursor.fetchall()

        self.return_connection(conn)

        if not ten_k_row and not ten_q_rows:
            return None

        result = {}

        if ten_k_row:
            result['10-K'] = {
                'filed_date': ten_k_row[0],
                'url': ten_k_row[1],
                'accession_number': ten_k_row[2]
            }

        if ten_q_rows:
            result['10-Q'] = [
                {
                    'filed_date': row[0],
                    'url': row[1],
                    'accession_number': row[2]
                }
                for row in ten_q_rows
            ]

        return result

    def is_filings_cache_valid(self, symbol: str, max_age_days: int = 7) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT last_updated FROM sec_filings
            WHERE symbol = %s
            ORDER BY last_updated DESC
            LIMIT 1
        """, (symbol,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return False

        last_updated = row[0]
        age_days = (datetime.now() - last_updated).total_seconds() / 86400
        return age_days < max_age_days

    def get_latest_sec_filing_date(self, symbol: str) -> Optional[str]:
        """
        Get the most recent filing date for a symbol.

        Used for incremental fetching - only fetch filings newer than this date.

        Args:
            symbol: Stock symbol

        Returns:
            Filing date string (YYYY-MM-DD) or None if no filings cached
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(filing_date) FROM sec_filings
            WHERE symbol = %s
        """, (symbol,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row or not row[0]:
            return None

        # Return as string in YYYY-MM-DD format
        if hasattr(row[0], 'strftime'):
            return row[0].strftime('%Y-%m-%d')
        return str(row[0])

    def save_filing_section(self, symbol: str, section_name: str, content: str, filing_type: str, filing_date: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO filing_sections
            (symbol, section_name, content, filing_type, filing_date, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, section_name, filing_type) DO UPDATE SET
                content = EXCLUDED.content,
                filing_date = EXCLUDED.filing_date,
                last_updated = EXCLUDED.last_updated
        """, (symbol, section_name, content, filing_type, filing_date, datetime.now()))
        conn.commit()
        self.return_connection(conn)

    def get_filing_sections(self, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT section_name, content, filing_type, filing_date, last_updated
            FROM filing_sections
            WHERE symbol = %s
        """, (symbol,))
        rows = cursor.fetchall()
        self.return_connection(conn)

        if not rows:
            return None

        sections = {}
        for row in rows:
            section_name = row[0]
            sections[section_name] = {
                'content': row[1],
                'filing_type': row[2],
                'filing_date': row[3],
                'last_updated': row[4]
            }

        return sections

    def is_sections_cache_valid(self, symbol: str, max_age_days: int = 30) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT last_updated FROM filing_sections
            WHERE symbol = %s
            ORDER BY last_updated DESC
            LIMIT 1
        """, (symbol,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return False

        last_updated = row[0]
        age_days = (datetime.now() - last_updated).total_seconds() / 86400
        return age_days < max_age_days

    def save_filing_section_summary(self, symbol: str, section_name: str, summary: str,
                                     filing_type: str, filing_date: str):
        """Save an AI-generated summary for a filing section."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO filing_section_summaries
            (symbol, section_name, summary, filing_type, filing_date, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, section_name, filing_type) DO UPDATE SET
                summary = EXCLUDED.summary,
                filing_date = EXCLUDED.filing_date,
                last_updated = EXCLUDED.last_updated
        """, (symbol, section_name, summary, filing_type, filing_date, datetime.now()))
        conn.commit()
        self.return_connection(conn)

    def get_filing_section_summaries(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get all AI-generated summaries for a symbol's filing sections."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT section_name, summary, filing_type, filing_date, last_updated
            FROM filing_section_summaries
            WHERE symbol = %s
        """, (symbol,))
        rows = cursor.fetchall()
        self.return_connection(conn)

        if not rows:
            return None

        summaries = {}
        for row in rows:
            section_name = row[0]
            summaries[section_name] = {
                'summary': row[1],
                'filing_type': row[2],
                'filing_date': row[3],
                'last_updated': row[4]
            }

        return summaries

    def save_news_article(self, symbol: str, article_data: Dict[str, Any]):
        """
        Save a news article to the database.

        Skips articles for symbols not in the stocks table to prevent FK violations.
        This aligns with the price caching pattern that gracefully skips missing stocks.

        Args:
            symbol: Stock symbol
            article_data: Dict containing article data (finnhub_id, headline, summary, etc.)
        """
        # Check if symbol exists in stocks table (skip if not - matches price cache pattern)
        if not self._symbol_exists(symbol):
            return

        sql = """
            INSERT INTO news_articles
            (symbol, finnhub_id, headline, summary, source, url, image_url, category, datetime, published_date, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, finnhub_id) DO UPDATE SET
                headline = EXCLUDED.headline,
                summary = EXCLUDED.summary,
                source = EXCLUDED.source,
                url = EXCLUDED.url,
                image_url = EXCLUDED.image_url,
                category = EXCLUDED.category,
                datetime = EXCLUDED.datetime,
                published_date = EXCLUDED.published_date,
                last_updated = EXCLUDED.last_updated
        """
        args = (
            symbol,
            article_data.get('finnhub_id'),
            article_data.get('headline'),
            article_data.get('summary'),
            article_data.get('source'),
            article_data.get('url'),
            article_data.get('image_url'),
            article_data.get('category'),
            article_data.get('datetime'),
            article_data.get('published_date'),
            datetime.now()
        )
        self.write_queue.put((sql, args))

    def get_news_articles(self, symbol: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get news articles for a stock, ordered by date descending (most recent first)

        Args:
            symbol: Stock symbol
            limit: Optional limit on number of articles to return

        Returns:
            List of article dicts
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT id, symbol, finnhub_id, headline, summary, source, url,
                   image_url, category, datetime, published_date, last_updated
            FROM news_articles
            WHERE symbol = %s
            ORDER BY datetime DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, (symbol,))
        rows = cursor.fetchall()
        self.return_connection(conn)

        return [
            {
                'id': row[0],
                'symbol': row[1],
                'finnhub_id': row[2],
                'headline': row[3],
                'summary': row[4],
                'source': row[5],
                'url': row[6],
                'image_url': row[7],
                'category': row[8],
                'datetime': row[9],
                'published_date': row[10].isoformat() if row[10] else None,
                'last_updated': row[11].isoformat() if row[11] else None
            }
            for row in rows
        ]

    def get_news_articles_multi(self, symbols: List[str], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent news articles across multiple symbols.

        Args:
            symbols: List of stock symbols
            limit: Max total articles to return

        Returns:
            List of article dicts sorted by datetime descending
        """
        if not symbols:
            return []

        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # Use ANY operator for efficiency with multiple symbols
            query = """
                SELECT id, symbol, finnhub_id, headline, summary, source, url,
                       image_url, category, datetime, published_date, last_updated
                FROM news_articles
                WHERE symbol = ANY(%s)
                ORDER BY datetime DESC
                LIMIT %s
            """

            cursor.execute(query, (list(symbols), limit))
            rows = cursor.fetchall()

            return [
                {
                    'id': row[0],
                    'symbol': row[1],
                    'finnhub_id': row[2],
                    'headline': row[3],
                    'summary': row[4],
                    'source': row[5],
                    'url': row[6],
                    'image_url': row[7],
                    'category': row[8],
                    'datetime': row[9],
                    'published_date': row[10].isoformat() if row[10] else None,
                    'last_updated': row[11].isoformat() if row[11] else None
                }
                for row in rows
            ]
        finally:
            self.return_connection(conn)

    def get_news_cache_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Check if we have cached news for a symbol and when it was last updated

        Args:
            symbol: Stock symbol

        Returns:
            Dict with cache info or None if no cache
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*), MAX(last_updated)
            FROM news_articles
            WHERE symbol = %s
        """, (symbol,))

        row = cursor.fetchone()
        self.return_connection(conn)

        if not row or row[0] == 0:
            return None

        return {
            'article_count': row[0],
            'last_updated': row[1]
        }

    def get_latest_news_timestamp(self, symbol: str) -> Optional[int]:
        """
        Get the Unix timestamp of when we last cached news for a symbol.

        Uses last_updated (cache time) not article datetime, so incremental
        fetching starts from when we last checked, not when the last article
        was published. This prevents re-fetching the same old articles.

        Args:
            symbol: Stock symbol

        Returns:
            Unix timestamp (seconds) or None if no articles cached
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Use last_updated (when we cached) not datetime (article publication)
            cursor.execute("""
                SELECT EXTRACT(EPOCH FROM MAX(last_updated))::bigint FROM news_articles
                WHERE symbol = %s
            """, (symbol,))
            row = cursor.fetchone()
            if not row or not row[0]:
                return None
            return int(row[0])
        finally:
            self.return_connection(conn)

    def save_material_event(self, symbol: str, event_data: Dict[str, Any]):
        """
        Save a material event (8-K) to database

        Args:
            symbol: Stock symbol
            event_data: Dict containing event data (event_type, headline, etc.)
        """
        sql = """
            INSERT INTO material_events
            (symbol, event_type, headline, description, source, url,
             filing_date, datetime, published_date, sec_accession_number,
             sec_item_codes, content_text, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, sec_accession_number)
            DO UPDATE SET
                headline = EXCLUDED.headline,
                description = EXCLUDED.description,
                content_text = EXCLUDED.content_text,
                last_updated = EXCLUDED.last_updated
        """
        args = (
            symbol,
            event_data.get('event_type', '8k'),
            event_data.get('headline'),
            event_data.get('description'),
            event_data.get('source', 'SEC'),
            event_data.get('url'),
            event_data.get('filing_date'),
            event_data.get('datetime'),
            event_data.get('published_date'),
            event_data.get('sec_accession_number'),
            event_data.get('sec_item_codes', []),
            event_data.get('content_text'),
            datetime.now()
        )
        self.write_queue.put((sql, args))

    def get_material_events(self, symbol: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get material events for a stock, ordered by date descending (most recent first)

        Args:
            symbol: Stock symbol
            limit: Optional limit on number of events to return

        Returns:
            List of event dicts (includes AI summary if available)
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT e.id, e.symbol, e.event_type, e.headline, e.description, e.source, e.url,
                   e.filing_date, e.datetime, e.published_date, e.sec_accession_number,
                   e.sec_item_codes, e.content_text, e.last_updated, s.summary
            FROM material_events e
            LEFT JOIN material_event_summaries s ON e.id = s.event_id
            WHERE e.symbol = %s
            ORDER BY e.datetime DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, (symbol,))
        rows = cursor.fetchall()
        self.return_connection(conn)

        return [
            {
                'id': row[0],
                'symbol': row[1],
                'event_type': row[2],
                'headline': row[3],
                'description': row[4],
                'source': row[5],
                'url': row[6],
                'filing_date': row[7].isoformat() if row[7] else None,
                'datetime': row[8],
                'published_date': row[9].isoformat() if row[9] else None,
                'sec_accession_number': row[10],
                'sec_item_codes': row[11] or [],
                'content_text': row[12],
                'last_updated': row[13].isoformat() if row[13] else None,
                'summary': row[14]
            }
            for row in rows
        ]

    def get_material_events_cache_status(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Check if we have cached material events for a symbol and when they were last updated

        Args:
            symbol: Stock symbol

        Returns:
            Dict with cache info or None if no cache
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*), MAX(last_updated)
            FROM material_events
            WHERE symbol = %s
        """, (symbol,))

        row = cursor.fetchone()
        self.return_connection(conn)

        if not row or row[0] == 0:
            return None

        return {
            'event_count': row[0],
            'last_updated': row[1]
        }

    def get_latest_material_event_date(self, symbol: str) -> Optional[str]:
        """
        Get the most recent 8-K filing date for a symbol.

        Used for incremental fetching - only fetch filings newer than this date.

        Args:
            symbol: Stock symbol

        Returns:
            Filing date string (YYYY-MM-DD) or None if no events cached
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(filing_date) FROM material_events
            WHERE symbol = %s
        """, (symbol,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row or not row[0]:
            return None

        # Return as string in YYYY-MM-DD format
        if hasattr(row[0], 'strftime'):
            return row[0].strftime('%Y-%m-%d')
        return str(row[0])

    def filing_exists(self, accession_number: str, form_type: str, ticker: str = None) -> bool:
        """
        Check if a filing with given accession number already exists in database.

        Used by RSS pagination to determine when to stop fetching (hit known filing).

        Args:
            accession_number: SEC accession number (e.g., '0001628280-26-003909')
            form_type: Filing type ('8-K', '10-K', '10-Q', 'FORM4')
            ticker: Optional ticker for Form 4 fallback check (since accession_number may be NULL in old data)

        Returns:
            True if filing exists, False otherwise
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Map form type to table and column
        if form_type == '8-K':
            table = 'material_events'
            column = 'sec_accession_number'
        elif form_type in ['10-K', '10-Q']:
            table = 'sec_filings'
            column = 'accession_number'
        elif form_type == 'FORM4':
            # For Form 4, check accession_number first, but fall back to checking if
            # we have ANY insider trades for this stock (since old data has NULL accession_number)
            cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM insider_trades
                    WHERE accession_number = %s
                )
            """, (accession_number,))

            result = cursor.fetchone()[0]

            # If not found by accession number and we have a ticker, check if we have ANY
            # insider trades for this stock (indicates we've processed it before)
            if not result and ticker:
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM insider_trades
                        WHERE symbol = %s
                        LIMIT 1
                    )
                """, (ticker,))
                result = cursor.fetchone()[0]

            self.return_connection(conn)
            return result
        else:
            self.return_connection(conn)
            return False

        cursor.execute(f"""
            SELECT EXISTS(
                SELECT 1 FROM {table}
                WHERE {column} = %s
            )
        """, (accession_number,))

        result = cursor.fetchone()[0]
        self.return_connection(conn)
        return result

    def save_material_event_summary(self, event_id: int, summary: str, model_version: str = None):
        """
        Save an AI-generated summary for a material event.

        Args:
            event_id: ID of the material event
            summary: Generated summary text
            model_version: Optional model version used for generation
        """
        sql = """
            INSERT INTO material_event_summaries (event_id, summary, model_version, generated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (event_id) DO UPDATE SET
                summary = EXCLUDED.summary,
                model_version = EXCLUDED.model_version,
                generated_at = NOW()
        """
        self.write_queue.put((sql, (event_id, summary, model_version)))

    def get_material_event_summary(self, event_id: int) -> Optional[str]:
        """
        Get the cached summary for a material event.

        Args:
            event_id: ID of the material event

        Returns:
            Summary text or None if not cached
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT summary FROM material_event_summaries WHERE event_id = %s
        """, (event_id,))
        row = cursor.fetchone()
        self.return_connection(conn)
        return row[0] if row else None

    def get_material_event_summaries_batch(self, event_ids: List[int]) -> Dict[int, str]:
        """
        Get cached summaries for multiple material events.

        Args:
            event_ids: List of material event IDs

        Returns:
            Dict mapping event_id to summary text (only includes cached events)
        """
        if not event_ids:
            return {}

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT event_id, summary FROM material_event_summaries
            WHERE event_id = ANY(%s)
        """, (event_ids,))
        rows = cursor.fetchall()
        self.return_connection(conn)
        return {row[0]: row[1] for row in rows}
