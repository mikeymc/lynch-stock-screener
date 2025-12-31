# ABOUTME: Manages PostgreSQL database for caching stock data and financial metrics
# ABOUTME: Provides schema and operations for storing and retrieving stock information

import psycopg
from psycopg_pool import ConnectionPool
import threading
import os
import queue
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Set
import json

logger = logging.getLogger(__name__)


class Database:
    def __init__(self,
                 host: str = "localhost",
                 port: int = 5432,
                 database: str = "lynch_stocks",
                 user: str = "lynch",
                 password: str = "lynch_dev_password"):

        # Build connection string with keepalives
        self.conninfo = (
            f"host={host} port={port} dbname={database} user={user} password={password} "
            f"keepalives=1 keepalives_idle=30 keepalives_interval=10 keepalives_count=5"
        )
        self.host = host
        self.port = port
        self.database = database

        self._lock = threading.Lock()
        self._initializing = True

        # Connection pool for concurrent reads
        # Pool size must accommodate parallel screening workers (40) + some overhead
        # Can be overridden via DB_POOL_SIZE env var (useful for tests)
        self.pool_size = int(os.environ.get('DB_POOL_SIZE', 50))
        min_connections = min(5, self.pool_size)  # Don't exceed pool_size
        logger.info(f"Creating database connection pool: {host}:{port}/{database} (pool_size={self.pool_size}, min={min_connections})")
        
        # psycopg3 ConnectionPool with built-in health checking
        # The 'check' callback validates connections before handing to clients
        self.connection_pool = ConnectionPool(
            conninfo=self.conninfo,
            min_size=min_connections,
            max_size=self.pool_size,
            check=ConnectionPool.check_connection,  # Built-in health check
            max_lifetime=3600,  # Recycle connections after 1 hour
            max_idle=300,  # Close idle connections after 5 minutes
            open=True,  # Open pool immediately on creation
        )
        logger.info("Database connection pool created successfully")

        # Connection pool monitoring
        self._pool_stats_lock = threading.Lock()
        self._connections_checked_out = 0
        self._connections_returned = 0
        self._connection_errors = 0
        self._peak_connections_in_use = 0
        self._current_connections_in_use = 0

        # Queue for database write operations
        self.write_queue = queue.Queue()
        self.write_batch_size = 50
        
        # Cache from symbol lookups (for FK validation)
        self._symbol_cache: Optional[Set[str]] = None
        self._symbol_cache_lock = threading.Lock()

        # Initialize schema
        logger.info("Initializing database schema...")
        init_conn = self.connection_pool.getconn()
        try:
            self._init_schema_with_connection(init_conn)
            logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}", exc_info=True)
            raise
        finally:
            self.connection_pool.putconn(init_conn)

        self._initializing = False

        # Start background writer thread
        logger.info("Starting background writer thread...")
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        logger.info("Database writer thread started successfully")

    def flush(self):
        """Wait for all pending writes to complete and commit"""
        self.write_queue.put("FLUSH")
        self.write_queue.join()

    def get_connection(self):
        """Get a connection from the pool.
        
        psycopg3's ConnectionPool with check=ConnectionPool.check_connection
        automatically validates connections before returning them, so we no
        longer need manual validation here.
        """
        try:
            conn = self.connection_pool.getconn()

            with self._pool_stats_lock:
                self._connections_checked_out += 1
                self._current_connections_in_use += 1
                if self._current_connections_in_use > self._peak_connections_in_use:
                    self._peak_connections_in_use = self._current_connections_in_use

                # Warn if pool usage is high
                usage_pct = (self._current_connections_in_use / self.pool_size) * 100
                if usage_pct >= 80:
                    logger.warning(f"Connection pool usage at {usage_pct:.1f}% ({self._current_connections_in_use}/{self.pool_size})")
            return conn
        except Exception as e:
            with self._pool_stats_lock:
                self._connection_errors += 1
            logger.error(f"Error getting connection from pool: {e}")
            raise

    def return_connection(self, conn):
        """Return a connection to the pool"""
        try:
            # Ensure connection is in idle state (no uncommitted transaction)
            # psycopg3 pool warns if connections are returned with active transactions
            if conn and not conn.closed:
                conn.rollback()
            self.connection_pool.putconn(conn)
            with self._pool_stats_lock:
                self._connections_returned += 1
                self._current_connections_in_use -= 1
        except Exception as e:
            with self._pool_stats_lock:
                self._connection_errors += 1
            logger.error(f"Error returning connection to pool: {e}")
            raise
    
    def _symbol_exists(self, symbol: str) -> bool:
        """Check if a symbol exists in the stocks table.
        
        Uses a cached Set for efficiency during batch operations.
        Cache is lazily initialized on first call and refreshed if miss.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            True if symbol exists in stocks table, False otherwise
        """
        with self._symbol_cache_lock:
            # Lazy init: load all symbols on first use
            if self._symbol_cache is None:
                conn = self.get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT symbol FROM stocks")
                    self._symbol_cache = {row[0] for row in cursor.fetchall()}
                finally:
                    self.return_connection(conn)
            
            # Fast check against cache
            if symbol in self._symbol_cache:
                return True
            
            # Cache miss - check DB directly (symbol might have been added recently)
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM stocks WHERE symbol = %s LIMIT 1", (symbol,))
                exists = cursor.fetchone() is not None
                if exists:
                    self._symbol_cache.add(symbol)
                return exists
            finally:
                self.return_connection(conn)

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics for monitoring"""
        with self._pool_stats_lock:
            return {
                'pool_size': self.pool_size,
                'current_in_use': self._current_connections_in_use,
                'peak_in_use': self._peak_connections_in_use,
                'total_checked_out': self._connections_checked_out,
                'total_returned': self._connections_returned,
                'connection_errors': self._connection_errors,
                'usage_percent': (self._current_connections_in_use / self.pool_size) * 100 if self.pool_size > 0 else 0,
                'potential_leaks': self._connections_checked_out - self._connections_returned
            }

    def _sanitize_numpy_types(self, args):
        """Convert numpy types to Python native types for psycopg"""
        import numpy as np

        if isinstance(args, (list, tuple)):
            return type(args)(self._sanitize_numpy_types(arg) for arg in args)
        elif isinstance(args, dict):
            return {k: self._sanitize_numpy_types(v) for k, v in args.items()}
        elif isinstance(args, (np.integer, np.floating)):
            return args.item()
        elif isinstance(args, np.ndarray):
            return args.tolist()
        elif isinstance(args, np.bool_):
            return bool(args)
        else:
            return args

    def _writer_loop(self):
        """
        Background thread that handles all database writes sequentially.
        Implements batched writes for better performance with high concurrency.
        """
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        logger.info("Writer loop started with initial database connection")

        batch = []
        last_commit = time.time()
        reconnect_count = 0

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

                    if task == "FLUSH":
                        # Flush forces an immediate commit
                        if batch:
                            try:
                                for sql, args in batch:
                                    sanitized_args = self._sanitize_numpy_types(args)
                                    cursor.execute(sql, sanitized_args)
                                conn.commit()
                                last_commit = time.time()
                                batch = []
                            except Exception as e:
                                logger.error(f"Database batch write error during FLUSH: {e}", exc_info=True)
                                conn.rollback()
                                batch = []
                        self.write_queue.task_done()
                        continue

                    batch.append(task)
                    self.write_queue.task_done()

                should_commit = (
                    len(batch) >= self.write_batch_size or
                    (batch and time.time() - last_commit >= 2.0)
                )

                if should_commit:
                    try:
                        for sql, args in batch:
                            # Convert numpy types to Python native types
                            sanitized_args = self._sanitize_numpy_types(args)
                            cursor.execute(sql, sanitized_args)
                        conn.commit()
                        last_commit = time.time()
                        batch = []
                    except Exception as e:
                        error_msg = str(e).lower()
                        is_connection_error = any(msg in error_msg for msg in [
                            'closed', 'lost', 'terminated', 'broken', 'connection'
                        ])
                        
                        logger.error(f"Database batch write error (batch_size={len(batch)}): {e}", exc_info=True)
                        try:
                            conn.rollback()
                        except Exception as rollback_error:
                            logger.error(f"Rollback also failed: {rollback_error}")
                        batch = []
                        
                        # If it's a connection error, we need to reconnect
                        if is_connection_error:
                            logger.warning("Connection error during batch write - reconnecting")
                            try:
                                self.connection_pool.putconn(conn, close=True)
                            except Exception:
                                pass  # Ignore errors closing dead connection
                            try:
                                conn = self.connection_pool.getconn()
                                cursor = conn.cursor()
                                reconnect_count += 1
                                logger.info(f"Writer loop reconnected after batch error (reconnect #{reconnect_count})")
                            except Exception as reconnect_error:
                                logger.error(f"Failed to reconnect after batch error: {reconnect_error}")
                                time.sleep(5)

            except Exception as e:
                error_type = type(e).__name__
                logger.error(f"Fatal error in writer loop ({error_type}): {e}", exc_info=True)

                # Check if this is a connection error
                is_connection_error = any(msg in str(e).lower() for msg in [
                    'closed', 'lost', 'terminated', 'broken', 'connection'
                ])

                if is_connection_error:
                    logger.warning("Detected connection error - attempting to reconnect")
                    # Connection or cursor is broken - need to reconnect
                    try:
                        self.connection_pool.putconn(conn, close=True)
                        logger.info("Closed broken connection and returned to pool")
                    except Exception as close_error:
                        logger.error(f"Error while closing broken connection: {close_error}")

                    # Get a new connection and cursor
                    try:
                        conn = self.connection_pool.getconn()
                        cursor = conn.cursor()
                        reconnect_count += 1
                        # Clear batch since we lost the transaction
                        batch = []
                        logger.info(f"Writer loop reconnected successfully (reconnect #{reconnect_count})")
                    except Exception as reconnect_error:
                        logger.error(f"Failed to reconnect writer loop: {reconnect_error}", exc_info=True)
                        time.sleep(5)
                else:
                    # Non-connection error, just log and continue
                    logger.warning("Non-connection error in writer loop, continuing with same connection")
                    time.sleep(1)

        logger.info("Writer loop shutting down")
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

        # Migration: ensure stocks.symbol has primary key (for existing databases)
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE table_name = 'stocks'
            AND table_schema = 'public'
            AND constraint_type = 'PRIMARY KEY'
        """)
        if cursor.fetchone()[0] == 0:
            print("Migrating stocks: adding PRIMARY KEY...")
            cursor.execute("""
                DELETE FROM stocks a USING stocks b
                WHERE a.ctid < b.ctid AND a.symbol = b.symbol
            """)
            cursor.execute("ALTER TABLE stocks ADD PRIMARY KEY (symbol)")
            conn.commit()
            print("Migration complete: stocks PRIMARY KEY added")

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
                forward_pe REAL,
                forward_peg_ratio REAL,
                forward_eps REAL,
                insider_net_buying_6m REAL,
                analyst_rating TEXT,
                analyst_rating_score REAL,
                analyst_count INTEGER,
                price_target_high REAL,
                price_target_low REAL,
                price_target_mean REAL,
                short_ratio REAL,
                short_percent_float REAL,
                next_earnings_date DATE,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        # Migration: Add future indicator columns to stock_metrics
        cursor.execute("""
            DO $$
            BEGIN
                -- forward_pe
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'forward_pe') THEN
                    ALTER TABLE stock_metrics ADD COLUMN forward_pe REAL;
                END IF;
                
                -- forward_peg_ratio
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'forward_peg_ratio') THEN
                    ALTER TABLE stock_metrics ADD COLUMN forward_peg_ratio REAL;
                END IF;
                
                -- forward_eps
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'forward_eps') THEN
                    ALTER TABLE stock_metrics ADD COLUMN forward_eps REAL;
                END IF;
                
                -- insider_net_buying_6m
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'insider_net_buying_6m') THEN
                    ALTER TABLE stock_metrics ADD COLUMN insider_net_buying_6m REAL;
                END IF;
                
                -- analyst_rating
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'analyst_rating') THEN
                    ALTER TABLE stock_metrics ADD COLUMN analyst_rating TEXT;
                END IF;
                
                -- analyst_rating_score
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'analyst_rating_score') THEN
                    ALTER TABLE stock_metrics ADD COLUMN analyst_rating_score REAL;
                END IF;
                
                -- analyst_count
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'analyst_count') THEN
                    ALTER TABLE stock_metrics ADD COLUMN analyst_count INTEGER;
                END IF;
                
                -- price_target_high
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'price_target_high') THEN
                    ALTER TABLE stock_metrics ADD COLUMN price_target_high REAL;
                END IF;
                
                -- price_target_low
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'price_target_low') THEN
                    ALTER TABLE stock_metrics ADD COLUMN price_target_low REAL;
                END IF;
                
                -- price_target_mean
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'price_target_mean') THEN
                    ALTER TABLE stock_metrics ADD COLUMN price_target_mean REAL;
                END IF;
                
                -- short_ratio
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'short_ratio') THEN
                    ALTER TABLE stock_metrics ADD COLUMN short_ratio REAL;
                END IF;
                
                -- short_percent_float
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'short_percent_float') THEN
                    ALTER TABLE stock_metrics ADD COLUMN short_percent_float REAL;
                END IF;
                
                -- next_earnings_date
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'next_earnings_date') THEN
                    ALTER TABLE stock_metrics ADD COLUMN next_earnings_date DATE;
                END IF;
            END $$;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS insider_trades (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                name TEXT,
                position TEXT,
                transaction_date DATE,
                transaction_type TEXT,
                shares REAL,
                value REAL,
                filing_url TEXT,
                transaction_code TEXT,
                is_10b51_plan BOOLEAN DEFAULT FALSE,
                direct_indirect TEXT DEFAULT 'D',
                transaction_type_label TEXT,
                price_per_share REAL,
                is_derivative BOOLEAN DEFAULT FALSE,
                accession_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, name, transaction_date, transaction_type, shares)
            )
        """)

        # Migration: Add Form 4 enrichment columns to insider_trades
        cursor.execute("""
            DO $$
            BEGIN
                -- transaction_code (P/S/M/A/F/G etc.)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'transaction_code') THEN
                    ALTER TABLE insider_trades ADD COLUMN transaction_code TEXT;
                END IF;
                
                -- is_10b51_plan
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'is_10b51_plan') THEN
                    ALTER TABLE insider_trades ADD COLUMN is_10b51_plan BOOLEAN DEFAULT FALSE;
                END IF;
                
                -- direct_indirect (D or I)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'direct_indirect') THEN
                    ALTER TABLE insider_trades ADD COLUMN direct_indirect TEXT DEFAULT 'D';
                END IF;
                
                -- transaction_type_label (human-readable)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'transaction_type_label') THEN
                    ALTER TABLE insider_trades ADD COLUMN transaction_type_label TEXT;
                END IF;
                
                -- price_per_share
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'price_per_share') THEN
                    ALTER TABLE insider_trades ADD COLUMN price_per_share REAL;
                END IF;
                
                -- is_derivative
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'is_derivative') THEN
                    ALTER TABLE insider_trades ADD COLUMN is_derivative BOOLEAN DEFAULT FALSE;
                END IF;
                
                -- accession_number
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'accession_number') THEN
                    ALTER TABLE insider_trades ADD COLUMN accession_number TEXT;
                END IF;
                
                -- footnotes (array of footnote texts)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'footnotes') THEN
                    ALTER TABLE insider_trades ADD COLUMN footnotes TEXT[];
                END IF;
                
                -- shares_owned_after (post-transaction shares owned)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'shares_owned_after') THEN
                    ALTER TABLE insider_trades ADD COLUMN shares_owned_after REAL;
                END IF;
                
                -- ownership_change_pct (% of holdings this transaction represents)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'insider_trades' AND column_name = 'ownership_change_pct') THEN
                    ALTER TABLE insider_trades ADD COLUMN ownership_change_pct REAL;
                END IF;
            END $$;
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
                operating_cash_flow REAL,
                capital_expenditures REAL,
                free_cash_flow REAL,
                last_updated TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, year, period)
            )
        """)

        # Migration: Drop dividend_yield column if it exists (now computed on-the-fly)
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name = 'earnings_history' AND column_name = 'dividend_yield') THEN
                    ALTER TABLE earnings_history DROP COLUMN dividend_yield;
                END IF;
            END $$;
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
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                google_id TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                picture TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol TEXT PRIMARY KEY,
                added_at TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        # Migration: Add user_id to watchlist table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'watchlist' AND column_name = 'user_id') THEN
                    -- Add user_id column (nullable initially)
                    ALTER TABLE watchlist ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

                    -- Wipe existing data (as per requirement)
                    DELETE FROM watchlist;

                    -- Drop old primary key constraint
                    ALTER TABLE watchlist DROP CONSTRAINT watchlist_pkey;

                    -- Add id column as new primary key
                    ALTER TABLE watchlist ADD COLUMN id SERIAL PRIMARY KEY;

                    -- Add unique constraint on user_id and symbol
                    ALTER TABLE watchlist ADD CONSTRAINT watchlist_user_symbol_unique UNIQUE(user_id, symbol);

                    -- Make user_id required
                    ALTER TABLE watchlist ALTER COLUMN user_id SET NOT NULL;
                END IF;
            END $$;
        """)

        # Migration: Add user_id to chart_analyses table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'chart_analyses' AND column_name = 'user_id') THEN
                    -- Add user_id column (nullable initially)
                    ALTER TABLE chart_analyses ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

                    -- Wipe existing data (as per requirement)
                    DELETE FROM chart_analyses;

                    -- Drop old primary key constraint
                    ALTER TABLE chart_analyses DROP CONSTRAINT chart_analyses_pkey;

                    -- Add id column as new primary key
                    ALTER TABLE chart_analyses ADD COLUMN id SERIAL PRIMARY KEY;

                    -- Add unique constraint on user_id, symbol, and section
                    ALTER TABLE chart_analyses ADD CONSTRAINT chart_analyses_user_symbol_section_unique UNIQUE(user_id, symbol, section);

                    -- Make user_id required
                    ALTER TABLE chart_analyses ALTER COLUMN user_id SET NOT NULL;
                END IF;
            END $$;
        """)

        # Migration: Add user_id to lynch_analyses table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'lynch_analyses' AND column_name = 'user_id') THEN
                    -- Add user_id column (nullable initially)
                    ALTER TABLE lynch_analyses ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

                    -- Wipe existing data (as per requirement)
                    DELETE FROM lynch_analyses;

                    -- Drop old primary key constraint
                    ALTER TABLE lynch_analyses DROP CONSTRAINT lynch_analyses_pkey;

                    -- Add id column as new primary key
                    ALTER TABLE lynch_analyses ADD COLUMN id SERIAL PRIMARY KEY;

                    -- Add unique constraint on user_id and symbol
                    ALTER TABLE lynch_analyses ADD CONSTRAINT lynch_analyses_user_symbol_unique UNIQUE(user_id, symbol);

                    -- Make user_id required
                    ALTER TABLE lynch_analyses ALTER COLUMN user_id SET NOT NULL;
                END IF;
            END $$;
        """)

        # Create dcf_recommendations table for storing AI-generated DCF scenarios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dcf_recommendations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                symbol TEXT NOT NULL,
                recommendations_json TEXT NOT NULL,
                generated_at TIMESTAMP,
                model_version TEXT,
                CONSTRAINT dcf_recommendations_user_symbol_unique UNIQUE(user_id, symbol),
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

        # AI-generated summaries of filing sections
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS filing_section_summaries (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                section_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                filing_type TEXT NOT NULL,
                filing_date TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, section_name, filing_type)
            )
        """)

        # DEPRECATED: price_history table replaced by weekly_prices
        # Keeping commented for reference - will be dropped in migration
        # cursor.execute("""
        #     CREATE TABLE IF NOT EXISTS price_history (
        #         symbol TEXT,
        #         date DATE,
        #         close REAL,
        #         adjusted_close REAL,
        #         volume BIGINT,
        #         PRIMARY KEY (symbol, date),
        #         FOREIGN KEY (symbol) REFERENCES stocks(symbol)
        #     )
        # """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS weekly_prices (
                symbol TEXT,
                week_ending DATE,
                price REAL,
                last_updated TIMESTAMP,
                PRIMARY KEY (symbol, week_ending),
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                backtest_date DATE,
                years_back INTEGER,
                start_price REAL,
                end_price REAL,
                total_return REAL,
                historical_score REAL,
                historical_rating TEXT,
                peg_score REAL,
                debt_score REAL,
                ownership_score REAL,
                consistency_score REAL,
                peg_ratio REAL,
                earnings_cagr REAL,
                revenue_cagr REAL,
                debt_to_equity REAL,
                institutional_ownership REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, years_back)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS algorithm_configurations (
                id SERIAL PRIMARY KEY,
                name TEXT,
                weight_peg REAL,
                weight_consistency REAL,
                weight_debt REAL,
                weight_ownership REAL,
                peg_excellent REAL DEFAULT 1.0,
                peg_good REAL DEFAULT 1.5,
                peg_fair REAL DEFAULT 2.0,
                debt_excellent REAL DEFAULT 0.5,
                debt_good REAL DEFAULT 1.0,
                debt_moderate REAL DEFAULT 2.0,
                inst_own_min REAL DEFAULT 0.20,
                inst_own_max REAL DEFAULT 0.60,
                revenue_growth_excellent REAL DEFAULT 15.0,
                revenue_growth_good REAL DEFAULT 10.0,
                revenue_growth_fair REAL DEFAULT 5.0,
                income_growth_excellent REAL DEFAULT 15.0,
                income_growth_good REAL DEFAULT 10.0,
                income_growth_fair REAL DEFAULT 5.0,
                correlation_1yr REAL,
                correlation_3yr REAL,
                correlation_5yr REAL,
                is_active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add missing columns if they don't exist
        try:
            # List of new columns to check/add
            new_columns = [
                ('peg_excellent', 'REAL DEFAULT 1.0'),
                ('peg_good', 'REAL DEFAULT 1.5'),
                ('peg_fair', 'REAL DEFAULT 2.0'),
                ('debt_excellent', 'REAL DEFAULT 0.5'),
                ('debt_good', 'REAL DEFAULT 1.0'),
                ('debt_moderate', 'REAL DEFAULT 2.0'),
                ('inst_own_min', 'REAL DEFAULT 0.20'),
                ('inst_own_max', 'REAL DEFAULT 0.60'),
                ('revenue_growth_excellent', 'REAL DEFAULT 15.0'),
                ('revenue_growth_good', 'REAL DEFAULT 10.0'),
                ('revenue_growth_fair', 'REAL DEFAULT 5.0'),
                ('income_growth_excellent', 'REAL DEFAULT 15.0'),
                ('income_growth_good', 'REAL DEFAULT 10.0'),
                ('income_growth_fair', 'REAL DEFAULT 5.0')
            ]
            
            for col_name, col_def in new_columns:
                cursor.execute(f"""
                    DO $$ 
                    BEGIN 
                        BEGIN
                            ALTER TABLE algorithm_configurations ADD COLUMN {col_name} {col_def};
                        EXCEPTION
                            WHEN duplicate_column THEN NULL;
                        END;
                    END $$;
                """)
        except Exception as e:
            print(f"Migration warning: {e}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS optimization_runs (
                id SERIAL PRIMARY KEY,
                years_back INTEGER,
                iterations INTEGER,
                initial_correlation REAL,
                final_correlation REAL,
                improvement REAL,
                best_config_id INTEGER REFERENCES algorithm_configurations(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            CREATE TABLE IF NOT EXISTS background_jobs (
                id SERIAL PRIMARY KEY,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                claimed_by TEXT,
                claimed_at TIMESTAMP,
                claim_expires_at TIMESTAMP,
                params JSONB NOT NULL DEFAULT '{}',
                progress_pct INTEGER DEFAULT 0,
                progress_message TEXT,
                processed_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0,
                result JSONB,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_background_jobs_pending
            ON background_jobs(status, created_at)
            WHERE status = 'pending'
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
                overall_score REAL,
                scored_at TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES screening_sessions(id) ON DELETE CASCADE
            )
        """)

        # Migration: add overall_score and scored_at columns if missing
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'screening_results' AND column_name = 'overall_score') THEN
                    ALTER TABLE screening_results ADD COLUMN overall_score REAL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'screening_results' AND column_name = 'scored_at') THEN
                    ALTER TABLE screening_results ADD COLUMN scored_at TIMESTAMP;
                END IF;
            END $$;
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

        # Migration: Add user_id to conversations table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'conversations' AND column_name = 'user_id'
                ) THEN
                    -- Add user_id column
                    ALTER TABLE conversations ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;

                    -- Clear existing conversations since we can't assign user_id retroactively
                    DELETE FROM messages;
                    DELETE FROM conversations;

                    -- Make user_id required
                    ALTER TABLE conversations ALTER COLUMN user_id SET NOT NULL;
                END IF;
            END $$;
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

        # Migration: ensure app_settings.key has primary key (for existing databases)
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE table_name = 'app_settings'
            AND table_schema = 'public'
            AND constraint_type = 'PRIMARY KEY'
        """)
        if cursor.fetchone()[0] == 0:
            print("Migrating app_settings: adding PRIMARY KEY...")
            cursor.execute("""
                DELETE FROM app_settings a USING app_settings b
                WHERE a.ctid < b.ctid AND a.key = b.key
            """)
            cursor.execute("ALTER TABLE app_settings ADD PRIMARY KEY (key)")
            conn.commit()
            print("Migration complete: app_settings PRIMARY KEY added")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                finnhub_id INTEGER,
                headline TEXT,
                summary TEXT,
                source TEXT,
                url TEXT,
                image_url TEXT,
                category TEXT,
                datetime INTEGER,
                published_date TIMESTAMP,
                last_updated TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, finnhub_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS material_events (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                event_type TEXT NOT NULL,
                headline TEXT NOT NULL,
                description TEXT,
                source TEXT NOT NULL DEFAULT 'SEC',
                url TEXT,
                filing_date DATE,
                datetime INTEGER,
                published_date TIMESTAMP,
                sec_accession_number TEXT,
                sec_item_codes TEXT[],
                content_text TEXT,
                last_updated TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, sec_accession_number)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS earnings_transcripts (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                quarter TEXT NOT NULL,
                fiscal_year INTEGER,
                earnings_date DATE,
                transcript_text TEXT,
                summary TEXT,
                has_qa BOOLEAN DEFAULT false,
                participants TEXT[],
                source_url TEXT,
                last_updated TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, quarter, fiscal_year)
            )
        """)

        # Migration: add summary column to earnings_transcripts if missing
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'earnings_transcripts' AND column_name = 'summary') THEN
                    ALTER TABLE earnings_transcripts ADD COLUMN summary TEXT;
                END IF;
            END $$;
        """)

        # Material event summaries (AI-generated summaries for 8-K filings)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS material_event_summaries (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL REFERENCES material_events(id) ON DELETE CASCADE,
                summary TEXT NOT NULL,
                model_version TEXT,
                generated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(event_id)
            )
        """)

        # Analyst estimates (EPS and revenue forecasts from yfinance)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyst_estimates (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                period TEXT NOT NULL,
                eps_avg REAL,
                eps_low REAL,
                eps_high REAL,
                eps_growth REAL,
                eps_year_ago REAL,
                eps_num_analysts INTEGER,
                revenue_avg REAL,
                revenue_low REAL,
                revenue_high REAL,
                revenue_growth REAL,
                revenue_year_ago REAL,
                revenue_num_analysts INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, period)
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

    def ensure_stocks_exist_batch(self, market_data_cache: Dict[str, Dict[str, Any]]):
        """
        Ensure stocks exist in the database before caching related data.
        
        This prevents FK violations when caching jobs run in parallel with screening.
        Uses batch upsert for efficiency - inserts minimal stock records if missing,
        leaves existing records untouched (DO NOTHING).
        
        Args:
            market_data_cache: Dict from TradingView {symbol: {name, price, market_cap, ...}}
        """
        if not market_data_cache:
            return
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Batch upsert - insert if not exists, do nothing if already present
            # This is lighter than save_stock_basic since we don't update existing
            for symbol, data in market_data_cache.items():
                cursor.execute("""
                    INSERT INTO stocks (symbol, company_name, last_updated)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (symbol) DO NOTHING
                """, (symbol, data.get('name', symbol), datetime.now()))
            
            conn.commit()
        finally:
            self.return_connection(conn)

    def save_stock_metrics(self, symbol: str, metrics: Dict[str, Any]):
        """
        Save or update stock metrics.
        Supports partial updates - only keys present in metrics dict will be updated.
        """
        # Always update last_updated
        metrics['last_updated'] = datetime.now()
        
        # Valid columns map to ensure we only try to update valid fields
        valid_columns = {
            'price', 'pe_ratio', 'market_cap', 'debt_to_equity', 
            'institutional_ownership', 'revenue', 'dividend_yield', 
            'beta', 'total_debt', 'interest_expense', 'effective_tax_rate',
            'forward_pe', 'forward_peg_ratio', 'forward_eps',
            'insider_net_buying_6m', 'last_updated',
            'analyst_rating', 'analyst_rating_score', 'analyst_count',
            'price_target_high', 'price_target_low', 'price_target_mean',
            'short_ratio', 'short_percent_float', 'next_earnings_date'
        }
        
        # Filter metrics to only valid columns
        update_data = {k: v for k, v in metrics.items() if k in valid_columns}
        
        if not update_data:
            return

        # Build dynamic SQL
        columns = ['symbol'] + list(update_data.keys())
        placeholders = ['%s'] * len(columns)
        
        # Build SET clause for ON CONFLICT DO UPDATE
        # updates = [f"{col} = EXCLUDED.{col}" for col in update_data.keys()]
        # better: use explicit value passing to avoid issues with EXCLUDED if safe
        # actually EXCLUDED is standard for upsert. 
        updates = [f"{col} = EXCLUDED.{col}" for col in update_data.keys()]

        sql = f"""
            INSERT INTO stock_metrics ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT (symbol) DO UPDATE SET
                {', '.join(updates)}
        """
        
        args = [symbol] + list(update_data.values())
        
        self.write_queue.put((sql, tuple(args)))

    def save_insider_trades(self, symbol: str, trades: List[Dict[str, Any]]):
        """
        Batch save insider trades with Form 4 enrichment data.
        Supports both legacy fields and new Form 4 fields.
        """
        if not trades:
            return

        sql = """
            INSERT INTO insider_trades
            (symbol, name, position, transaction_date, transaction_type, shares, value, filing_url,
             transaction_code, is_10b51_plan, direct_indirect, transaction_type_label, price_per_share, 
             is_derivative, accession_number, footnotes, shares_owned_after, ownership_change_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, name, transaction_date, transaction_type, shares) 
            DO UPDATE SET
                transaction_code = EXCLUDED.transaction_code,
                is_10b51_plan = EXCLUDED.is_10b51_plan,
                direct_indirect = EXCLUDED.direct_indirect,
                transaction_type_label = EXCLUDED.transaction_type_label,
                price_per_share = EXCLUDED.price_per_share,
                is_derivative = EXCLUDED.is_derivative,
                accession_number = EXCLUDED.accession_number,
                footnotes = EXCLUDED.footnotes,
                shares_owned_after = EXCLUDED.shares_owned_after,
                ownership_change_pct = EXCLUDED.ownership_change_pct
        """
        
        for trade in trades:
            # Convert footnotes list to PostgreSQL array format
            footnotes = trade.get('footnotes', [])
            pg_footnotes = footnotes if footnotes else None
            
            args = (
                symbol,
                trade.get('name'),
                trade.get('position'),
                trade.get('transaction_date'),
                trade.get('transaction_type'),
                trade.get('shares'),
                trade.get('value'),
                trade.get('filing_url'),
                trade.get('transaction_code'),
                trade.get('is_10b51_plan', False),
                trade.get('direct_indirect', 'D'),
                trade.get('transaction_type_label'),
                trade.get('price_per_share'),
                trade.get('is_derivative', False),
                trade.get('accession_number'),
                pg_footnotes,
                trade.get('shares_owned_after'),
                trade.get('ownership_change_pct')
            )
            self.write_queue.put((sql, args))

    def get_insider_trades(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, position, transaction_date, transaction_type, shares, value, filing_url,
                       transaction_code, is_10b51_plan, direct_indirect, transaction_type_label, 
                       price_per_share, is_derivative, accession_number, footnotes,
                       shares_owned_after, ownership_change_pct
                FROM insider_trades
                WHERE symbol = %s
                ORDER BY transaction_date DESC
                LIMIT %s
            """, (symbol, limit))
            
            rows = cursor.fetchall()
            return [{
                'name': row[0],
                'position': row[1],
                'transaction_date': row[2].isoformat() if row[2] else None,
                'transaction_type': row[3],
                'shares': row[4],
                'value': row[5],
                'filing_url': row[6],
                'transaction_code': row[7],
                'is_10b51_plan': row[8] if row[8] is not None else False,
                'direct_indirect': row[9] or 'D',
                'transaction_type_label': row[10],
                'price_per_share': row[11],
                'is_derivative': row[12] if row[12] is not None else False,
                'accession_number': row[13],
                'footnotes': list(row[14]) if row[14] else [],
                'shares_owned_after': row[15],
                'ownership_change_pct': row[16]
            } for row in rows]
        finally:
            self.return_connection(conn)

    def save_earnings_history(self, symbol: str, year: int, eps: float, revenue: float, fiscal_end: Optional[str] = None, debt_to_equity: Optional[float] = None, period: str = 'annual', net_income: Optional[float] = None, dividend_amount: Optional[float] = None, operating_cash_flow: Optional[float] = None, capital_expenditures: Optional[float] = None, free_cash_flow: Optional[float] = None):
        sql = """
            INSERT INTO earnings_history
            (symbol, year, earnings_per_share, revenue, fiscal_end, debt_to_equity, period, net_income, dividend_amount, operating_cash_flow, capital_expenditures, free_cash_flow, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, year, period) DO UPDATE SET
                earnings_per_share = EXCLUDED.earnings_per_share,
                revenue = EXCLUDED.revenue,
                fiscal_end = EXCLUDED.fiscal_end,
                debt_to_equity = EXCLUDED.debt_to_equity,
                net_income = EXCLUDED.net_income,
                dividend_amount = EXCLUDED.dividend_amount,
                operating_cash_flow = EXCLUDED.operating_cash_flow,
                capital_expenditures = EXCLUDED.capital_expenditures,
                free_cash_flow = EXCLUDED.free_cash_flow,
                last_updated = EXCLUDED.last_updated
        """
        args = (symbol, year, eps, revenue, fiscal_end, debt_to_equity, period, net_income, dividend_amount, operating_cash_flow, capital_expenditures, free_cash_flow, datetime.now())
        self.write_queue.put((sql, args))

    def stock_exists(self, symbol: str) -> bool:
        """Check if a stock exists in the stocks table."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM stocks WHERE symbol = %s", (symbol,))
            return cursor.fetchone() is not None
        finally:
            self.return_connection(conn)

    def get_stock_metrics(self, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sm.*, s.company_name, s.exchange, s.sector, s.country, s.ipo_year
                FROM stock_metrics sm
                JOIN stocks s ON sm.symbol = s.symbol
                WHERE sm.symbol = %s
            """, (symbol,))
            row = cursor.fetchone()

            if not row:
                return None
            
            # Map row by index based on SELECT sm.* order
            # Current schema order:
            # symbol, price, pe_ratio, market_cap, debt_to_equity, institutional_ownership, revenue, dividend_yield, 
            # last_updated, beta, total_debt, interest_expense, effective_tax_rate, forward_pe, forward_peg_ratio, forward_eps, insider_net_buying_6m
            
            # Since sm.* can depend on DB column order, we should be careful. 
            # Ideally we'd name columns explicitly, but sm.* is convenient.
            # Let's assume the order matches CREATE TABLE and migration appends order.
            
            # 0: symbol
            # 1: price
            # 2: pe_ratio
            # 3: market_cap
            # 4: debt_to_equity
            # 5: institutional_ownership
            # 6: revenue
            # 7: dividend_yield
            # 8: last_updated
            # 9: beta
            # 10: total_debt
            # 11: interest_expense
            # 12: effective_tax_rate
            # 13: forward_pe
            # 14: forward_peg_ratio
            # 15: forward_eps
            # 16: insider_net_buying_6m
            # 17: company_name (joined)
            # 18: exchange (joined)
            # 19: sector (joined)
            # 20: country (joined)
            # 21: ipo_year (joined)

            # NOTE: If columns were added via migration they are at the end of the table
            # Python's cursor description could be used to map names safely, but for now we follow the append logic
            
            # Check length to determine if new columns exist (to support code running before migration completes fully or old cached connections)
            has_new_cols = len(row) >= 22 
            
            offset = 0 # base offset
            
            return {
                'symbol': row[0],
                'price': row[1],
                'pe_ratio': row[2],
                'market_cap': row[3],
                'debt_to_equity': row[4],
                'institutional_ownership': row[5],
                'revenue': row[6],\
                'dividend_yield': row[7],
                'last_updated': row[8],
                'beta': row[9],
                'total_debt': row[10],
                'interest_expense': row[11],
                'effective_tax_rate': row[12],
                'forward_pe': row[13] if has_new_cols else None,
                'forward_peg_ratio': row[14] if has_new_cols else None,
                'forward_eps': row[15] if has_new_cols else None,
                'insider_net_buying_6m': row[16] if has_new_cols else None,
                # Join columns are appended at the end of sm.* result
                'company_name': row[-5],
                'exchange': row[-4],
                'sector': row[-3],
                'country': row[-2],
                'ipo_year': row[-1]
            }
        finally:
            self.return_connection(conn)

    def get_earnings_history(self, symbol: str, period_type: str = 'annual') -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            if period_type == 'quarterly':
                where_clause = "WHERE symbol = %s AND period IN ('Q1', 'Q2', 'Q3', 'Q4')"
            else:
                where_clause = "WHERE symbol = %s AND period = 'annual'"

            cursor.execute(f"""
                SELECT year, earnings_per_share, revenue, fiscal_end, debt_to_equity, period, net_income, dividend_amount, operating_cash_flow, capital_expenditures, free_cash_flow, last_updated
                FROM earnings_history
                {where_clause}
                ORDER BY year DESC, period
            """, (symbol,))
            rows = cursor.fetchall()

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
                    'operating_cash_flow': row[8],
                    'capital_expenditures': row[9],
                    'free_cash_flow': row[10],
                    'last_updated': row[11]
                }
                for row in rows
            ]
        finally:
            self.return_connection(conn)


    def save_weekly_prices(self, symbol: str, weekly_data: Dict[str, Any]):
        """
        Save weekly price data.
        weekly_data dict with: 'dates' list and 'prices' list
        """
        if not weekly_data or not weekly_data.get('dates') or not weekly_data.get('prices'):
            return
        
        sql = """
            INSERT INTO weekly_prices
            (symbol, week_ending, price, last_updated)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol, week_ending) DO UPDATE SET
                price = EXCLUDED.price,
                last_updated = EXCLUDED.last_updated
        """
        
        # Batch write
        for date_str, price in zip(weekly_data['dates'], weekly_data['prices']):
            args = (symbol, date_str, price, datetime.now())
            self.write_queue.put((sql, args))
    
    def get_weekly_prices(self, symbol: str, start_year: int = None) -> Dict[str, Any]:
        """
        Get weekly price data for a symbol.
        
        Args:
            symbol: Stock symbol
            start_year: Optional start year filter
            
        Returns:
            Dict with 'dates' and 'prices' lists
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            query = "SELECT week_ending, price FROM weekly_prices WHERE symbol = %s"
            params = [symbol]
            
            if start_year:
                query += " AND EXTRACT(YEAR FROM week_ending) >= %s"
                params.append(start_year)
            
            query += " ORDER BY week_ending ASC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return {
                'dates': [row[0].strftime('%Y-%m-%d') for row in rows],
                'prices': [float(row[1]) for row in rows]
            }
        finally:
            self.return_connection(conn)
    
    def clear_weekly_prices(self, symbol: str = None) -> int:
        """
        Clear weekly price data for a symbol or all symbols.
        
        Use this when cached prices need to be refreshed (e.g., after fixing
        split adjustment issues).
        
        Args:
            symbol: Stock symbol to clear, or None to clear ALL weekly prices
            
        Returns:
            Number of rows deleted
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute("DELETE FROM weekly_prices WHERE symbol = %s", (symbol,))
                rows_deleted = cursor.rowcount
            else:
                # TRUNCATE doesn't return rowcount, so query count first
                cursor.execute("SELECT COUNT(*) FROM weekly_prices")
                rows_deleted = cursor.fetchone()[0]
                cursor.execute("TRUNCATE TABLE weekly_prices")
            
            conn.commit()
            return rows_deleted
        finally:
            self.return_connection(conn)
    
    # DEPRECATED: Use save_weekly_prices() instead
    # def save_price_point(self, symbol: str, date: str, price: float):
    #     """
    #     Save a single price point (e.g., fiscal year-end price).
    #     
    #     Args:
    #         symbol: Stock symbol
    #         date: Date in YYYY-MM-DD format
    #         price: Closing price
    #     """
    #     sql = """
    #         INSERT INTO price_history
    #         (symbol, date, close, adjusted_close, volume)
    #         VALUES (%s, %s, %s, %s, %s)
    #         ON CONFLICT (symbol, date) DO UPDATE SET
    #             close = EXCLUDED.close
    #     """
    #     args = (symbol, date, price, price, None)
    #     self.write_queue.put((sql, args))

    def is_cache_valid(self, symbol: str, max_age_hours: int = 24) -> bool:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_updated FROM stock_metrics WHERE symbol = %s
            """, (symbol,))
            row = cursor.fetchone()

            if not row:
                return False

            last_updated = row[0]
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            return age_hours < max_age_hours
        finally:
            self.return_connection(conn)

    def get_all_cached_stocks(self) -> List[str]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        finally:
            self.return_connection(conn)

    def save_lynch_analysis(self, user_id: int, symbol: str, analysis_text: str, model_version: str):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lynch_analyses
                (user_id, symbol, analysis_text, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol) DO UPDATE SET
                    analysis_text = EXCLUDED.analysis_text,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, analysis_text, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_lynch_analysis(self, user_id: int, symbol: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, analysis_text, generated_at, model_version
                FROM lynch_analyses
                WHERE user_id = %s AND symbol = %s
            """, (user_id, symbol))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'symbol': row[0],
                'analysis_text': row[1],
                'generated_at': row[2],
                'model_version': row[3]
            }
        finally:
            self.return_connection(conn)

    def set_chart_analysis(self, user_id: int, symbol: str, section: str, analysis_text: str, model_version: str):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chart_analyses
                (user_id, symbol, section, analysis_text, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol, section) DO UPDATE SET
                    analysis_text = EXCLUDED.analysis_text,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, section, analysis_text, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_chart_analysis(self, user_id: int, symbol: str, section: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, section, analysis_text, generated_at, model_version
                FROM chart_analyses
                WHERE user_id = %s AND symbol = %s AND section = %s
            """, (user_id, symbol, section))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'symbol': row[0],
                'section': row[1],
                'analysis_text': row[2],
                'generated_at': row[3],
                'model_version': row[4]
            }
        finally:
            self.return_connection(conn)

    def set_dcf_recommendations(self, user_id: int, symbol: str, recommendations: Dict[str, Any], model_version: str):
        """Save DCF recommendations for a user/symbol"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Store scenarios and reasoning as JSON
            recommendations_json = json.dumps(recommendations)
            cursor.execute("""
                INSERT INTO dcf_recommendations
                (user_id, symbol, recommendations_json, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol) DO UPDATE SET
                    recommendations_json = EXCLUDED.recommendations_json,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, recommendations_json, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_dcf_recommendations(self, user_id: int, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached DCF recommendations for a user/symbol"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, recommendations_json, generated_at, model_version
                FROM dcf_recommendations
                WHERE user_id = %s AND symbol = %s
            """, (user_id, symbol))
            row = cursor.fetchone()

            if not row:
                return None

            recommendations = json.loads(row[1])
            return {
                'symbol': row[0],
                'scenarios': recommendations.get('scenarios', {}),
                'reasoning': recommendations.get('reasoning', ''),
                'generated_at': row[2],
                'model_version': row[3]
            }
        finally:
            self.return_connection(conn)


    def create_session(self, algorithm: str, total_count: int, total_analyzed: int = 0, pass_count: int = 0, close_count: int = 0, fail_count: int = 0) -> int:
        """Create a new screening session with initial status"""
        conn = self.get_connection()
        try:
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
            return session_id
        finally:
            self.return_connection(conn)

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
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE screening_sessions
                SET status = 'cancelled'
                WHERE id = %s
            """, (session_id,))
            conn.commit()
        finally:
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
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, company_name, country, market_cap, sector, ipo_year,
                       price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership,
                       dividend_yield, earnings_cagr, revenue_cagr, consistency_score,
                       peg_status, debt_status, institutional_ownership_status, overall_status,
                       overall_score, scored_at
                FROM screening_results
                WHERE session_id = %s
                ORDER BY id ASC
            """, (session_id,))
            rows = cursor.fetchall()

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
                    'overall_status': row[18],
                    'overall_score': row[19],
                    'scored_at': row[20]
                })

            return results
        finally:
            self.return_connection(conn)

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
             institutional_ownership_status, institutional_ownership_score,
             overall_status, overall_score, scored_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            result_data.get('overall_status'),
            result_data.get('overall_score'),
            datetime.now()
        )
        self.write_queue.put((sql_insert, args_insert))

    def get_latest_session(self, search: str = None, page: int = 1, limit: int = 100, 
                           sort_by: str = 'overall_status', sort_dir: str = 'asc',
                           country_filter: str = None) -> Optional[Dict[str, Any]]:
        """
        Get the most recent screening session with paginated, sorted results.
        
        Args:
            search: Optional search filter for symbol/company name
            page: Page number for pagination (1-indexed)
            limit: Results per page
            sort_by: Column to sort by
            sort_dir: Sort direction ('asc' or 'desc')
            country_filter: Optional country code to filter by (e.g., 'US')
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, created_at, total_analyzed, pass_count, close_count, fail_count
                FROM screening_sessions
                ORDER BY created_at DESC
                LIMIT 1
            """)
            session_row = cursor.fetchone()

            if not session_row:
                return None

            session_id = session_row[0]

            # Whitelist of allowed sort columns to prevent SQL injection
            allowed_sort_columns = {
                'symbol', 'company_name', 'market_cap', 'price', 'pe_ratio', 'peg_ratio',
                'debt_to_equity', 'institutional_ownership', 'dividend_yield',
                'earnings_cagr', 'revenue_cagr', 'consistency_score', 'overall_status',
                'overall_score', 'peg_score', 'debt_score', 'institutional_ownership_score'
            }
            
            # Validate sort parameters
            if sort_by not in allowed_sort_columns:
                sort_by = 'overall_score'
            if sort_dir.lower() not in ('asc', 'desc'):
                sort_dir = 'desc'
            
            # Build base query
            base_query = """
                SELECT symbol, company_name, country, market_cap, sector, ipo_year,
                       price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership, dividend_yield,
                       earnings_cagr, revenue_cagr, consistency_score,
                       peg_status, peg_score, debt_status, debt_score,
                       institutional_ownership_status, institutional_ownership_score, overall_status,
                       overall_score
                FROM screening_results
                WHERE session_id = %s
            """
            params = [session_id]
            
            # Apply country filter if provided
            if country_filter:
                base_query += " AND country = %s"
                params.append(country_filter)
            
            if search:
                base_query += " AND (symbol ILIKE %s OR company_name ILIKE %s)"
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])
            
            # Get total count for pagination
            count_query = f"SELECT COUNT(*) FROM ({base_query}) AS filtered"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Add ordering and pagination
            # Special handling for overall_status - use CASE to rank properly
            # Also use status ranking as fallback when overall_score is NULL
            status_rank_expr = """CASE overall_status
                WHEN 'STRONG_BUY' THEN 1
                WHEN 'PASS' THEN 1
                WHEN 'BUY' THEN 2
                WHEN 'CLOSE' THEN 2
                WHEN 'HOLD' THEN 3
                WHEN 'CAUTION' THEN 4
                WHEN 'AVOID' THEN 5
                WHEN 'FAIL' THEN 5
                ELSE 6
            END"""
            
            if sort_by == 'overall_status':
                # Use status ranking for text-based status sorting
                order_expr = f"{status_rank_expr} {sort_dir.upper()}"
            elif sort_by == 'overall_score':
                # For overall_score, fall back to status ranking when score is NULL
                order_expr = f"COALESCE(overall_score, 0) {sort_dir.upper()}, {status_rank_expr} ASC"
            else:
                # Handle NULL values in sorting - always put them last (IS NULL ASC = false first, true last)
                order_expr = f"{sort_by} IS NULL ASC, {sort_by} {sort_dir.upper()}"
            
            query = base_query + f" ORDER BY {order_expr}"
            
            # Add pagination
            offset = (page - 1) * limit
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            result_rows = cursor.fetchall()

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
                    'overall_status': row[21],
                    'overall_score': row[22]
                })

            # Get status counts for full session (respects country filter, not search/pagination)
            status_count_query = """
                SELECT overall_status, COUNT(*) as count
                FROM screening_results
                WHERE session_id = %s
            """
            status_count_params = [session_id]
            
            if country_filter:
                status_count_query += " AND country = %s"
                status_count_params.append(country_filter)
            
            status_count_query += " GROUP BY overall_status"
            
            cursor.execute(status_count_query, status_count_params)
            status_rows = cursor.fetchall()
            status_counts = {row[0]: row[1] for row in status_rows if row[0]}

            return {
                'session_id': session_id,
                'created_at': session_row[1],
                'total_analyzed': session_row[2],
                'pass_count': session_row[3],
                'close_count': session_row[4],
                'fail_count': session_row[5],
                'results': results,
                'total_count': total_count,
                'page': page,
                'limit': limit,
                'total_pages': (total_count + limit - 1) // limit,  # Ceiling division
                'status_counts': status_counts  # e.g. {'STRONG_BUY': 50, 'BUY': 100, ...}
            }
        finally:
            self.return_connection(conn)

    def cleanup_old_sessions(self, keep_count: int = 2):
        conn = self.get_connection()
        try:
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
        finally:
            self.return_connection(conn)

    def create_user(self, google_id: str, email: str, name: str = None, picture: str = None) -> int:
        """Create a new user and return their user_id"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (google_id, email, name, picture, created_at, last_login)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (google_id) DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    picture = EXCLUDED.picture,
                    last_login = EXCLUDED.last_login
                RETURNING id
            """, (google_id, email, name, picture, datetime.now(), datetime.now()))
            user_id = cursor.fetchone()[0]
            conn.commit()
            return user_id
        finally:
            self.return_connection(conn)

    def get_user_by_google_id(self, google_id: str) -> Optional[Dict[str, Any]]:
        """Get user by Google ID"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("SELECT * FROM users WHERE google_id = %s", (google_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by user_id"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def update_last_login(self, user_id: int):
        """Update user's last login timestamp"""
        sql = "UPDATE users SET last_login = %s WHERE id = %s"
        args = (datetime.now(), user_id)
        self.write_queue.put((sql, args))

    def add_to_watchlist(self, user_id: int, symbol: str):
        sql = """
            INSERT INTO watchlist (user_id, symbol, added_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, symbol) DO NOTHING
        """
        args = (user_id, symbol, datetime.now())
        self.write_queue.put((sql, args))

    def remove_from_watchlist(self, user_id: int, symbol: str):
        sql = "DELETE FROM watchlist WHERE user_id = %s AND symbol = %s"
        args = (user_id, symbol)
        self.write_queue.put((sql, args))

    def get_watchlist(self, user_id: int) -> List[str]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM watchlist WHERE user_id = %s ORDER BY added_at DESC", (user_id,))
            symbols = [row[0] for row in cursor.fetchall()]
            return symbols
        finally:
            self.return_connection(conn)

    def is_in_watchlist(self, user_id: int, symbol: str) -> bool:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM watchlist WHERE user_id = %s AND symbol = %s", (user_id, symbol))
            result = cursor.fetchone()
            return result is not None
        finally:
            self.return_connection(conn)

    def get_screening_symbols(self, session_id: int) -> List[str]:
        """Get all symbols from a specific screening session."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT symbol FROM screening_results WHERE session_id = %s",
                (session_id,)
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.return_connection(conn)

    def update_screening_result_scores(
        self,
        symbol: str,
        overall_score: float = None,
        overall_status: str = None,
        peg_score: float = None,
        debt_score: float = None,
        institutional_ownership_score: float = None,
        scored_at: datetime = None
    ):
        """Update scores for all screening_results rows matching a symbol."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE screening_results
                SET overall_score = %s,
                    overall_status = %s,
                    peg_score = %s,
                    debt_score = %s,
                    institutional_ownership_score = %s,
                    scored_at = %s
                WHERE symbol = %s
            """, (
                overall_score,
                overall_status,
                peg_score,
                debt_score,
                institutional_ownership_score,
                scored_at or datetime.now(),
                symbol
            ))

            conn.commit()
            logger.info(f"Updated scores for {symbol} ({cursor.rowcount} rows affected)")

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update scores for {symbol}: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_latest_session_id(self) -> Optional[int]:
        """Get the ID of the most recent screening session."""
        session = self.get_latest_session()
        return session['id'] if session else None

    def get_stocks_ordered_by_score(self, limit: Optional[int] = None, country: Optional[str] = None) -> List[str]:
        """
        Get stock symbols from latest completed screening session, ordered by overall_status.
        
        Priority order: STRONG_BUY -> BUY -> HOLD -> CAUTION -> AVOID
        This ensures cache jobs prioritize the best-rated stocks first.
        
        Args:
            limit: Optional max number of symbols to return
            country: Optional country filter (e.g., 'United States')
            
        Returns:
            List of stock symbols ordered by priority
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Get latest completed session
            cursor.execute("""
                SELECT id FROM screening_sessions 
                WHERE status = 'complete' 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            session_row = cursor.fetchone()
            
            if not session_row:
                # No completed session - fall back to all stocks
                if country:
                    cursor.execute("SELECT symbol FROM stocks WHERE country = %s ORDER BY symbol", (country,))
                else:
                    cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")
                symbols = [row[0] for row in cursor.fetchall()]
                return symbols[:limit] if limit else symbols
            
            session_id = session_row[0]
            
            # Get symbols ordered by score priority
            query = """
                SELECT sr.symbol FROM screening_results sr
                JOIN stocks s ON sr.symbol = s.symbol
                WHERE sr.session_id = %s
            """
            params = [session_id]
            
            if country:
                query += " AND s.country = %s"
                params.append(country)
            
            query += """
                ORDER BY 
                    CASE sr.overall_status 
                        WHEN 'STRONG_BUY' THEN 1 
                        WHEN 'BUY' THEN 2 
                        WHEN 'HOLD' THEN 3 
                        WHEN 'CAUTION' THEN 4 
                        WHEN 'AVOID' THEN 5 
                        ELSE 6 
                    END ASC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query, params)
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.return_connection(conn)

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

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key, with optional default"""
        result = self.get_setting_full(key)
        return result['value'] if result else default

    def get_setting_full(self, key: str) -> Optional[Dict[str, Any]]:
        """Get complete setting record (key, value, description)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value, description FROM app_settings WHERE key = %s", (key,))
        result = cursor.fetchone()
        self.return_connection(conn)

        if result is None:
            return None
        else:
            return {
                'key': key,
                'value': json.loads(result[0]),
                'description': result[1]
            }

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

    def clear_material_events(self, symbol: str = None) -> int:
        """
        Clear material events (8-K) cache for a symbol or all symbols.
        
        Use this when cached 8-K content needs to be refreshed (e.g., after
        updating the content extraction logic to fetch EX-99.x exhibits).
        
        Args:
            symbol: Stock symbol to clear, or None to clear ALL material events
            
        Returns:
            Number of rows deleted
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute("DELETE FROM material_events WHERE symbol = %s", (symbol,))
                rows_deleted = cursor.rowcount
            else:
                # TRUNCATE doesn't return rowcount, so query count first
                cursor.execute("SELECT COUNT(*) FROM material_events")
                rows_deleted = cursor.fetchone()[0]
                cursor.execute("TRUNCATE TABLE material_events")
            
            conn.commit()
            return rows_deleted
        finally:
            self.return_connection(conn)

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

    def save_earnings_transcript(self, symbol: str, transcript_data: Dict[str, Any]):
        """
        Save an earnings call transcript.
        
        Args:
            symbol: Stock symbol
            transcript_data: Dict containing quarter, fiscal_year, earnings_date, 
                           transcript_text, has_qa, participants, source_url
        """
        sql = """
            INSERT INTO earnings_transcripts 
            (symbol, quarter, fiscal_year, earnings_date, transcript_text, has_qa, 
             participants, source_url, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (symbol, quarter, fiscal_year) DO UPDATE SET
                earnings_date = EXCLUDED.earnings_date,
                transcript_text = EXCLUDED.transcript_text,
                has_qa = EXCLUDED.has_qa,
                participants = EXCLUDED.participants,
                source_url = EXCLUDED.source_url,
                last_updated = NOW()
        """
        
        params = (
            symbol.upper(),
            transcript_data.get('quarter'),
            transcript_data.get('fiscal_year'),
            transcript_data.get('earnings_date'),
            transcript_data.get('transcript_text'),
            transcript_data.get('has_qa', False),
            transcript_data.get('participants', []),
            transcript_data.get('source_url'),
        )
        
        self.write_queue.put((sql, params))
        logger.info(f"Saved transcript for {symbol} {transcript_data.get('quarter')} {transcript_data.get('fiscal_year')}")

    def get_latest_earnings_transcript(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent earnings transcript for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Transcript dict or None if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, symbol, quarter, fiscal_year, earnings_date, transcript_text,
                   summary, has_qa, participants, source_url, last_updated
            FROM earnings_transcripts
            WHERE symbol = %s
            ORDER BY fiscal_year DESC, quarter DESC
            LIMIT 1
        """, (symbol.upper(),))
        
        row = cursor.fetchone()
        self.return_connection(conn)
        
        if not row:
            return None
        
        return {
            'id': row[0],
            'symbol': row[1],
            'quarter': row[2],
            'fiscal_year': row[3],
            'earnings_date': row[4].isoformat() if row[4] else None,
            'transcript_text': row[5],
            'summary': row[6],
            'has_qa': row[7],
            'participants': row[8] or [],
            'source_url': row[9],
            'last_updated': row[10].isoformat() if row[10] else None
        }

    def save_analyst_estimates(self, symbol: str, estimates_data: Dict[str, Any]):
        """
        Save analyst estimates for EPS and revenue.
        
        Args:
            symbol: Stock symbol
            estimates_data: Dict with period keys ('0q', '+1q', '0y', '+1y') containing:
                - eps_avg, eps_low, eps_high, eps_growth, eps_year_ago, eps_num_analysts
                - revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_year_ago, revenue_num_analysts
        """
        for period, data in estimates_data.items():
            if not data:
                continue
                
            sql = """
                INSERT INTO analyst_estimates 
                (symbol, period, eps_avg, eps_low, eps_high, eps_growth, eps_year_ago, eps_num_analysts,
                 revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_year_ago, revenue_num_analysts,
                 last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period) DO UPDATE SET
                    eps_avg = EXCLUDED.eps_avg,
                    eps_low = EXCLUDED.eps_low,
                    eps_high = EXCLUDED.eps_high,
                    eps_growth = EXCLUDED.eps_growth,
                    eps_year_ago = EXCLUDED.eps_year_ago,
                    eps_num_analysts = EXCLUDED.eps_num_analysts,
                    revenue_avg = EXCLUDED.revenue_avg,
                    revenue_low = EXCLUDED.revenue_low,
                    revenue_high = EXCLUDED.revenue_high,
                    revenue_growth = EXCLUDED.revenue_growth,
                    revenue_year_ago = EXCLUDED.revenue_year_ago,
                    revenue_num_analysts = EXCLUDED.revenue_num_analysts,
                    last_updated = NOW()
            """
            
            params = (
                symbol.upper(),
                period,
                data.get('eps_avg'),
                data.get('eps_low'),
                data.get('eps_high'),
                data.get('eps_growth'),
                data.get('eps_year_ago'),
                data.get('eps_num_analysts'),
                data.get('revenue_avg'),
                data.get('revenue_low'),
                data.get('revenue_high'),
                data.get('revenue_growth'),
                data.get('revenue_year_ago'),
                data.get('revenue_num_analysts'),
            )
            
            self.write_queue.put((sql, params))

    def get_analyst_estimates(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all analyst estimates for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dict keyed by period ('0q', '+1q', '0y', '+1y') with estimate data
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT period, eps_avg, eps_low, eps_high, eps_growth, eps_year_ago, eps_num_analysts,
                       revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_year_ago, 
                       revenue_num_analysts, last_updated
                FROM analyst_estimates
                WHERE symbol = %s
            """, (symbol.upper(),))
            
            rows = cursor.fetchall()
            
            result = {}
            for row in rows:
                result[row[0]] = {
                    'eps_avg': row[1],
                    'eps_low': row[2],
                    'eps_high': row[3],
                    'eps_growth': row[4],
                    'eps_year_ago': row[5],
                    'eps_num_analysts': row[6],
                    'revenue_avg': row[7],
                    'revenue_low': row[8],
                    'revenue_high': row[9],
                    'revenue_growth': row[10],
                    'revenue_year_ago': row[11],
                    'revenue_num_analysts': row[12],
                    'last_updated': row[13].isoformat() if row[13] else None
                }
            
            return result
        finally:
            self.return_connection(conn)

    def save_transcript_summary(self, symbol: str, quarter: str, fiscal_year: int, summary: str):
        """
        Save an AI-generated summary for an earnings transcript.
        
        Args:
            symbol: Stock symbol
            quarter: Quarter (e.g., "Q4")
            fiscal_year: Fiscal year
            summary: AI-generated summary text
        """
        sql = """
            UPDATE earnings_transcripts 
            SET summary = %s, last_updated = NOW()
            WHERE symbol = %s AND quarter = %s AND fiscal_year = %s
        """
        params = (summary, symbol.upper(), quarter, fiscal_year)
        
        self.write_queue.put((sql, params))
        logger.info(f"Saved transcript summary for {symbol} {quarter} {fiscal_year}")

    def get_earnings_transcripts(self, symbol: str, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Get recent earnings transcripts for a symbol.
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of transcripts to return (default 4 = 1 year)
            
        Returns:
            List of transcript dicts
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, symbol, quarter, fiscal_year, earnings_date, transcript_text,
                   has_qa, participants, source_url, last_updated
            FROM earnings_transcripts
            WHERE symbol = %s
            ORDER BY fiscal_year DESC, quarter DESC
            LIMIT %s
        """, (symbol.upper(), limit))
        
        rows = cursor.fetchall()
        self.return_connection(conn)
        
        return [
            {
                'id': row[0],
                'symbol': row[1],
                'quarter': row[2],
                'fiscal_year': row[3],
                'earnings_date': row[4].isoformat() if row[4] else None,
                'transcript_text': row[5],
                'has_qa': row[6],
                'participants': row[7] or [],
                'source_url': row[8],
                'last_updated': row[9].isoformat() if row[9] else None
            }
            for row in rows
        ]

    def set_setting(self, key: str, value: Any, description: str = None):
        logger.info(f"Setting configuration: key='{key}', value={value}")
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
        logger.info("Initializing default settings (only adds missing settings, does not overwrite existing)")
        defaults = {
            # PEG thresholds (existing)
            'peg_excellent': {'value': 1.0, 'desc': 'Upper limit for Excellent PEG ratio'},
            'peg_good': {'value': 1.5, 'desc': 'Upper limit for Good PEG ratio'},
            'peg_fair': {'value': 2.0, 'desc': 'Upper limit for Fair PEG ratio'},
            
            # Debt thresholds (existing)
            'debt_excellent': {'value': 0.5, 'desc': 'Upper limit for Excellent Debt/Equity'},
            'debt_good': {'value': 1.0, 'desc': 'Upper limit for Good Debt/Equity'},
            'debt_moderate': {'value': 2.0, 'desc': 'Upper limit for Moderate Debt/Equity'},
            
            # Institutional ownership thresholds (existing)
            'inst_own_min': {'value': 0.20, 'desc': 'Minimum ideal institutional ownership'},
            'inst_own_max': {'value': 0.60, 'desc': 'Maximum ideal institutional ownership'},
            
            # Revenue growth thresholds (NEW)
            'revenue_growth_excellent': {'value': 15.0, 'desc': 'Excellent revenue growth % (CAGR)'},
            'revenue_growth_good': {'value': 10.0, 'desc': 'Good revenue growth % (CAGR)'},
            'revenue_growth_fair': {'value': 5.0, 'desc': 'Fair revenue growth % (CAGR)'},
            
            # Income growth thresholds (NEW)
            'income_growth_excellent': {'value': 15.0, 'desc': 'Excellent income growth % (CAGR)'},
            'income_growth_good': {'value': 10.0, 'desc': 'Good income growth % (CAGR)'},
            'income_growth_fair': {'value': 5.0, 'desc': 'Fair income growth % (CAGR)'},
            
            # Algorithm weights (existing)
            'weight_peg': {'value': 0.50, 'desc': 'Weight for PEG Score in Weighted Algo'},
            'weight_consistency': {'value': 0.25, 'desc': 'Weight for Consistency in Weighted Algo'},
            'weight_debt': {'value': 0.15, 'desc': 'Weight for Debt Score in Weighted Algo'},
            'weight_ownership': {'value': 0.10, 'desc': 'Weight for Ownership in Weighted Algo'}
        }

        current_settings = self.get_all_settings()

        added_count = 0
        for key, data in defaults.items():
            if key not in current_settings:
                self.set_setting(key, data['value'], data['desc'])
                added_count += 1

        logger.info(f"Default settings initialization complete: {added_count} new settings added")
    # Backtest Results Methods
    def save_backtest_result(self, result: Dict[str, Any]):
        """Save a backtest result"""
        sql = """
            INSERT INTO backtest_results
            (symbol, backtest_date, years_back, start_price, end_price, total_return,
             historical_score, historical_rating, peg_score, debt_score, ownership_score,
             consistency_score, peg_ratio, earnings_cagr, revenue_cagr, debt_to_equity,
             institutional_ownership)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, years_back) DO UPDATE SET
                backtest_date = EXCLUDED.backtest_date,
                start_price = EXCLUDED.start_price,
                end_price = EXCLUDED.end_price,
                total_return = EXCLUDED.total_return,
                historical_score = EXCLUDED.historical_score,
                historical_rating = EXCLUDED.historical_rating,
                peg_score = EXCLUDED.peg_score,
                debt_score = EXCLUDED.debt_score,
                ownership_score = EXCLUDED.ownership_score,
                consistency_score = EXCLUDED.consistency_score,
                peg_ratio = EXCLUDED.peg_ratio,
                earnings_cagr = EXCLUDED.earnings_cagr,
                revenue_cagr = EXCLUDED.revenue_cagr,
                debt_to_equity = EXCLUDED.debt_to_equity,
                institutional_ownership = EXCLUDED.institutional_ownership
        """
        hist_data = result.get('historical_data', {})
        args = (
            result['symbol'],
            result['backtest_date'],
            result.get('years_back', 1),
            result['start_price'],
            result['end_price'],
            result['total_return'],
            result['historical_score'],
            result['historical_rating'],
            hist_data.get('peg_score'),
            hist_data.get('debt_score'),
            hist_data.get('institutional_ownership_score'),
            hist_data.get('consistency_score'),
            hist_data.get('peg_ratio'),
            hist_data.get('earnings_cagr'),
            hist_data.get('revenue_cagr'),
            hist_data.get('debt_to_equity'),
            hist_data.get('institutional_ownership')
        )
        self.write_queue.put((sql, args))

    def get_backtest_results(self, years_back: int = None) -> List[Dict[str, Any]]:
        """Get backtest results, optionally filtered by years_back"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if years_back:
            query = "SELECT * FROM backtest_results WHERE years_back = %s ORDER BY symbol"
            cursor.execute(query, (years_back,))
        else:
            query = "SELECT * FROM backtest_results ORDER BY years_back, symbol"
            cursor.execute(query)
        
        rows = cursor.fetchall()
        self.return_connection(conn)
        
        return [
            {
                'id': row[0],
                'symbol': row[1],
                'backtest_date': row[2],
                'years_back': row[3],
                'start_price': row[4],
                'end_price': row[5],
                'total_return': row[6],
                'historical_score': row[7],
                'historical_rating': row[8],
                'peg_score': row[9],
                'debt_score': row[10],
                'ownership_score': row[11],
                'consistency_score': row[12],
                'peg_ratio': row[13],
                'earnings_cagr': row[14],
                'revenue_cagr': row[15],
                'debt_to_equity': row[16],
                'institutional_ownership': row[17],
                'created_at': row[18]
            }
            for row in rows
        ]

    # Algorithm Configuration Methods
    def save_algorithm_config(self, config: Dict[str, Any]) -> int:
        """Save an algorithm configuration and return its ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO algorithm_configurations
            (name, weight_peg, weight_consistency, weight_debt, weight_ownership,
             peg_excellent, peg_good, peg_fair,
             debt_excellent, debt_good, debt_moderate,
             inst_own_min, inst_own_max,
             revenue_growth_excellent, revenue_growth_good, revenue_growth_fair,
             income_growth_excellent, income_growth_good, income_growth_fair,
             correlation_1yr, correlation_3yr, correlation_5yr, is_active)
            VALUES (%s, %s, %s, %s, %s, 
                    %s, %s, %s, 
                    %s, %s, %s, 
                    %s, %s, 
                    %s, %s, %s, 
                    %s, %s, %s, 
                    %s, %s, %s, %s)
            RETURNING id
        """, (
            config.get('name', 'Unnamed'),
            config['weight_peg'],
            config['weight_consistency'],
            config['weight_debt'],
            config['weight_ownership'],
            config.get('peg_excellent', 1.0),
            config.get('peg_good', 1.5),
            config.get('peg_fair', 2.0),
            config.get('debt_excellent', 0.5),
            config.get('debt_good', 1.0),
            config.get('debt_moderate', 2.0),
            config.get('inst_own_min', 0.20),
            config.get('inst_own_max', 0.60),
            config.get('revenue_growth_excellent', 15.0),
            config.get('revenue_growth_good', 10.0),
            config.get('revenue_growth_fair', 5.0),
            config.get('income_growth_excellent', 15.0),
            config.get('income_growth_good', 10.0),
            config.get('income_growth_fair', 5.0),
            config.get('correlation_1yr'),
            config.get('correlation_3yr'),
            config.get('correlation_5yr'),
            config.get('is_active', False)
        ))
        
        config_id = cursor.fetchone()[0]
        conn.commit()
        self.return_connection(conn)
        return config_id

    def get_algorithm_configs(self) -> List[Dict[str, Any]]:
        """Get all algorithm configurations"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM algorithm_configurations ORDER BY created_at DESC")
        rows = cursor.fetchall()
        self.return_connection(conn)

        # Get column names from cursor description to map correctly
        # This is safer than hardcoding indices since we just added columns
        colnames = [desc[0] for desc in cursor.description]

        results = []
        for row in rows:
            row_dict = dict(zip(colnames, row))
            results.append(row_dict)

        return results

    # Background Jobs Methods

    def create_background_job(self, job_type: str, params: Dict[str, Any]) -> int:
        """Create a new background job and return its ID"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO background_jobs (job_type, params, status, created_at)
                VALUES (%s, %s, 'pending', NOW())
                RETURNING id
            """, (job_type, json.dumps(params)))
            job_id = cursor.fetchone()[0]
            conn.commit()
            return job_id
        finally:
            self.return_connection(conn)

    def get_background_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get a background job by ID"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, job_type, status, claimed_by, claimed_at, claim_expires_at,
                       params, progress_pct, progress_message, processed_count, total_count,
                       result, error_message, created_at, started_at, completed_at
                FROM background_jobs
                WHERE id = %s
            """, (job_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'id': row[0],
                'job_type': row[1],
                'status': row[2],
                'claimed_by': row[3],
                'claimed_at': row[4],
                'claim_expires_at': row[5],
                'params': row[6] if isinstance(row[6], dict) else json.loads(row[6]) if row[6] else {},
                'progress_pct': row[7],
                'progress_message': row[8],
                'processed_count': row[9],
                'total_count': row[10],
                'result': row[11] if isinstance(row[11], dict) else json.loads(row[11]) if row[11] else None,
                'error_message': row[12],
                'created_at': row[13],
                'started_at': row[14],
                'completed_at': row[15]
            }
        finally:
            self.return_connection(conn)

    def claim_pending_job(self, worker_id: str, claim_minutes: int = 10) -> Optional[Dict[str, Any]]:
        """
        Atomically claim a pending job using FOR UPDATE SKIP LOCKED.
        Returns the claimed job or None if no pending jobs available.
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                WITH claimable AS (
                    SELECT id FROM background_jobs
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE background_jobs
                SET status = 'claimed',
                    claimed_by = %s,
                    claimed_at = NOW(),
                    claim_expires_at = NOW() + INTERVAL '%s minutes'
                WHERE id = (SELECT id FROM claimable)
                RETURNING id, job_type, status, claimed_by, claimed_at, claim_expires_at,
                          params, progress_pct, progress_message, processed_count, total_count,
                          result, error_message, created_at, started_at, completed_at
            """, (worker_id, claim_minutes))

            row = cursor.fetchone()
            conn.commit()

            if not row:
                return None

            return {
                'id': row[0],
                'job_type': row[1],
                'status': row[2],
                'claimed_by': row[3],
                'claimed_at': row[4],
                'claim_expires_at': row[5],
                'params': row[6] if isinstance(row[6], dict) else json.loads(row[6]) if row[6] else {},
                'progress_pct': row[7],
                'progress_message': row[8],
                'processed_count': row[9],
                'total_count': row[10],
                'result': row[11] if isinstance(row[11], dict) else json.loads(row[11]) if row[11] else None,
                'error_message': row[12],
                'created_at': row[13],
                'started_at': row[14],
                'completed_at': row[15]
            }
        finally:
            self.return_connection(conn)

    def update_job_progress(self, job_id: int, progress_pct: int = None,
                           progress_message: str = None, processed_count: int = None,
                           total_count: int = None):
        """Update job progress information"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            updates = []
            values = []

            if progress_pct is not None:
                updates.append("progress_pct = %s")
                values.append(progress_pct)
            if progress_message is not None:
                updates.append("progress_message = %s")
                values.append(progress_message)
            if processed_count is not None:
                updates.append("processed_count = %s")
                values.append(processed_count)
            if total_count is not None:
                updates.append("total_count = %s")
                values.append(total_count)

            if updates:
                values.append(job_id)
                cursor.execute(f"""
                    UPDATE background_jobs
                    SET {', '.join(updates)}
                    WHERE id = %s
                """, tuple(values))
                conn.commit()
        finally:
            self.return_connection(conn)

    def update_job_status(self, job_id: int, status: str):
        """Update job status"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET status = %s,
                    started_at = CASE WHEN %s = 'running' AND started_at IS NULL THEN NOW() ELSE started_at END
                WHERE id = %s
            """, (status, status, job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def complete_job(self, job_id: int, result: Dict[str, Any]):
        """Mark job as completed with result"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET status = 'completed',
                    result = %s,
                    completed_at = NOW(),
                    progress_pct = 100
                WHERE id = %s
            """, (json.dumps(result), job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def fail_job(self, job_id: int, error_message: str):
        """Mark job as failed with error message"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET status = 'failed',
                    error_message = %s,
                    completed_at = NOW()
                WHERE id = %s
            """, (error_message, job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def cancel_job(self, job_id: int):
        """Cancel a job and release its claim"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Set status to cancelled and clear the claim
            cursor.execute("""
                UPDATE background_jobs
                SET status = 'cancelled',
                    completed_at = NOW(),
                    claimed_by = NULL,
                    claimed_at = NULL
                WHERE id = %s
            """, (job_id,))
            conn.commit()
        finally:
            self.return_connection(conn)

    def extend_job_claim(self, job_id: int, minutes: int = 10):
        """Extend job claim expiry (heartbeat)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET claim_expires_at = NOW() + INTERVAL '%s minutes'
                WHERE id = %s
            """, (minutes, job_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_pending_jobs_count(self) -> int:
        """Get count of pending jobs"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM background_jobs WHERE status = 'pending'")
            count = cursor.fetchone()[0]
            return count
        finally:
            self.return_connection(conn)

    def release_job(self, job_id: int):
        """Release a claimed job back to pending status"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET status = 'pending',
                    claimed_by = NULL,
                    claimed_at = NULL,
                    claim_expires_at = NULL
                WHERE id = %s
            """, (job_id,))
            conn.commit()
        finally:
            self.return_connection(conn)
