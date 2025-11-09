# ABOUTME: Manages SQLite database for caching stock data and financial metrics
# ABOUTME: Provides schema and operations for storing and retrieving stock information

import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List


class Database:
    def __init__(self, db_path: str = "stocks.db"):
        self.db_path = db_path
        self.init_schema()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                symbol TEXT PRIMARY KEY,
                company_name TEXT,
                exchange TEXT,
                sector TEXT,
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
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS earnings_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                year INTEGER,
                earnings_per_share REAL,
                revenue REAL,
                fiscal_end TEXT,
                last_updated TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, year)
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
            CREATE TABLE IF NOT EXISTS screening_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP,
                total_analyzed INTEGER,
                pass_count INTEGER,
                close_count INTEGER,
                fail_count INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS screening_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                debt_status TEXT,
                institutional_ownership_status TEXT,
                overall_status TEXT,
                FOREIGN KEY (session_id) REFERENCES screening_sessions(id) ON DELETE CASCADE
            )
        """)

        # Migration: Add fiscal_end column if it doesn't exist
        cursor.execute("PRAGMA table_info(earnings_history)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'fiscal_end' not in columns:
            cursor.execute("ALTER TABLE earnings_history ADD COLUMN fiscal_end TEXT")

        # Migration: Add country and ipo_year columns to stocks table
        cursor.execute("PRAGMA table_info(stocks)")
        stocks_columns = [row[1] for row in cursor.fetchall()]
        if 'country' not in stocks_columns:
            cursor.execute("ALTER TABLE stocks ADD COLUMN country TEXT")
        if 'ipo_year' not in stocks_columns:
            cursor.execute("ALTER TABLE stocks ADD COLUMN ipo_year INTEGER")

        # Migration: Add dividend_yield column to stock_metrics table
        cursor.execute("PRAGMA table_info(stock_metrics)")
        metrics_columns = [row[1] for row in cursor.fetchall()]
        if 'dividend_yield' not in metrics_columns:
            cursor.execute("ALTER TABLE stock_metrics ADD COLUMN dividend_yield REAL")

        # Migration: Add dividend_yield column to screening_results table
        cursor.execute("PRAGMA table_info(screening_results)")
        results_columns = [row[1] for row in cursor.fetchall()]
        if 'dividend_yield' not in results_columns:
            cursor.execute("ALTER TABLE screening_results ADD COLUMN dividend_yield REAL")

        # Migration: Add score columns to screening_results table
        cursor.execute("PRAGMA table_info(screening_results)")
        results_columns = [row[1] for row in cursor.fetchall()]
        if 'peg_score' not in results_columns:
            cursor.execute("ALTER TABLE screening_results ADD COLUMN peg_score REAL")
        if 'debt_score' not in results_columns:
            cursor.execute("ALTER TABLE screening_results ADD COLUMN debt_score REAL")
        if 'institutional_ownership_score' not in results_columns:
            cursor.execute("ALTER TABLE screening_results ADD COLUMN institutional_ownership_score REAL")

        conn.commit()
        conn.close()

    def save_stock_basic(self, symbol: str, company_name: str, exchange: str, sector: str = None,
                        country: str = None, ipo_year: int = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO stocks (symbol, company_name, exchange, sector, country, ipo_year, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (symbol, company_name, exchange, sector, country, ipo_year, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def save_stock_metrics(self, symbol: str, metrics: Dict[str, Any]):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO stock_metrics
            (symbol, price, pe_ratio, market_cap, debt_to_equity, institutional_ownership, revenue, dividend_yield, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            metrics.get('price'),
            metrics.get('pe_ratio'),
            metrics.get('market_cap'),
            metrics.get('debt_to_equity'),
            metrics.get('institutional_ownership'),
            metrics.get('revenue'),
            metrics.get('dividend_yield'),
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()

    def save_earnings_history(self, symbol: str, year: int, eps: float, revenue: float, fiscal_end: Optional[str] = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO earnings_history
            (symbol, year, earnings_per_share, revenue, fiscal_end, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, year, eps, revenue, fiscal_end, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_stock_metrics(self, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sm.*, s.company_name, s.exchange, s.sector, s.country, s.ipo_year
            FROM stock_metrics sm
            JOIN stocks s ON sm.symbol = s.symbol
            WHERE sm.symbol = ?
        """, (symbol,))
        row = cursor.fetchone()
        conn.close()

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
            'company_name': row[9],
            'exchange': row[10],
            'sector': row[11],
            'country': row[12],
            'ipo_year': row[13]
        }

    def get_earnings_history(self, symbol: str) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT year, earnings_per_share, revenue, fiscal_end, last_updated
            FROM earnings_history
            WHERE symbol = ?
            ORDER BY year DESC
        """, (symbol,))
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                'year': row[0],
                'eps': row[1],
                'revenue': row[2],
                'fiscal_end': row[3],
                'last_updated': row[4]
            }
            for row in rows
        ]

    def is_cache_valid(self, symbol: str, max_age_hours: int = 24) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT last_updated FROM stock_metrics WHERE symbol = ?
        """, (symbol,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return False

        last_updated = datetime.fromisoformat(row[0])
        age_hours = (datetime.now() - last_updated).total_seconds() / 3600
        return age_hours < max_age_hours

    def get_all_cached_stocks(self) -> List[str]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")
        rows = cursor.fetchall()
        conn.close()

        return [row[0] for row in rows]

    def save_lynch_analysis(self, symbol: str, analysis_text: str, model_version: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO lynch_analyses
            (symbol, analysis_text, generated_at, model_version)
            VALUES (?, ?, ?, ?)
        """, (symbol, analysis_text, datetime.now().isoformat(), model_version))
        conn.commit()
        conn.close()

    def get_lynch_analysis(self, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT symbol, analysis_text, generated_at, model_version
            FROM lynch_analyses
            WHERE symbol = ?
        """, (symbol,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'symbol': row[0],
            'analysis_text': row[1],
            'generated_at': row[2],
            'model_version': row[3]
        }

    def create_session(self, total_analyzed: int, pass_count: int, close_count: int, fail_count: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO screening_sessions (created_at, total_analyzed, pass_count, close_count, fail_count)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), total_analyzed, pass_count, close_count, fail_count))
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return session_id

    def save_screening_result(self, session_id: int, result_data: Dict[str, Any]):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO screening_results
            (session_id, symbol, company_name, country, market_cap, sector, ipo_year,
             price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership, dividend_yield,
             earnings_cagr, revenue_cagr, consistency_score,
             peg_status, peg_score, debt_status, debt_score,
             institutional_ownership_status, institutional_ownership_score, overall_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
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
        ))
        conn.commit()
        conn.close()

    def get_latest_session(self) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get the latest session
        cursor.execute("""
            SELECT id, created_at, total_analyzed, pass_count, close_count, fail_count
            FROM screening_sessions
            ORDER BY created_at DESC
            LIMIT 1
        """)
        session_row = cursor.fetchone()

        if not session_row:
            conn.close()
            return None

        session_id = session_row[0]

        # Get all results for this session
        cursor.execute("""
            SELECT symbol, company_name, country, market_cap, sector, ipo_year,
                   price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership, dividend_yield,
                   earnings_cagr, revenue_cagr, consistency_score,
                   peg_status, peg_score, debt_status, debt_score,
                   institutional_ownership_status, institutional_ownership_score, overall_status
            FROM screening_results
            WHERE session_id = ?
        """, (session_id,))
        result_rows = cursor.fetchall()

        conn.close()

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

        # Get IDs of sessions to delete (all except the keep_count most recent)
        cursor.execute("""
            SELECT id FROM screening_sessions
            ORDER BY created_at DESC
            LIMIT -1 OFFSET ?
        """, (keep_count,))
        old_session_ids = [row[0] for row in cursor.fetchall()]

        # Delete old sessions (CASCADE will delete associated results)
        for session_id in old_session_ids:
            cursor.execute("DELETE FROM screening_sessions WHERE id = ?", (session_id,))

        conn.commit()
        conn.close()
