# ABOUTME: Manages PostgreSQL database for caching stock data and financial metrics
# ABOUTME: Provides schema and operations for storing and retrieving stock information

import psycopg2
import psycopg2.pool
import psycopg2.extras
import threading
import os
import queue
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
import json


class Database:
    def __init__(self,
                 host: str = "localhost",
                 port: int = 5432,
                 database: str = "lynch_stocks",
                 user: str = "lynch",
                 password: str = "lynch_dev_password"):

        self.db_params = {
            'host': host,
            'port': port,
            'database': database,
            'user': user,
            'password': password
        }

        self._lock = threading.Lock()
        self._initializing = True

        # Connection pool for concurrent reads
        # Pool size must accommodate parallel screening workers (40) + some overhead
        self.pool_size = 50
        self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=5,
            maxconn=self.pool_size,
            **self.db_params
        )

        # Queue for database write operations
        self.write_queue = queue.Queue()
        self.write_batch_size = 50

        # Initialize schema
        init_conn = self.connection_pool.getconn()
        try:
            self._init_schema_with_connection(init_conn)
        finally:
            self.connection_pool.putconn(init_conn)

        self._initializing = False

        # Start background writer thread
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        print("Database writer thread started")

    def get_connection(self):
        """Get a connection from the pool"""
        return self.connection_pool.getconn()

    def return_connection(self, conn):
        """Return a connection to the pool"""
        self.connection_pool.putconn(conn)

    def _writer_loop(self):
        """
        Background thread that handles all database writes sequentially.
        Implements batched writes for better performance with high concurrency.
        """
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        batch = []
        last_commit = time.time()

        while True:
            try:
                try:
                    task = self.write_queue.get(timeout=2.0)
                except queue.Empty:
                    task = None

                if task is None and not batch:
                    continue

                if task is not None:
                    if task == "STOP":
                        if batch:
                            conn.commit()
                        break

                    batch.append(task)
                    self.write_queue.task_done()

                should_commit = (
                    len(batch) >= self.write_batch_size or
                    (batch and time.time() - last_commit >= 2.0)
                )

                if should_commit:
                    try:
                        for sql, args in batch:
                            cursor.execute(sql, args)
                        conn.commit()
                        last_commit = time.time()
                        batch = []
                    except Exception as e:
                        print(f"Database batch write error: {e}")
                        conn.rollback()
                        batch = []

            except Exception as e:
                print(f"Fatal error in writer loop: {e}")
                time.sleep(1)

        self.connection_pool.putconn(conn)

    def connection(self):
        """
        Context manager for database connections.
        """
        from contextlib import contextmanager

        @contextmanager
        def _connection():
            conn = self.get_connection()
            try:
                yield conn
            finally:
                self.return_connection(conn)

        return _connection()

    def _init_schema_with_connection(self, conn):
        """Initialize database schema using the provided connection"""
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                symbol TEXT PRIMARY KEY,
                company_name TEXT,
                exchange TEXT,
                sector TEXT,
                country TEXT,
                ipo_year INTEGER,
                last_updated TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_metrics (
                symbol TEXT PRIMARY KEY,
                price REAL,
                pe_ratio REAL,
                market_cap REAL,
                debt_to_equity REAL,
                institutional_ownership REAL,
                revenue REAL,
                dividend_yield REAL,
                last_updated TIMESTAMP,
                beta REAL,
                total_debt REAL,
                interest_expense REAL,
                effective_tax_rate REAL,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS earnings_history (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                year INTEGER,
                earnings_per_share REAL,
                revenue REAL,
                fiscal_end TEXT,
                debt_to_equity REAL,
                period TEXT DEFAULT 'annual',
                net_income REAL,
                dividend_amount REAL,
                dividend_yield REAL,
                operating_cash_flow REAL,
                capital_expenditures REAL,
                free_cash_flow REAL,
                last_updated TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, year, period)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lynch_analyses (
                symbol TEXT PRIMARY KEY,
                analysis_text TEXT,
                generated_at TIMESTAMP,
                model_version TEXT,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chart_analyses (
                symbol TEXT,
                section TEXT,
                analysis_text TEXT,
                generated_at TIMESTAMP,
                model_version TEXT,
                PRIMARY KEY (symbol, section),
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol TEXT PRIMARY KEY,
                added_at TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sec_filings (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                filing_type TEXT,
                filing_date TEXT,
                document_url TEXT,
                accession_number TEXT,
                last_updated TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, accession_number)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS filing_sections (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                section_name TEXT,
                content TEXT,
                filing_type TEXT,
                filing_date TEXT,
                last_updated TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, section_name, filing_type)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screening_sessions (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP,
                total_analyzed INTEGER,
                pass_count INTEGER,
                close_count INTEGER,
                fail_count INTEGER,
                status TEXT DEFAULT 'running',
                processed_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0,
                current_symbol TEXT,
                algorithm TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screening_results (
                id SERIAL PRIMARY KEY,
                session_id INTEGER,
                symbol TEXT,
                company_name TEXT,
                country TEXT,
                market_cap REAL,
                sector TEXT,
                ipo_year INTEGER,
                price REAL,
                pe_ratio REAL,
                peg_ratio REAL,
                debt_to_equity REAL,
                institutional_ownership REAL,
                dividend_yield REAL,
                earnings_cagr REAL,
                revenue_cagr REAL,
                consistency_score REAL,
                peg_status TEXT,
                peg_score REAL,
                debt_status TEXT,
                debt_score REAL,
                institutional_ownership_status TEXT,
                institutional_ownership_score REAL,
                overall_status TEXT,
                FOREIGN KEY (session_id) REFERENCES screening_sessions(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_sources (
                id SERIAL PRIMARY KEY,
                message_id INTEGER NOT NULL,
                section_name TEXT NOT NULL,
                filing_type TEXT,
                filing_date TEXT,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT
            )
        """)

        conn.commit()

    def save_stock_basic(self, symbol: str, company_name: str, exchange: str, sector: str = None,
                        country: str = None, ipo_year: int = None):
        sql = """
            INSERT INTO stocks (symbol, company_name, exchange, sector, country, ipo_year, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                exchange = EXCLUDED.exchange,
                sector = EXCLUDED.sector,
                country = EXCLUDED.country,
                ipo_year = EXCLUDED.ipo_year,
                last_updated = EXCLUDED.last_updated
        """
        args = (symbol, company_name, exchange, sector, country, ipo_year, datetime.now())
        self.write_queue.put((sql, args))

    def save_stock_metrics(self, symbol: str, metrics: Dict[str, Any]):
        sql = """
            INSERT INTO stock_metrics
            (symbol, price, pe_ratio, market_cap, debt_to_equity, institutional_ownership, revenue, dividend_yield, beta, total_debt, interest_expense, effective_tax_rate, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                price = EXCLUDED.price,
                pe_ratio = EXCLUDED.pe_ratio,
                market_cap = EXCLUDED.market_cap,
                debt_to_equity = EXCLUDED.debt_to_equity,
                institutional_ownership = EXCLUDED.institutional_ownership,
                revenue = EXCLUDED.revenue,
                dividend_yield = EXCLUDED.dividend_yield,
                beta = EXCLUDED.beta,
                total_debt = EXCLUDED.total_debt,
                interest_expense = EXCLUDED.interest_expense,
                effective_tax_rate = EXCLUDED.effective_tax_rate,
                last_updated = EXCLUDED.last_updated
        """
        args = (
            symbol,
            metrics.get('price'),
            metrics.get('pe_ratio'),
            metrics.get('market_cap'),
            metrics.get('debt_to_equity'),
            metrics.get('institutional_ownership'),
            metrics.get('revenue'),
            metrics.get('dividend_yield'),
            metrics.get('beta'),
            metrics.get('total_debt'),
            metrics.get('interest_expense'),
            metrics.get('effective_tax_rate'),
            datetime.now()
        )
        self.write_queue.put((sql, args))

    def save_earnings_history(self, symbol: str, year: int, eps: float, revenue: float, fiscal_end: Optional[str] = None, debt_to_equity: Optional[float] = None, period: str = 'annual', net_income: Optional[float] = None, dividend_amount: Optional[float] = None, dividend_yield: Optional[float] = None, operating_cash_flow: Optional[float] = None, capital_expenditures: Optional[float] = None, free_cash_flow: Optional[float] = None):
        sql = """
            INSERT INTO earnings_history
            (symbol, year, earnings_per_share, revenue, fiscal_end, debt_to_equity, period, net_income, dividend_amount, dividend_yield, operating_cash_flow, capital_expenditures, free_cash_flow, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, year, period) DO UPDATE SET
                earnings_per_share = EXCLUDED.earnings_per_share,
                revenue = EXCLUDED.revenue,
                fiscal_end = EXCLUDED.fiscal_end,
                debt_to_equity = EXCLUDED.debt_to_equity,
                net_income = EXCLUDED.net_income,
                dividend_amount = EXCLUDED.dividend_amount,
                dividend_yield = EXCLUDED.dividend_yield,
                operating_cash_flow = EXCLUDED.operating_cash_flow,
                capital_expenditures = EXCLUDED.capital_expenditures,
                free_cash_flow = EXCLUDED.free_cash_flow,
                last_updated = EXCLUDED.last_updated
        """
        args = (symbol, year, eps, revenue, fiscal_end, debt_to_equity, period, net_income, dividend_amount, dividend_yield, operating_cash_flow, capital_expenditures, free_cash_flow, datetime.now())
        self.write_queue.put((sql, args))

    def get_stock_metrics(self, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sm.*, s.company_name, s.exchange, s.sector, s.country, s.ipo_year
            FROM stock_metrics sm
            JOIN stocks s ON sm.symbol = s.symbol
            WHERE sm.symbol = %s
        """, (symbol,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return None

        return {
            'symbol': row[0],
            'price': row[1],
            'pe_ratio': row[2],
            'market_cap': row[3],
            'debt_to_equity': row[4],
            'institutional_ownership': row[5],
            'revenue': row[6],
            'dividend_yield': row[7],
            'last_updated': row[8],
            'beta': row[9],
            'total_debt': row[10],
            'interest_expense': row[11],
            'effective_tax_rate': row[12],
            'company_name': row[13],
            'exchange': row[14],
            'sector': row[15],
            'country': row[16],
            'ipo_year': row[17]
        }

    def get_earnings_history(self, symbol: str, period_type: str = 'annual') -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()

        if period_type == 'quarterly':
            where_clause = "WHERE symbol = %s AND period IN ('Q1', 'Q2', 'Q3', 'Q4')"
        else:
            where_clause = "WHERE symbol = %s AND period = 'annual'"

        cursor.execute(f"""
            SELECT year, earnings_per_share, revenue, fiscal_end, debt_to_equity, period, net_income, dividend_amount, dividend_yield, operating_cash_flow, capital_expenditures, free_cash_flow, last_updated
            FROM earnings_history
            {where_clause}
            ORDER BY year DESC, period
        """, (symbol,))
        rows = cursor.fetchall()
        self.return_connection(conn)

        return [
            {
                'year': row[0],
                'eps': row[1],
                'revenue': row[2],
                'fiscal_end': row[3],
                'debt_to_equity': row[4],
                'period': row[5],
                'net_income': row[6],
                'dividend_amount': row[7],
                'dividend_yield': row[8],
                'operating_cash_flow': row[9],
                'capital_expenditures': row[10],
                'free_cash_flow': row[11],
                'last_updated': row[12]
            }
            for row in rows
        ]

    def is_cache_valid(self, symbol: str, max_age_hours: int = 24) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT last_updated FROM stock_metrics WHERE symbol = %s
        """, (symbol,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return False

        last_updated = row[0]
        age_hours = (datetime.now() - last_updated).total_seconds() / 3600
        return age_hours < max_age_hours

    def get_all_cached_stocks(self) -> List[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")
        rows = cursor.fetchall()
        self.return_connection(conn)

        return [row[0] for row in rows]

    def save_lynch_analysis(self, symbol: str, analysis_text: str, model_version: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO lynch_analyses
            (symbol, analysis_text, generated_at, model_version)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE SET
                analysis_text = EXCLUDED.analysis_text,
                generated_at = EXCLUDED.generated_at,
                model_version = EXCLUDED.model_version
        """, (symbol, analysis_text, datetime.now(), model_version))
        conn.commit()
        self.return_connection(conn)

    def get_lynch_analysis(self, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, analysis_text, generated_at, model_version
            FROM lynch_analyses
            WHERE symbol = %s
        """, (symbol,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return None

        return {
            'symbol': row[0],
            'analysis_text': row[1],
            'generated_at': row[2],
            'model_version': row[3]
        }

    def set_chart_analysis(self, symbol: str, section: str, analysis_text: str, model_version: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chart_analyses
            (symbol, section, analysis_text, generated_at, model_version)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (symbol, section) DO UPDATE SET
                analysis_text = EXCLUDED.analysis_text,
                generated_at = EXCLUDED.generated_at,
                model_version = EXCLUDED.model_version
        """, (symbol, section, analysis_text, datetime.now(), model_version))
        conn.commit()
        self.return_connection(conn)

    def get_chart_analysis(self, symbol: str, section: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, section, analysis_text, generated_at, model_version
            FROM chart_analyses
            WHERE symbol = %s AND section = %s
        """, (symbol, section))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return None

        return {
            'symbol': row[0],
            'section': row[1],
            'analysis_text': row[2],
            'generated_at': row[3],
            'model_version': row[4]
        }

    def create_session(self, algorithm: str, total_count: int, total_analyzed: int = 0, pass_count: int = 0, close_count: int = 0, fail_count: int = 0) -> int:
        """Create a new screening session with initial status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO screening_sessions (
                created_at, algorithm, total_count, processed_count,
                total_analyzed, pass_count, close_count, fail_count, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (datetime.now(), algorithm, total_count, 0, total_analyzed, pass_count, close_count, fail_count, 'running'))
        session_id = cursor.fetchone()[0]
        conn.commit()
        self.return_connection(conn)
        return session_id

    def update_session_progress(self, session_id: int, processed_count: int, current_symbol: str = None):
        """Update screening session progress"""
        sql = """
            UPDATE screening_sessions
            SET processed_count = %s, current_symbol = %s
            WHERE id = %s
        """
        args = (processed_count, current_symbol, session_id)
        self.write_queue.put((sql, args))

    def update_session_total_count(self, session_id: int, total_count: int):
        """Update session total count"""
        sql = "UPDATE screening_sessions SET total_count = %s WHERE id = %s"
        args = (total_count, session_id)
        self.write_queue.put((sql, args))

    def complete_session(self, session_id: int, total_analyzed: int, pass_count: int, close_count: int, fail_count: int):
        """Mark session as complete with final counts"""
        sql = """
            UPDATE screening_sessions
            SET status = 'complete',
                total_analyzed = %s,
                pass_count = %s,
                close_count = %s,
                fail_count = %s,
                processed_count = total_count
            WHERE id = %s
        """
        args = (total_analyzed, pass_count, close_count, fail_count, session_id)
        self.write_queue.put((sql, args))

    def cancel_session(self, session_id: int):
        """Mark session as cancelled"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE screening_sessions
            SET status = 'cancelled'
            WHERE id = %s
        """, (session_id,))
        conn.commit()
        self.return_connection(conn)

    def get_session_progress(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get current progress of a screening session"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_at, algorithm, status, processed_count, total_count,
                       current_symbol, total_analyzed, pass_count, close_count, fail_count
                FROM screening_sessions
                WHERE id = %s
            """, (session_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'id': row[0],
                'created_at': row[1],
                'algorithm': row[2],
                'status': row[3],
                'processed_count': row[4],
                'total_count': row[5],
                'current_symbol': row[6],
                'total_analyzed': row[7],
                'pass_count': row[8],
                'close_count': row[9],
                'fail_count': row[10]
            }
        finally:
            self.return_connection(conn)

    def get_session_results(self, session_id: int) -> List[Dict[str, Any]]:
        """Get all results for a screening session"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, company_name, country, market_cap, sector, ipo_year,
                   price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership,
                   dividend_yield, earnings_cagr, revenue_cagr, consistency_score,
                   peg_status, debt_status, institutional_ownership_status, overall_status
            FROM screening_results
            WHERE session_id = %s
            ORDER BY id ASC
        """, (session_id,))
        rows = cursor.fetchall()
        self.return_connection(conn)

        results = []
        for row in rows:
            results.append({
                'symbol': row[0],
                'company_name': row[1],
                'country': row[2],
                'market_cap': row[3],
                'sector': row[4],
                'ipo_year': row[5],
                'price': row[6],
                'pe_ratio': row[7],
                'peg_ratio': row[8],
                'debt_to_equity': row[9],
                'institutional_ownership': row[10],
                'dividend_yield': row[11],
                'earnings_cagr': row[12],
                'revenue_cagr': row[13],
                'consistency_score': row[14],
                'peg_status': row[15],
                'debt_status': row[16],
                'institutional_ownership_status': row[17],
                'overall_status': row[18]
            })

        return results

    def save_screening_result(self, session_id: int, result_data: Dict[str, Any]):
        sql_delete = """
            DELETE FROM screening_results
            WHERE session_id = %s AND symbol = %s
        """
        args_delete = (session_id, result_data.get('symbol'))
        self.write_queue.put((sql_delete, args_delete))

        sql_insert = """
            INSERT INTO screening_results
            (session_id, symbol, company_name, country, market_cap, sector, ipo_year,
             price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership, dividend_yield,
             earnings_cagr, revenue_cagr, consistency_score,
             peg_status, peg_score, debt_status, debt_score,
             institutional_ownership_status, institutional_ownership_score, overall_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        args_insert = (
            session_id,
            result_data.get('symbol'),
            result_data.get('company_name'),
            result_data.get('country'),
            result_data.get('market_cap'),
            result_data.get('sector'),
            result_data.get('ipo_year'),
            result_data.get('price'),
            result_data.get('pe_ratio'),
            result_data.get('peg_ratio'),
            result_data.get('debt_to_equity'),
            result_data.get('institutional_ownership'),
            result_data.get('dividend_yield'),
            result_data.get('earnings_cagr'),
            result_data.get('revenue_cagr'),
            result_data.get('consistency_score'),
            result_data.get('peg_status'),
            result_data.get('peg_score'),
            result_data.get('debt_status'),
            result_data.get('debt_score'),
            result_data.get('institutional_ownership_status'),
            result_data.get('institutional_ownership_score'),
            result_data.get('overall_status')
        )
        self.write_queue.put((sql_insert, args_insert))

    def get_latest_session(self) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, created_at, total_analyzed, pass_count, close_count, fail_count
            FROM screening_sessions
            ORDER BY created_at DESC
            LIMIT 1
        """)
        session_row = cursor.fetchone()

        if not session_row:
            self.return_connection(conn)
            return None

        session_id = session_row[0]

        cursor.execute("""
            SELECT symbol, company_name, country, market_cap, sector, ipo_year,
                   price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership, dividend_yield,
                   earnings_cagr, revenue_cagr, consistency_score,
                   peg_status, peg_score, debt_status, debt_score,
                   institutional_ownership_status, institutional_ownership_score, overall_status
            FROM screening_results
            WHERE session_id = %s
        """, (session_id,))
        result_rows = cursor.fetchall()

        self.return_connection(conn)

        results = []
        for row in result_rows:
            results.append({
                'symbol': row[0],
                'company_name': row[1],
                'country': row[2],
                'market_cap': row[3],
                'sector': row[4],
                'ipo_year': row[5],
                'price': row[6],
                'pe_ratio': row[7],
                'peg_ratio': row[8],
                'debt_to_equity': row[9],
                'institutional_ownership': row[10],
                'dividend_yield': row[11],
                'earnings_cagr': row[12],
                'revenue_cagr': row[13],
                'consistency_score': row[14],
                'peg_status': row[15],
                'peg_score': row[16],
                'debt_status': row[17],
                'debt_score': row[18],
                'institutional_ownership_status': row[19],
                'institutional_ownership_score': row[20],
                'overall_status': row[21]
            })

        return {
            'session_id': session_id,
            'created_at': session_row[1],
            'total_analyzed': session_row[2],
            'pass_count': session_row[3],
            'close_count': session_row[4],
            'fail_count': session_row[5],
            'results': results
        }

    def cleanup_old_sessions(self, keep_count: int = 2):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id FROM screening_sessions
            ORDER BY created_at DESC
            OFFSET %s
        """, (keep_count,))
        old_session_ids = [row[0] for row in cursor.fetchall()]

        for session_id in old_session_ids:
            cursor.execute("DELETE FROM screening_sessions WHERE id = %s", (session_id,))

        conn.commit()
        self.return_connection(conn)

    def add_to_watchlist(self, symbol: str):
        sql = """
            INSERT INTO watchlist (symbol, added_at)
            VALUES (%s, %s)
            ON CONFLICT (symbol) DO NOTHING
        """
        args = (symbol, datetime.now())
        self.write_queue.put((sql, args))

    def remove_from_watchlist(self, symbol: str):
        sql = "DELETE FROM watchlist WHERE symbol = %s"
        args = (symbol,)
        self.write_queue.put((sql, args))

    def get_watchlist(self) -> List[str]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC")
            symbols = [row[0] for row in cursor.fetchall()]
            return symbols
        finally:
            self.return_connection(conn)

    def is_in_watchlist(self, symbol: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM watchlist WHERE symbol = %s", (symbol,))
        result = cursor.fetchone()
        self.return_connection(conn)
        return result is not None

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

    def get_setting(self, key: str, default: Any = None) -> Any:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = %s", (key,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if row:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return row[0]
        return default

    def set_setting(self, key: str, value: Any, description: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()

        json_value = json.dumps(value)

        if description:
            cursor.execute("""
                INSERT INTO app_settings (key, value, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    description = EXCLUDED.description
            """, (key, json_value, description))
        else:
            cursor.execute("SELECT description FROM app_settings WHERE key = %s", (key,))
            row = cursor.fetchone()
            existing_desc = row[0] if row else None

            cursor.execute("""
                INSERT INTO app_settings (key, value, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value
            """, (key, json_value, existing_desc))

        conn.commit()
        self.return_connection(conn)

    def get_all_settings(self) -> Dict[str, Any]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value, description FROM app_settings")
        rows = cursor.fetchall()
        self.return_connection(conn)

        settings = {}
        for row in rows:
            try:
                value = json.loads(row[1])
            except json.JSONDecodeError:
                value = row[1]

            settings[row[0]] = {
                'value': value,
                'description': row[2]
            }
        return settings

    def init_default_settings(self):
        """Initialize default settings if they don't exist."""
        defaults = {
            'peg_excellent': {'value': 1.0, 'desc': 'Upper limit for Excellent PEG ratio'},
            'peg_good': {'value': 1.5, 'desc': 'Upper limit for Good PEG ratio'},
            'peg_fair': {'value': 2.0, 'desc': 'Upper limit for Fair PEG ratio'},
            'debt_excellent': {'value': 0.5, 'desc': 'Upper limit for Excellent Debt/Equity'},
            'debt_good': {'value': 1.0, 'desc': 'Upper limit for Good Debt/Equity'},
            'debt_moderate': {'value': 2.0, 'desc': 'Upper limit for Moderate Debt/Equity'},
            'inst_own_min': {'value': 0.20, 'desc': 'Minimum ideal institutional ownership'},
            'inst_own_max': {'value': 0.60, 'desc': 'Maximum ideal institutional ownership'},
            'weight_peg': {'value': 0.50, 'desc': 'Weight for PEG Score in Weighted Algo'},
            'weight_consistency': {'value': 0.25, 'desc': 'Weight for Consistency in Weighted Algo'},
            'weight_debt': {'value': 0.15, 'desc': 'Weight for Debt Score in Weighted Algo'},
            'weight_ownership': {'value': 0.10, 'desc': 'Weight for Ownership in Weighted Algo'}
        }

        current_settings = self.get_all_settings()

        for key, data in defaults.items():
            if key not in current_settings:
                self.set_setting(key, data['value'], data['desc'])
