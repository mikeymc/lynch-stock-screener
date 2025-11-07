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
        return sqlite3.connect(self.db_path)

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

        # Migration: Add fiscal_end column if it doesn't exist
        cursor.execute("PRAGMA table_info(earnings_history)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'fiscal_end' not in columns:
            cursor.execute("ALTER TABLE earnings_history ADD COLUMN fiscal_end TEXT")

        conn.commit()
        conn.close()

    def save_stock_basic(self, symbol: str, company_name: str, exchange: str, sector: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO stocks (symbol, company_name, exchange, sector, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, company_name, exchange, sector, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def save_stock_metrics(self, symbol: str, metrics: Dict[str, Any]):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO stock_metrics
            (symbol, price, pe_ratio, market_cap, debt_to_equity, institutional_ownership, revenue, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            metrics.get('price'),
            metrics.get('pe_ratio'),
            metrics.get('market_cap'),
            metrics.get('debt_to_equity'),
            metrics.get('institutional_ownership'),
            metrics.get('revenue'),
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
            SELECT sm.*, s.company_name, s.exchange, s.sector
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
            'last_updated': row[7],
            'company_name': row[8],
            'exchange': row[9],
            'sector': row[10]
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
