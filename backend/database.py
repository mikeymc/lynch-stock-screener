# ABOUTME: Manages PostgreSQL database for caching stock data and financial metrics
# ABOUTME: Provides schema and operations for storing and retrieving stock information

import psycopg
from psycopg_pool import ConnectionPool
import threading
import os
import queue
import time
import logging
from datetime import datetime, timezone
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
            # The _init_schema_with_connection method should handle its own commits.
            # If it doesn't, a commit here would be needed. Assuming it does for now.
            logger.info("Database schema initialized successfully")

            # Migration: Drop unused screening tables (refactored to use on-demand scoring)
            try:
                cursor = init_conn.cursor() # Create a cursor for the migration
                cursor.execute("""
                    DROP TABLE IF EXISTS screening_results CASCADE;
                    DROP TABLE IF EXISTS screening_sessions CASCADE;
                """)
                init_conn.commit()
                logger.info("Migration: Dropped screening_sessions and screening_results tables")
            except Exception as e:
                logger.warning(f"Migration warning (drop screening tables): {e}")
                init_conn.rollback() # Rollback only the migration if it fails

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
        """Wait for all pending writes to complete and commit (blocking)"""
        self.write_queue.put("FLUSH")
        self.write_queue.join()
    
    def flush_async(self):
        """Trigger a commit without waiting (non-blocking)
        
        Use this for periodic flushes during long jobs where you want to
        commit progress but don't need to wait. The final flush before
        job completion should use flush() to ensure all data is committed.
        """
        self.write_queue.put("FLUSH")

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
                
                -- gross_margin (for Buffett scoring)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'stock_metrics' AND column_name = 'gross_margin') THEN
                    ALTER TABLE stock_metrics ADD COLUMN gross_margin REAL;
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

        # Cache checks table - tracks when symbols were last checked for each cache type
        # Used to skip redundant API calls for symbols that have already been processed
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_checks (
                symbol TEXT NOT NULL,
                cache_type TEXT NOT NULL,
                last_checked DATE NOT NULL,
                last_data_date DATE,
                PRIMARY KEY (symbol, cache_type)
            )
        """)
        
        # Index for efficient lookups by cache_type (for bulk operations)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_checks_type 
            ON cache_checks(cache_type, last_checked)
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

        # Migration: Add new columns for Buffett/Lynch metrics if they don't exist
        # shares_outstanding, shareholder_equity, cash_and_cash_equivalents
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'earnings_history' AND column_name = 'shares_outstanding') THEN
                    ALTER TABLE earnings_history ADD COLUMN shares_outstanding REAL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'earnings_history' AND column_name = 'shareholder_equity') THEN
                    ALTER TABLE earnings_history ADD COLUMN shareholder_equity REAL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'earnings_history' AND column_name = 'cash_and_cash_equivalents') THEN
                    ALTER TABLE earnings_history ADD COLUMN cash_and_cash_equivalents REAL;
                END IF;
            END $$;
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
                user_id INTEGER,
                symbol TEXT,
                character_id TEXT DEFAULT 'lynch',
                analysis_text TEXT,
                generated_at TIMESTAMP,
                model_version TEXT,
                PRIMARY KEY (user_id, symbol, character_id),
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Migration: Add character_id and user_id to lynch_analyses if they don't exist
        # and ensure PK/Unique constraints include character_id
        cursor.execute("""
            DO $$
            BEGIN
                -- Add character_id if missing
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'lynch_analyses' AND column_name = 'character_id') THEN
                    ALTER TABLE lynch_analyses ADD COLUMN character_id TEXT DEFAULT 'lynch';
                END IF;

                -- Add user_id if missing
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'lynch_analyses' AND column_name = 'user_id') THEN
                    ALTER TABLE lynch_analyses ADD COLUMN user_id INTEGER;
                END IF;

                -- Always ensure the user_id is populated for PK if we're migrating
                UPDATE lynch_analyses SET user_id = 999 WHERE user_id IS NULL; -- Default to dev user or most likely owner

                -- Update Primary Key to include character_id if it's currently just (user_id, symbol) or something else
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints tc 
                    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name 
                    WHERE tc.table_name = 'lynch_analyses' AND tc.constraint_type = 'PRIMARY KEY' AND kcu.column_name = 'character_id'
                ) THEN
                    ALTER TABLE lynch_analyses DROP CONSTRAINT IF EXISTS lynch_analyses_pkey;
                    ALTER TABLE lynch_analyses ADD PRIMARY KEY (user_id, symbol, character_id);
                END IF;

                -- Aggressively drop legacy unique constraint if it exists
                ALTER TABLE lynch_analyses DROP CONSTRAINT IF EXISTS lynch_analyses_user_symbol_unique;
            END $$;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chart_analyses (
                user_id INTEGER,
                symbol TEXT,
                section TEXT,
                character_id TEXT DEFAULT 'lynch',
                analysis_text TEXT,
                generated_at TIMESTAMP,
                model_version TEXT,
                PRIMARY KEY (user_id, symbol, section, character_id),
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Migration: Update chart_analyses schema for multiple characters
        cursor.execute("""
            DO $$
            BEGIN
                -- Add character_id if missing
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'chart_analyses' AND column_name = 'character_id') THEN
                    ALTER TABLE chart_analyses ADD COLUMN character_id TEXT DEFAULT 'lynch';
                END IF;

                -- Add user_id if missing
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'chart_analyses' AND column_name = 'user_id') THEN
                    ALTER TABLE chart_analyses ADD COLUMN user_id INTEGER;
                END IF;

                UPDATE chart_analyses SET user_id = 999 WHERE user_id IS NULL;

                -- Update Primary Key to include character_id
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints tc 
                    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name 
                    WHERE tc.table_name = 'chart_analyses' AND tc.constraint_type = 'PRIMARY KEY' AND kcu.column_name = 'character_id'
                ) THEN
                    ALTER TABLE chart_analyses DROP CONSTRAINT IF EXISTS chart_analyses_pkey;
                    ALTER TABLE chart_analyses ADD PRIMARY KEY (user_id, symbol, section, character_id);
                END IF;

                -- Aggressively drop legacy unique constraint
                ALTER TABLE chart_analyses DROP CONSTRAINT IF EXISTS chart_analyses_user_symbol_section_unique;
            END $$;
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

        # Migration: Add active_character column to users table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'users' AND column_name = 'active_character') THEN
                    ALTER TABLE users ADD COLUMN active_character TEXT DEFAULT 'lynch';
                END IF;
            END $$;
        """)

        # Migration: Add theme column to users table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'users' AND column_name = 'theme') THEN
                    ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'midnight';
                END IF;
            END $$;
        """)

        # Migration: Add password_hash column to users table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'users' AND column_name = 'password_hash') THEN
                    ALTER TABLE users ADD COLUMN password_hash TEXT;
                END IF;
            END $$;
        """)

        # Migration: Make google_id nullable for email/password users
        cursor.execute("""
            ALTER TABLE users ALTER COLUMN google_id DROP NOT NULL;
        """)

        # Migration: Make google_id nullable for email/password users
        cursor.execute("""
            ALTER TABLE users ALTER COLUMN google_id DROP NOT NULL;
        """)

        # Migration: Add is_verified and verification_token to users table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'users' AND column_name = 'is_verified') THEN
                    ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT TRUE;
                    ALTER TABLE users ADD COLUMN verification_token TEXT;
                END IF;
            END $$;
        """)

        # Migration: Add verification_code and code_expires_at to users table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'users' AND column_name = 'verification_code') THEN
                    ALTER TABLE users ADD COLUMN verification_code VARCHAR(6);
                    ALTER TABLE users ADD COLUMN code_expires_at TIMESTAMP;
                END IF;
            END $$;
        """)

        # Migration: Add has_completed_onboarding to users table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'users' AND column_name = 'has_completed_onboarding') THEN
                    ALTER TABLE users ADD COLUMN has_completed_onboarding BOOLEAN DEFAULT FALSE;
                END IF;
            END $$;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_feedback (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                email TEXT,
                feedback_text TEXT,
                screenshot_data TEXT,
                page_url TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'new',
                FOREIGN KEY (user_id) REFERENCES users(id)
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                symbol TEXT REFERENCES stocks(symbol),
                condition_type TEXT NOT NULL,
                condition_params JSONB NOT NULL,
                frequency TEXT DEFAULT 'daily',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                triggered_at TIMESTAMP,
                message TEXT,
                condition_description TEXT,
                UNIQUE(user_id, symbol, condition_type, condition_params)
            )
        """)
        
        # Migration: Add condition_description for flexible LLM-based alerts
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alerts' AND column_name = 'condition_description') THEN
                    ALTER TABLE alerts ADD COLUMN condition_description TEXT;
                END IF;
            END $$;
        """)
        
        # Migration: Drop UNIQUE constraint to allow multiple custom alerts per ticker
        # The constraint UNIQUE(user_id, symbol, condition_type, condition_params) prevents
        # users from creating multiple custom alerts for the same ticker because all custom
        # alerts use condition_type='custom' and condition_params={}. The actual conditions
        # are stored in condition_description, so this constraint is overly restrictive.
        cursor.execute("""
            DO $$
            BEGIN
                -- Drop the constraint if it exists
                IF EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conname = 'alerts_user_id_symbol_condition_type_condition_params_key'
                ) THEN
                    ALTER TABLE alerts DROP CONSTRAINT alerts_user_id_symbol_condition_type_condition_params_key;
                END IF;
            END $$;
        """)
        
        # Initialize remaining schema (misplaced code wrapper)
        self._init_rest_of_schema(conn)

    def create_alert(self, user_id: int, symbol: str, condition_type: str = 'custom', 
                     condition_params: Optional[Dict[str, Any]] = None, 
                     frequency: str = 'daily', 
                     condition_description: Optional[str] = None) -> int:
        """
        Create a new user alert.
        
        Args:
            user_id: User ID creating the alert
            symbol: Stock symbol for the alert
            condition_type: Legacy alert type ('price', 'pe_ratio', or 'custom' for LLM-based)
            condition_params: Legacy condition parameters (dict with threshold/operator)
            frequency: How often to check (not currently used, but kept for future)
            condition_description: Natural language description of the alert condition (for LLM evaluation)
        
        Returns:
            Alert ID
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Default to empty params if not provided
            if condition_params is None:
                condition_params = {}
            
            cursor.execute("""
                INSERT INTO alerts (user_id, symbol, condition_type, condition_params, frequency, status, condition_description)
                VALUES (%s, %s, %s, %s, %s, 'active', %s)
                RETURNING id
            """, (user_id, symbol, condition_type, json.dumps(condition_params), frequency, condition_description))
            alert_id = cursor.fetchone()[0]
            conn.commit()
            return alert_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating alert: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_alerts(self, user_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get alerts for a user, optionally filtered by status."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT id, symbol, condition_type, condition_params, frequency, status, 
                       created_at, last_checked, triggered_at, message, condition_description
                FROM alerts 
                WHERE user_id = %s
            """
            params = [user_id]
            
            if status:
                query += " AND status = %s"
                params.append(status)
                
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                alert = dict(zip(columns, row))
                # Parse JSONB params if string (psycopg3 handles this automatically usually but to be safe)
                if isinstance(alert['condition_params'], str):
                    alert['condition_params'] = json.loads(alert['condition_params'])
                results.append(alert)
            return results
        finally:
            self.return_connection(conn)

    def delete_alert(self, alert_id: int, user_id: int) -> bool:
        """Delete an alert (soft delete or hard delete? let's do hard delete for now)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM alerts WHERE id = %s AND user_id = %s", (alert_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Error deleting alert: {e}")
            return False
        finally:
            self.return_connection(conn)
            
    def update_alert_status(self, alert_id: int, status: str, triggered_at: Optional[datetime] = None, message: str = None):
        """Update the status of an alert."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            updates = ["status = %s"]
            params = [status]
            
            if triggered_at:
                updates.append("triggered_at = %s")
                params.append(triggered_at)
                
            if message:
                updates.append("message = %s")
                params.append(message)
                
            # Always update last_checked
            updates.append("last_checked = CURRENT_TIMESTAMP")
            
            updates.append("WHERE id = %s") # This is wrong logic, WHERE should be outside
            
            sql = f"UPDATE alerts SET {', '.join(updates)} WHERE id = %s"
            # Now append id to params
            params.append(alert_id)
            
            # Correct the logic: remove the WHERE clause from updates list
            # Actually, let's rewrite for clarity
            
            sql = """
                UPDATE alerts 
                SET status = %s, 
                    last_checked = CURRENT_TIMESTAMP,
                    triggered_at = COALESCE(%s, triggered_at),
                    message = COALESCE(%s, message)
                WHERE id = %s
            """
            cursor.execute(sql, (status, triggered_at, message, alert_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating alert status: {e}")
            raise
        finally:
            self.return_connection(conn)

    def get_all_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts for processing by the worker."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, user_id, symbol, condition_type, condition_params, frequency, status, last_checked, condition_description
                FROM alerts 
                WHERE status = 'active'
            """)
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                alert = dict(zip(columns, row))
                if isinstance(alert['condition_params'], str):
                    alert['condition_params'] = json.loads(alert['condition_params'])
                results.append(alert)
            return results
        finally:
            self.return_connection(conn)

    def _init_rest_of_schema(self, conn):
        """Initialize remaining schema tables"""
        cursor = conn.cursor()

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
                roe REAL,
                debt_to_earnings REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, years_back)
            )
        """)

        # Migration: Add Buffett metrics to backtest_results
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'backtest_results' AND column_name = 'roe') THEN
                    ALTER TABLE backtest_results ADD COLUMN roe REAL;
                END IF;

                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'backtest_results' AND column_name = 'debt_to_earnings') THEN
                    ALTER TABLE backtest_results ADD COLUMN debt_to_earnings REAL;
                END IF;

                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'backtest_results' AND column_name = 'gross_margin') THEN
                    ALTER TABLE backtest_results ADD COLUMN gross_margin REAL;
                END IF;
            END $$;
        """)

        # Migration: Add shareholder_equity to earnings_history
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'earnings_history' AND column_name = 'shareholder_equity') THEN
                    ALTER TABLE earnings_history ADD COLUMN shareholder_equity REAL;
                END IF;
            END $$;
        """)

        # Migration: Add shares_outstanding to earnings_history
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'earnings_history' AND column_name = 'shares_outstanding') THEN
                    ALTER TABLE earnings_history ADD COLUMN shares_outstanding REAL;
                END IF;
            END $$;
        """)

        # Migration: Add cash_and_cash_equivalents to earnings_history
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'earnings_history' AND column_name = 'cash_and_cash_equivalents') THEN
                    ALTER TABLE earnings_history ADD COLUMN cash_and_cash_equivalents REAL;
                END IF;
            END $$;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS algorithm_configurations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                name TEXT,
                weight_peg REAL,
                weight_consistency REAL,
                weight_debt REAL,
                weight_ownership REAL,
                weight_roe REAL,
                weight_debt_to_earnings REAL,
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
                roe_excellent REAL DEFAULT 20.0,
                roe_good REAL DEFAULT 15.0,
                roe_fair REAL DEFAULT 10.0,
                debt_to_earnings_excellent REAL DEFAULT 3.0,
                debt_to_earnings_good REAL DEFAULT 5.0,
                debt_to_earnings_fair REAL DEFAULT 8.0,
                correlation_5yr REAL,
                correlation_10yr REAL,
                is_active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                character TEXT DEFAULT 'lynch'
            )
        """)

        # Migration: Add missing columns if they don't exist
        try:
            # List of new columns to check/add
            new_columns = [
                ('user_id', 'INTEGER REFERENCES users(id)'),
                ('character', "TEXT DEFAULT 'lynch'"),
                ('weight_roe', 'REAL'),
                ('weight_debt_to_earnings', 'REAL'),
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
                ('income_growth_fair', 'REAL DEFAULT 5.0'),
                ('roe_excellent', 'REAL DEFAULT 20.0'),
                ('roe_good', 'REAL DEFAULT 15.0'),
                ('roe_fair', 'REAL DEFAULT 10.0'),
                ('debt_to_earnings_excellent', 'REAL DEFAULT 3.0'),
                ('debt_to_earnings_good', 'REAL DEFAULT 5.0'),
                ('debt_to_earnings_fair', 'REAL DEFAULT 8.0'),
                ('correlation_5yr', 'REAL'),
                ('correlation_10yr', 'REAL'),
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
            
            # Drop old correlation columns
            for old_col in ['correlation_1yr', 'correlation_3yr']:
                cursor.execute(f"""
                    ALTER TABLE algorithm_configurations DROP COLUMN IF EXISTS {old_col};
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
            DO $$
            BEGIN
                -- Migration: Add Gross Margin columns to algorithm_configurations (Buffett metrics)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'algorithm_configurations' AND column_name = 'gross_margin_excellent') THEN
                    ALTER TABLE algorithm_configurations ADD COLUMN gross_margin_excellent REAL DEFAULT 50.0;
                    ALTER TABLE algorithm_configurations ADD COLUMN gross_margin_good REAL DEFAULT 40.0;
                    ALTER TABLE algorithm_configurations ADD COLUMN gross_margin_fair REAL DEFAULT 30.0;
                    ALTER TABLE algorithm_configurations ADD COLUMN weight_gross_margin REAL DEFAULT 0.0;
                END IF;
                
                -- Migration: Add weight_gross_margin column (separate check since thresholds already exist)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'algorithm_configurations' AND column_name = 'weight_gross_margin') THEN
                    ALTER TABLE algorithm_configurations ADD COLUMN weight_gross_margin REAL DEFAULT 0.0;
                END IF;
            END $$;
        """)

        # Migration: Drop deprecated RAG chat tables (conversations, messages, message_sources)
        # These were replaced by agent chat tables (agent_conversations, agent_messages)
        cursor.execute("""
            DROP TABLE IF EXISTS message_sources CASCADE;
            DROP TABLE IF EXISTS messages CASCADE;
            DROP TABLE IF EXISTS conversations CASCADE;
        """)

        # Agent chat tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_conversations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_conversations_user 
            ON agent_conversations(user_id, last_message_at DESC)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_messages (
                id SERIAL PRIMARY KEY,
                conversation_id INTEGER NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                tool_calls JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_messages_conversation 
            ON agent_messages(conversation_id, created_at ASC)
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

        # Initialize default settings
        cursor.execute("SELECT 1 FROM app_settings WHERE key = 'feature_alerts_enabled'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO app_settings (key, value, description)
                VALUES ('feature_alerts_enabled', 'false', 'Toggle for Alerts feature (bell icon and agent tool)')
            """)
            conn.commit()

        # Initialize us_stocks_only setting (default: true for production)
        cursor.execute("SELECT 1 FROM app_settings WHERE key = 'us_stocks_only'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO app_settings (key, value, description)
                VALUES ('us_stocks_only', 'true', 'Filter to show only US stocks (hides country filters in UI)')
            """)
            conn.commit()

        # Initialize feature_economy_link_enabled setting (default: false)
        cursor.execute("SELECT 1 FROM app_settings WHERE key = 'feature_economy_link_enabled'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO app_settings (key, value, description)
                VALUES ('feature_economy_link_enabled', 'false', 'Show Economy link in navigation sidebar')
            """)
            conn.commit()

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

        # Migration: add period_end_date column to analyst_estimates
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'analyst_estimates' AND column_name = 'period_end_date') THEN
                    ALTER TABLE analyst_estimates ADD COLUMN period_end_date DATE;
                END IF;
            END $$;
        """)

        # Migration: add fiscal_quarter and fiscal_year columns
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'analyst_estimates' AND column_name = 'fiscal_quarter') THEN
                    ALTER TABLE analyst_estimates ADD COLUMN fiscal_quarter INTEGER;
                END IF;
            END $$;
        """)

        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'analyst_estimates' AND column_name = 'fiscal_year') THEN
                    ALTER TABLE analyst_estimates ADD COLUMN fiscal_year INTEGER;
                END IF;
            END $$;
        """)

        # EPS Trends - how estimates have changed over time
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS eps_trends (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                period TEXT NOT NULL,
                current_est REAL,
                days_7_ago REAL,
                days_30_ago REAL,
                days_60_ago REAL,
                days_90_ago REAL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, period)
            )
        """)

        # EPS Revisions - analyst revision counts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS eps_revisions (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                period TEXT NOT NULL,
                up_7d INTEGER,
                up_30d INTEGER,
                down_7d INTEGER,
                down_30d INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, period)
            )
        """)

        # Growth Estimates - stock vs index comparison
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS growth_estimates (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                period TEXT NOT NULL,
                stock_trend REAL,
                index_trend REAL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, period)
            )
        """)

        # Analyst Recommendations - monthly buy/hold/sell distribution
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyst_recommendations (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                period_month TEXT NOT NULL,
                strong_buy INTEGER,
                buy INTEGER,
                hold INTEGER,
                sell INTEGER,
                strong_sell INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, period_month)
            )
        """)

        # Migration: Add earnings/revenue growth columns to stock_metrics
        cursor.execute("""
            DO $$
            BEGIN
                -- price_target_median
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'price_target_median') THEN
                    ALTER TABLE stock_metrics ADD COLUMN price_target_median REAL;
                END IF;
                
                -- earnings_growth (YoY)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'earnings_growth') THEN
                    ALTER TABLE stock_metrics ADD COLUMN earnings_growth REAL;
                END IF;
                
                -- earnings_quarterly_growth
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'earnings_quarterly_growth') THEN
                    ALTER TABLE stock_metrics ADD COLUMN earnings_quarterly_growth REAL;
                END IF;
                
                -- revenue_growth
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'revenue_growth') THEN
                    ALTER TABLE stock_metrics ADD COLUMN revenue_growth REAL;
                END IF;
                
                -- recommendation_key (buy, hold, sell, etc.)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name = 'stock_metrics' AND column_name = 'recommendation_key') THEN
                    ALTER TABLE stock_metrics ADD COLUMN recommendation_key TEXT;
                END IF;
            END $$;
        """)

        # Social sentiment from Reddit and other sources
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS social_sentiment (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                source TEXT DEFAULT 'reddit',
                subreddit TEXT,
                title TEXT,
                selftext TEXT,
                url TEXT,
                author TEXT,
                score INTEGER DEFAULT 0,
                upvote_ratio REAL,
                num_comments INTEGER DEFAULT 0,
                sentiment_score REAL,
                created_utc BIGINT,
                published_at TIMESTAMP,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_social_sentiment_symbol_date
            ON social_sentiment(symbol, published_at DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_social_sentiment_score
            ON social_sentiment(score DESC)
        """)

        # Migration: add conversation_json column for storing Reddit comments
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'social_sentiment' AND column_name = 'conversation_json') THEN
                    ALTER TABLE social_sentiment ADD COLUMN conversation_json JSONB;
                END IF;
            END $$;
        """)

        # Migration: Add last_price_updated to stock_metrics
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'stock_metrics' AND column_name = 'last_price_updated') THEN
                    ALTER TABLE stock_metrics ADD COLUMN last_price_updated TIMESTAMP WITH TIME ZONE;
                END IF;
            END $$;
        """)

        # Paper trading portfolios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                initial_cash REAL DEFAULT 100000.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: Add dividend_preference to portfolios table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'portfolios' AND column_name = 'dividend_preference') THEN
                    ALTER TABLE portfolios ADD COLUMN dividend_preference TEXT DEFAULT 'cash' CHECK (dividend_preference IN ('cash', 'reinvest'));
                END IF;
            END $$;
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolios_user
            ON portfolios(user_id)
        """)

        # Portfolio transactions (source of truth for holdings and cash)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_transactions (
                id SERIAL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                symbol TEXT NOT NULL,
                transaction_type TEXT NOT NULL CHECK (transaction_type IN ('BUY', 'SELL')),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                price_per_share REAL NOT NULL,
                total_value REAL NOT NULL,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                note TEXT
            )
        """)

        # Migration: Update portfolio_transactions check constraint to allow DIVIDEND
        cursor.execute("""
            DO $$
            BEGIN
                -- Drop the old constraint if it exists
                IF EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conname = 'portfolio_transactions_transaction_type_check'
                ) THEN
                    ALTER TABLE portfolio_transactions DROP CONSTRAINT portfolio_transactions_transaction_type_check;
                END IF;
                
                -- Add updated constraint
                ALTER TABLE portfolio_transactions ADD CONSTRAINT portfolio_transactions_transaction_type_check 
                CHECK (transaction_type IN ('BUY', 'SELL', 'DIVIDEND'));
            END $$;
        """)

        # Cache for dividend payouts to avoid excessive API calls
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dividend_payouts (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL REFERENCES stocks(symbol),
                amount REAL NOT NULL,
                payment_date DATE NOT NULL,
                ex_dividend_date DATE,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, payment_date)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_portfolio
            ON portfolio_transactions(portfolio_id)
        """)

        # Portfolio value snapshots (for historical charts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_value_snapshots (
                id SERIAL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                total_value REAL NOT NULL,
                cash_value REAL NOT NULL,
                holdings_value REAL NOT NULL,
                snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_portfolio_time
            ON portfolio_value_snapshots(portfolio_id, snapshot_at)
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
        metrics['last_updated'] = datetime.now(timezone.utc)
        if 'price' in metrics:
            metrics['last_price_updated'] = datetime.now(timezone.utc)
        
        # Valid columns map to ensure we only try to update valid fields
        valid_columns = {
            'price', 'pe_ratio', 'market_cap', 'debt_to_equity', 
            'institutional_ownership', 'revenue', 'dividend_yield', 
            'beta', 'total_debt', 'interest_expense', 'effective_tax_rate',
            'gross_margin',  # For Buffett scoring
            'forward_pe', 'forward_peg_ratio', 'forward_eps',
            'insider_net_buying_6m', 'last_updated', 'last_price_updated',
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

    def has_recent_insider_trades(self, symbol: str, since_date: str) -> bool:
        """
        Check if we have insider trades (Form 4 data) for a symbol since a given date.
        
        Used by Form 4 cache job to skip already-processed symbols.
        
        Args:
            symbol: Stock symbol
            since_date: Date string (YYYY-MM-DD) - returns True if we have trades on or after this date
            
        Returns:
            True if we have at least one insider trade since since_date
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM insider_trades
                WHERE symbol = %s AND transaction_date >= %s
                LIMIT 1
            """, (symbol, since_date))
            return cursor.fetchone() is not None
        finally:
            self.return_connection(conn)

    # ==================== Cache Check Methods ====================
    
    def record_cache_check(self, symbol: str, cache_type: str, 
                           last_data_date: Optional[str] = None) -> None:
        """
        Record that a symbol was checked for a specific cache type.
        
        Call this after processing a symbol, even if no data was found.
        This prevents redundant API calls on subsequent cache runs.
        
        Args:
            symbol: Stock symbol
            cache_type: Type of cache ('form4', '10k', '8k', 'prices', 'transcripts', 'news')
            last_data_date: Optional date of most recent data found (for incremental fetches)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cache_checks (symbol, cache_type, last_checked, last_data_date)
                VALUES (%s, %s, CURRENT_DATE, %s)
                ON CONFLICT (symbol, cache_type) DO UPDATE SET
                    last_checked = CURRENT_DATE,
                    last_data_date = COALESCE(EXCLUDED.last_data_date, cache_checks.last_data_date)
            """, (symbol, cache_type, last_data_date))
            conn.commit()
        finally:
            self.return_connection(conn)
    
    def was_cache_checked_since(self, symbol: str, cache_type: str, since_date: str) -> bool:
        """
        Check if a symbol was already checked for a cache type since a given date.
        
        Used by cache jobs to skip symbols that have already been processed.
        
        Args:
            symbol: Stock symbol
            cache_type: Type of cache ('form4', '10k', '8k', 'prices', 'transcripts', 'news')
            since_date: Date string (YYYY-MM-DD) - returns True if checked on or after this date
            
        Returns:
            True if the symbol was checked since since_date
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM cache_checks
                WHERE symbol = %s AND cache_type = %s AND last_checked >= %s
                LIMIT 1
            """, (symbol, cache_type, since_date))
            return cursor.fetchone() is not None
        finally:
            self.return_connection(conn)
    
    def get_cache_check(self, symbol: str, cache_type: str) -> Optional[Dict[str, Any]]:
        """
        Get cache check info for a symbol and cache type.
        
        Returns:
            Dict with last_checked and last_data_date, or None if not found
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_checked, last_data_date FROM cache_checks
                WHERE symbol = %s AND cache_type = %s
            """, (symbol, cache_type))
            row = cursor.fetchone()
            if row:
                return {
                    'last_checked': row[0].isoformat() if row[0] else None,
                    'last_data_date': row[1].isoformat() if row[1] else None
                }
            return None
        finally:
            self.return_connection(conn)
    
    def clear_cache_checks(self, cache_type: Optional[str] = None, 
                           symbol: Optional[str] = None) -> int:
        """
        Clear cache check records.
        
        Args:
            cache_type: Optional - clear only this cache type
            symbol: Optional - clear only this symbol
            
        Returns:
            Number of rows deleted
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if symbol and cache_type:
                cursor.execute(
                    "DELETE FROM cache_checks WHERE symbol = %s AND cache_type = %s",
                    (symbol, cache_type)
                )
            elif cache_type:
                cursor.execute(
                    "DELETE FROM cache_checks WHERE cache_type = %s",
                    (cache_type,)
                )
            elif symbol:
                cursor.execute(
                    "DELETE FROM cache_checks WHERE symbol = %s",
                    (symbol,)
                )
            else:
                cursor.execute("DELETE FROM cache_checks")
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            self.return_connection(conn)

    def save_earnings_history(self, symbol: str, year: int, eps: Optional[float], revenue: Optional[float], fiscal_end: str = None, debt_to_equity: float = None, period: str = 'annual', net_income: float = None, dividend_amount: float = None, operating_cash_flow: float = None, capital_expenditures: float = None, free_cash_flow: float = None, shareholder_equity: float = None, shares_outstanding: float = None, cash_and_cash_equivalents: float = None):
        """Save earnings history for a single year/period."""
        sql = """
            INSERT INTO earnings_history (
                symbol, year, earnings_per_share, revenue, fiscal_end, debt_to_equity, period,
                net_income, dividend_amount, operating_cash_flow, capital_expenditures, free_cash_flow, shareholder_equity, shares_outstanding, cash_and_cash_equivalents, last_updated
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (symbol, year, period) DO UPDATE SET
                earnings_per_share = EXCLUDED.earnings_per_share,
                revenue = EXCLUDED.revenue,
                fiscal_end = COALESCE(EXCLUDED.fiscal_end, earnings_history.fiscal_end),
                debt_to_equity = COALESCE(EXCLUDED.debt_to_equity, earnings_history.debt_to_equity),
                net_income = COALESCE(EXCLUDED.net_income, earnings_history.net_income),
                dividend_amount = COALESCE(EXCLUDED.dividend_amount, earnings_history.dividend_amount),
                operating_cash_flow = COALESCE(EXCLUDED.operating_cash_flow, earnings_history.operating_cash_flow),
                capital_expenditures = COALESCE(EXCLUDED.capital_expenditures, earnings_history.capital_expenditures),
                free_cash_flow = COALESCE(EXCLUDED.free_cash_flow, earnings_history.free_cash_flow),
                shareholder_equity = COALESCE(EXCLUDED.shareholder_equity, earnings_history.shareholder_equity),
                shares_outstanding = COALESCE(EXCLUDED.shares_outstanding, earnings_history.shares_outstanding),
                cash_and_cash_equivalents = COALESCE(EXCLUDED.cash_and_cash_equivalents, earnings_history.cash_and_cash_equivalents),
                last_updated = CURRENT_TIMESTAMP
        """
        args = (symbol, year, eps, revenue, fiscal_end, debt_to_equity, period, net_income, dividend_amount, operating_cash_flow, capital_expenditures, free_cash_flow, shareholder_equity, shares_outstanding, cash_and_cash_equivalents)
        self.write_queue.put((sql, args))

    def clear_quarterly_earnings(self, symbol: str) -> int:
        """
        Delete all quarterly earnings records for a symbol.
        
        Used before force-refresh to ensure stale quarterly data is removed
        before inserting fresh data from EDGAR.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Number of rows deleted
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM earnings_history 
                WHERE symbol = %s AND period IN ('Q1', 'Q2', 'Q3', 'Q4')
            """, (symbol,))
            deleted = cursor.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"[{symbol}] Cleared {deleted} quarterly earnings records for force refresh")
            return deleted
        finally:
            self.return_connection(conn)

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
                SELECT sm.*, s.company_name, s.exchange, 
                       s.sector, 
                       s.country, s.ipo_year
                 FROM stock_metrics sm
                 JOIN stocks s ON sm.symbol = s.symbol
                 WHERE sm.symbol = %s
            """, (symbol,))
            row = cursor.fetchone()

            if not row:
                return None
            
            # Use cursor.description to dynamically map column names to values
            # This automatically handles columns added via migrations (price_target_*, analyst_*, short_*, etc.)
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        finally:
            self.return_connection(conn)

    def get_recently_updated_stocks(self, since_timestamp: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get stocks that have been updated since the given timestamp.
        Used for real-time UI updates.
        
        Args:
            since_timestamp: ISO format timestamp string
            limit: Max number of updates to return
            
        Returns:
            List of dictionaries with updated fields (price, change, etc.)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                WITH recent_earnings AS (
                    SELECT 
                        symbol, 
                        net_income,
                        year,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY year DESC) as rn,
                        COUNT(*) OVER (PARTITION BY symbol) as total_years
                    FROM earnings_history
                    -- Optimization: We could filter by symbol if we had the list upfront, 
                    -- but here we filter by joining with the results of the main query.
                    -- Actually, simpler to do it in one query.
                ),
                growth_calc AS (
                    SELECT 
                        t1.symbol,
                        t1.net_income as end_ni,
                        t2.net_income as start_ni,
                        (t1.year - t2.year) as years_diff
                    FROM recent_earnings t1
                    JOIN recent_earnings t2 ON t1.symbol = t2.symbol 
                    WHERE t1.rn = 1  -- Most recent
                      AND t2.rn = LEAST(5, t1.total_years) -- 5th most recent (or oldest if < 5)
                      AND t1.year > t2.year -- Ensure strictly newer
                      AND t2.net_income != 0 -- Avoid div by zero
                      AND t2.net_income IS NOT NULL
                      AND t1.net_income IS NOT NULL
                ),
                calculated_metrics AS (
                    SELECT 
                        g.symbol,
                        -- Linear Growth Rate Formula: ((End - Start) / |Start|) / Years * 100
                        (((g.end_ni - g.start_ni) / ABS(g.start_ni)) / NULLIF(g.years_diff, 0)) * 100 as earnings_cagr
                    FROM growth_calc g
                )
                SELECT 
                    sm.symbol, sm.price, sm.pe_ratio, sm.market_cap, 
                    sm.forward_pe, sm.forward_peg_ratio,
                    sm.dividend_yield, sm.beta, 
                    cm.earnings_cagr,
                    sm.last_price_updated as last_updated
                FROM stock_metrics sm
                LEFT JOIN calculated_metrics cm ON sm.symbol = cm.symbol
                WHERE sm.last_price_updated > %s
                ORDER BY sm.last_price_updated DESC
                LIMIT %s
            """, (since_timestamp, limit))
            
            updates = []
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                for row in cursor.fetchall():
                    # Handle datetime serialization for last_updated
                    row_dict = dict(zip(columns, row))
                    if isinstance(row_dict.get('last_updated'), datetime):
                        row_dict['last_updated'] = row_dict['last_updated'].isoformat()
                    
                    # Calculate PEG Ratio on the fly (Lynch Style: PE / Growth)
                    pe = row_dict.get('pe_ratio')
                    growth = row_dict.get('earnings_cagr')
                    
                    # Ensure minimal growth for valid PEG (Lynch preferred > 0, usually > 5-10)
                    if pe and growth and growth > 0:
                        row_dict['peg_ratio'] = round(pe / growth, 2)
                    else:
                        row_dict['peg_ratio'] = None

                    updates.append(row_dict)
                
            return updates
        except Exception as e:
            # Handle invalid timestamp format gracefully
            print(f"Error fetching recently updated stocks: {e}")
            return []
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
                SELECT year, earnings_per_share, revenue, fiscal_end, debt_to_equity, period,
                       net_income, dividend_amount, operating_cash_flow, capital_expenditures,
                       free_cash_flow, shareholder_equity, shares_outstanding, cash_and_cash_equivalents, last_updated
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
                    'shareholder_equity': row[11],
                    'shares_outstanding': row[12],
                    'cash_and_cash_equivalents': row[13],
                    'last_updated': row[14]
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


    def search_stocks(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search stocks by symbol or company name.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            
        Returns:
            List of dictionaries with 'symbol' and 'company_name'
        """
        if not query or len(query.strip()) == 0:
            return []
            
        search_term = f"%{query.strip()}%"
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, company_name 
                FROM stocks 
                WHERE symbol ILIKE %s OR company_name ILIKE %s 
                ORDER BY 
                    CASE 
                        WHEN symbol ILIKE %s THEN 0  -- Exact symbol match priority
                        WHEN symbol ILIKE %s THEN 1  -- Starts with symbol priority
                        ELSE 2 
                    END,
                    symbol 
                LIMIT %s
            """, (search_term, search_term, query, f"{query}%", limit))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    'symbol': row[0],
                    'company_name': row[1]
                })
                
            return results
        except Exception as e:
            logger.error(f"Error searching stocks: {e}")
            return []
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

    def save_lynch_analysis(self, user_id: int, symbol: str, analysis_text: str, model_version: str, character_id: str = 'lynch'):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lynch_analyses
                (user_id, symbol, character_id, analysis_text, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol, character_id) DO UPDATE SET
                    analysis_text = EXCLUDED.analysis_text,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, character_id, analysis_text, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_lynch_analysis(self, user_id: int, symbol: str, character_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if character_id is None:
            character_id = self.get_user_character(user_id)

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, analysis_text, generated_at, model_version, character_id
                FROM lynch_analyses
                WHERE user_id = %s AND symbol = %s AND character_id = %s
            """, (user_id, symbol, character_id))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'symbol': row[0],
                'analysis_text': row[1],
                'generated_at': row[2],
                'model_version': row[3],
                'character_id': row[4]
            }
        finally:
            self.return_connection(conn)

    def set_chart_analysis(self, user_id: int, symbol: str, section: str, analysis_text: str, model_version: str, character_id: str = 'lynch'):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chart_analyses
                (user_id, symbol, section, character_id, analysis_text, generated_at, model_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol, section, character_id) DO UPDATE SET
                    analysis_text = EXCLUDED.analysis_text,
                    generated_at = EXCLUDED.generated_at,
                    model_version = EXCLUDED.model_version
            """, (user_id, symbol, section, character_id, analysis_text, datetime.now(), model_version))
            conn.commit()
        finally:
            self.return_connection(conn)

    def get_chart_analysis(self, user_id: int, symbol: str, section: str, character_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if character_id is None:
            character_id = self.get_user_character(user_id)

        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, section, analysis_text, generated_at, model_version, character_id
                FROM chart_analyses
                WHERE user_id = %s AND symbol = %s AND section = %s AND character_id = %s
            """, (user_id, symbol, section, character_id))
            row = cursor.fetchone()

            if not row:
                return None

            return {
                'symbol': row[0],
                'section': row[1],
                'analysis_text': row[2],
                'generated_at': row[3],
                'model_version': row[4],
                'character_id': row[5]
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

    # DEPRECATED: def get_session_results(self, session_id: int) -> List[Dict[str, Any]]:
        # """Get all results for a screening session"""
        # conn = self.get_connection()
        # try:
            # cursor = conn.cursor()
            # cursor.execute("""
                # SELECT symbol, company_name, country, market_cap, sector, ipo_year,
                       # price, pe_ratio, peg_ratio, debt_to_equity, institutional_ownership,
                       # dividend_yield, earnings_cagr, revenue_cagr, consistency_score,
                       # peg_status, debt_status, institutional_ownership_status, overall_status,
                       # overall_score, scored_at
                # FROM screening_results
                # WHERE session_id = %s
                # ORDER BY id ASC
            # """, (session_id,))
            # rows = cursor.fetchall()

            # results = []
            # for row in rows:
                # results.append({
                    # 'symbol': row[0],
                    # 'company_name': row[1],
                    # 'country': row[2],
                    # 'market_cap': row[3],
                    # 'sector': row[4],
                    # 'ipo_year': row[5],
                    # 'price': row[6],
                    # 'pe_ratio': row[7],
                    # 'peg_ratio': row[8],
                    # 'debt_to_equity': row[9],
                    # 'institutional_ownership': row[10],
                    # 'dividend_yield': row[11],
                    # 'earnings_cagr': row[12],
                    # 'revenue_cagr': row[13],
                    # 'consistency_score': row[14],
                    # 'peg_status': row[15],
                    # 'debt_status': row[16],
                    # 'institutional_ownership_status': row[17],
                    # 'overall_status': row[18],
                    # 'overall_score': row[19],
                    # 'scored_at': row[20]
                # })

            # return results
        # finally:
            # self.return_connection(conn)

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
             overall_status, overall_score, scored_at,
             roe, owner_earnings, debt_to_earnings, gross_margin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            datetime.now(),
            result_data.get('roe'),
            result_data.get('owner_earnings'),
            result_data.get('debt_to_earnings'),
            result_data.get('gross_margin')
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
                'overall_score', 'peg_score', 'debt_score', 'institutional_ownership_score',
                'roe', 'owner_earnings', 'debt_to_earnings', 'gross_margin'
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
                       overall_score,
                       roe, owner_earnings, debt_to_earnings, gross_margin
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
                # Secondary sort by overall_score for deterministic ordering within status groups
                order_expr = f"{status_rank_expr} {sort_dir.upper()}, COALESCE(overall_score, 0) DESC"
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
                    'overall_score': row[22],
                    'roe': row[23],
                    'owner_earnings': row[24],
                    'debt_to_earnings': row[25],
                    'gross_margin': row[26]
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

    # DEPRECATED: def cleanup_old_sessions(self, keep_count: int = 2):
        # conn = self.get_connection()
        # try:
            # cursor = conn.cursor()

            # cursor.execute("""
                # SELECT id FROM screening_sessions
                # ORDER BY created_at DESC
                # OFFSET %s
            # """, (keep_count,))
            # old_session_ids = [row[0] for row in cursor.fetchall()]

            # for session_id in old_session_ids:
                # cursor.execute("DELETE FROM screening_sessions WHERE id = %s", (session_id,))

            # conn.commit()
        # finally:
            # self.return_connection(conn)

    def create_user(self, google_id: str, email: str, name: str = None, picture: str = None) -> int:
        """Create a new user and return their user_id"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (google_id, email, name, picture, created_at, last_login, theme)
                VALUES (%s, %s, %s, %s, %s, %s, 'midnight')
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

    def create_user_with_password(self, email: str, password_hash: str, name: str = None, verification_code: str = None, code_expires_at: datetime = None) -> int:
        """Create a new user with email/password and return their user_id"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # is_verified defaults to False for password users (if code provided), True otherwise
            is_verified = False if verification_code else True
            
            cursor.execute("""
                INSERT INTO users (email, password_hash, name, created_at, last_login, is_verified, verification_code, code_expires_at, theme)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'midnight')
                RETURNING id
            """, (email, password_hash, name, datetime.now(), datetime.now(), is_verified, verification_code, code_expires_at))
            user_id = cursor.fetchone()[0]
            conn.commit()
            return user_id
        finally:
            self.return_connection(conn)

    def verify_user_otp(self, email: str, code: str) -> bool:
        """Verify a user by email and OTP code"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Debug: Check what's in the DB for this email
            cursor.execute("""
                SELECT verification_code, code_expires_at, is_verified, NOW() 
                FROM users WHERE email = %s
            """, (email,))
            debug_row = cursor.fetchone()
            if debug_row:
                logger.info(f"OTP DEBUG: Email={email}, StoredCode={debug_row[0]}, Expires={debug_row[1]}, Verified={debug_row[2]}, DB_NOW={debug_row[3]}")
                logger.info(f"OTP DEBUG: InputCode={code}")
            else:
                logger.info(f"OTP DEBUG: Email={email} NOT FOUND")

            # Check if code matches and is not expired
            cursor.execute("""
                SELECT id FROM users 
                WHERE email = %s 
                AND verification_code = %s 
                AND code_expires_at > NOW()
                AND is_verified = FALSE
            """, (email, code))
            
            user = cursor.fetchone()
            
            if user:
                # Mark as verified and clear code
                cursor.execute("""
                    UPDATE users 
                    SET is_verified = TRUE, verification_code = NULL, code_expires_at = NULL 
                    WHERE id = %s
                """, (user[0],))
                conn.commit()
                return True
                
            return False
        finally:
            self.return_connection(conn)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            return cursor.fetchone()
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

    def get_user_character(self, user_id: int) -> str:
        """Get user's active investment character"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT active_character FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else 'lynch'
        finally:
            self.return_connection(conn)

    def set_user_character(self, user_id: int, character_id: str):
        """Set user's active investment character"""
        sql = "UPDATE users SET active_character = %s WHERE id = %s"
        args = (character_id, user_id)
        self.write_queue.put((sql, args))

    def get_user_theme(self, user_id: int) -> str:
        """Get user's active theme"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT theme FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else 'light'
        finally:
            self.return_connection(conn)

    def set_user_theme(self, user_id: int, theme: str):
        """Set user's active theme"""
        sql = "UPDATE users SET theme = %s WHERE id = %s"
        args = (theme, user_id)
        self.write_queue.put((sql, args))

    def mark_onboarding_complete(self, user_id: int):
        """Mark user as having completed the onboarding flow"""
        sql = "UPDATE users SET has_completed_onboarding = TRUE WHERE id = %s"
        args = (user_id,)
        self.write_queue.put((sql, args))
        self.flush()

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

    # =========================================================================
    # Paper Trading Portfolio Methods
    # =========================================================================

    def create_portfolio(self, user_id: int, name: str, initial_cash: float = 100000.0) -> int:
        """Create a new paper trading portfolio for a user"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolios (user_id, name, initial_cash)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (user_id, name, initial_cash))
            portfolio_id = cursor.fetchone()[0]
            conn.commit()
            return portfolio_id
        finally:
            self.return_connection(conn)

    def get_portfolio(self, portfolio_id: int) -> Optional[Dict[str, Any]]:
        """Get a portfolio by ID"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, user_id, name, initial_cash, created_at
                FROM portfolios
                WHERE id = %s
            """, (portfolio_id,))
            return cursor.fetchone()
        finally:
            self.return_connection(conn)

    def get_user_portfolios(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all portfolios for a user"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, user_id, name, initial_cash, created_at
                FROM portfolios
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def rename_portfolio(self, portfolio_id: int, new_name: str):
        """Rename a portfolio"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE portfolios SET name = %s WHERE id = %s
            """, (new_name, portfolio_id))
            conn.commit()
        finally:
            self.return_connection(conn)

    def delete_portfolio(self, portfolio_id: int, user_id: int) -> bool:
        """Delete a portfolio (verifies ownership). Returns True if deleted."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM portfolios
                WHERE id = %s AND user_id = %s
            """, (portfolio_id, user_id))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self.return_connection(conn)

    def record_transaction(
        self,
        portfolio_id: int,
        symbol: str,
        transaction_type: str,
        quantity: int,
        price_per_share: float,
        note: str = None
    ) -> int:
        """Record a buy or sell transaction"""
        total_value = quantity * price_per_share
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_transactions
                (portfolio_id, symbol, transaction_type, quantity, price_per_share, total_value, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (portfolio_id, symbol, transaction_type, quantity, price_per_share, total_value, note))
            tx_id = cursor.fetchone()[0]
            conn.commit()
            return tx_id
        finally:
            self.return_connection(conn)

    def get_portfolio_transactions(self, portfolio_id: int) -> List[Dict[str, Any]]:
        """Get all transactions for a portfolio"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, portfolio_id, symbol, transaction_type, quantity,
                       price_per_share, total_value, executed_at, note
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                ORDER BY executed_at DESC
            """, (portfolio_id,))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def get_portfolio_holdings(self, portfolio_id: int) -> Dict[str, int]:
        """Compute current holdings from transactions.

        Returns a dict mapping symbol -> quantity for positions > 0.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol,
                       SUM(CASE 
                           WHEN transaction_type = 'BUY' THEN quantity 
                           WHEN transaction_type = 'SELL' THEN -quantity 
                           ELSE 0 
                       END) as net_qty
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                GROUP BY symbol
                HAVING SUM(CASE 
                           WHEN transaction_type = 'BUY' THEN quantity 
                           WHEN transaction_type = 'SELL' THEN -quantity 
                           ELSE 0 
                       END) > 0
            """, (portfolio_id,))
            return {row[0]: row[1] for row in cursor.fetchall()}
        finally:
            self.return_connection(conn)

    def get_portfolio_holdings_detailed(self, portfolio_id: int, use_live_prices: bool = True) -> List[Dict[str, Any]]:
        """Get detailed holdings information including purchase prices and current values.
        
        Args:
            portfolio_id: Portfolio to get holdings for
            use_live_prices: If True, fetch live prices from yfinance. If False, use cached prices.
            
        Returns:
            List of dicts with keys: symbol, quantity, avg_purchase_price, current_price,
                                     total_cost, current_value, gain_loss, gain_loss_percent
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Calculate average purchase price using weighted average of BUY transactions
            # This uses FIFO-like logic: we calculate the weighted average cost basis
            cursor.execute("""
                SELECT 
                    symbol,
                    SUM(CASE 
                        WHEN transaction_type = 'BUY' THEN quantity 
                        WHEN transaction_type = 'SELL' THEN -quantity 
                        ELSE 0 
                    END) as net_qty,
                    SUM(CASE WHEN transaction_type = 'BUY' THEN quantity * price_per_share ELSE 0 END) / 
                        NULLIF(SUM(CASE WHEN transaction_type = 'BUY' THEN quantity ELSE 0 END), 0) as avg_purchase_price
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                GROUP BY symbol
                HAVING SUM(CASE 
                        WHEN transaction_type = 'BUY' THEN quantity 
                        WHEN transaction_type = 'SELL' THEN -quantity 
                        ELSE 0 
                    END) > 0
            """, (portfolio_id,))
            
            holdings_data = cursor.fetchall()
            
            # Fetch current prices
            detailed_holdings = []
            
            if use_live_prices:
                from portfolio_service import fetch_current_price
                for symbol, quantity, avg_purchase_price in holdings_data:
                    current_price = fetch_current_price(symbol, db=self)
                    if current_price and avg_purchase_price:
                        total_cost = quantity * avg_purchase_price
                        current_value = quantity * current_price
                        gain_loss = current_value - total_cost
                        gain_loss_percent = (gain_loss / total_cost * 100) if total_cost > 0 else 0.0
                        
                        detailed_holdings.append({
                            'symbol': symbol,
                            'quantity': quantity,
                            'avg_purchase_price': avg_purchase_price,
                            'current_price': current_price,
                            'total_cost': total_cost,
                            'current_value': current_value,
                            'gain_loss': gain_loss,
                            'gain_loss_percent': gain_loss_percent
                        })
            else:
                # Use cached prices from stock_metrics
                for symbol, quantity, avg_purchase_price in holdings_data:
                    cursor.execute("SELECT price FROM stock_metrics WHERE symbol = %s", (symbol,))
                    row = cursor.fetchone()
                    if row and row[0] and avg_purchase_price:
                        current_price = row[0]
                        total_cost = quantity * avg_purchase_price
                        current_value = quantity * current_price
                        gain_loss = current_value - total_cost
                        gain_loss_percent = (gain_loss / total_cost * 100) if total_cost > 0 else 0.0
                        
                        detailed_holdings.append({
                            'symbol': symbol,
                            'quantity': quantity,
                            'avg_purchase_price': avg_purchase_price,
                            'current_price': current_price,
                            'total_cost': total_cost,
                            'current_value': current_value,
                            'gain_loss': gain_loss,
                            'gain_loss_percent': gain_loss_percent
                        })
            
            return detailed_holdings
        finally:
            self.return_connection(conn)

    def get_portfolio_cash(self, portfolio_id: int) -> float:
        """Compute current cash balance from initial cash and transactions.

        cash = initial_cash - sum(BUY totals) + sum(SELL totals)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Get initial cash
            cursor.execute("SELECT initial_cash FROM portfolios WHERE id = %s", (portfolio_id,))
            row = cursor.fetchone()
            if not row:
                return 0.0
            initial_cash = row[0]

            # Get transaction totals
            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN transaction_type = 'BUY' THEN total_value ELSE 0 END), 0) as buys,
                    COALESCE(SUM(CASE WHEN transaction_type = 'SELL' THEN total_value ELSE 0 END), 0) as sells,
                    COALESCE(SUM(CASE WHEN transaction_type = 'DIVIDEND' THEN total_value ELSE 0 END), 0) as dividends
                FROM portfolio_transactions
                WHERE portfolio_id = %s
            """, (portfolio_id,))
            buys, sells, dividends = cursor.fetchone()

            return initial_cash - buys + sells + dividends
        finally:
            self.return_connection(conn)

    def save_portfolio_snapshot(
        self,
        portfolio_id: int,
        total_value: float,
        cash_value: float,
        holdings_value: float
    ) -> int:
        """Save a portfolio value snapshot for historical tracking"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_value_snapshots
                (portfolio_id, total_value, cash_value, holdings_value)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (portfolio_id, total_value, cash_value, holdings_value))
            snapshot_id = cursor.fetchone()[0]
            conn.commit()
            return snapshot_id
        finally:
            self.return_connection(conn)

    def get_portfolio_snapshots(self, portfolio_id: int, limit: int = None) -> List[Dict[str, Any]]:
        """Get portfolio value history snapshots"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            query = """
                SELECT id, portfolio_id, total_value, cash_value, holdings_value, snapshot_at
                FROM portfolio_value_snapshots
                WHERE portfolio_id = %s
                ORDER BY snapshot_at ASC
            """
            if limit:
                query += f" LIMIT {limit}"
            cursor.execute(query, (portfolio_id,))
            return cursor.fetchall()
        finally:
            self.return_connection(conn)

    def get_portfolio_summary(self, portfolio_id: int, use_live_prices: bool = True) -> Optional[Dict[str, Any]]:
        """Get portfolio with computed cash, holdings value, and performance.

        Args:
            portfolio_id: Portfolio to summarize
            use_live_prices: If True, fetch live prices from yfinance for accuracy.
                             If False, use cached prices from stock_metrics (faster, for snapshots).
        """
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        cash = self.get_portfolio_cash(portfolio_id)
        holdings = self.get_portfolio_holdings(portfolio_id)
        holdings_detailed = self.get_portfolio_holdings_detailed(portfolio_id, use_live_prices)

        # Calculate holdings value from detailed holdings
        holdings_value = sum(h['current_value'] for h in holdings_detailed)

        total_value = cash + holdings_value
        initial_cash = portfolio['initial_cash']
        gain_loss = total_value - initial_cash
        gain_loss_percent = (gain_loss / initial_cash * 100) if initial_cash > 0 else 0.0

        return {
            'id': portfolio['id'],
            'user_id': portfolio['user_id'],
            'name': portfolio['name'],
            'initial_cash': initial_cash,
            'created_at': portfolio['created_at'],
            'cash': cash,
            'holdings': holdings,  # Keep simple dict for backward compatibility
            'holdings_detailed': holdings_detailed,  # New detailed holdings list
            'holdings_value': holdings_value,
            'total_value': total_value,
            'gain_loss': gain_loss,
            'gain_loss_percent': gain_loss_percent
        }

    def get_all_portfolios(self) -> List[Dict[str, Any]]:
        """Get all portfolios (for batch snapshot operations)"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
            cursor.execute("""
                SELECT id, user_id, name, initial_cash, created_at
                FROM portfolios
            """)
            return cursor.fetchall()
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
        Get stock symbols ordered alphabetically.
        
        Note: Scoring is now done on-demand via /api/sessions/latest, 
        so we no longer have pre-computed scores in the database.
        
        Args:
            limit: Optional max number of symbols to return
            country: Optional country filter (e.g., 'United States')
            
        Returns:
            List of stock symbols ordered alphabetically
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Get all stocks, optionally filtered by country
            if country:
                cursor.execute("SELECT symbol FROM stocks WHERE country = %s ORDER BY symbol", (country,))
            else:
                cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")
            
            symbols = [row[0] for row in cursor.fetchall()]
            return symbols[:limit] if limit else symbols
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
            try:
                value = json.loads(result[0])
            except (json.JSONDecodeError, TypeError):
                value = result[0]
                
            return {
                'key': key,
                'value': value,
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
                - period_end_date (optional): The fiscal period end date
        """
        for period, data in estimates_data.items():
            if not data:
                continue

            sql = """
                INSERT INTO analyst_estimates
                (symbol, period, eps_avg, eps_low, eps_high, eps_growth, eps_year_ago, eps_num_analysts,
                 revenue_avg, revenue_low, revenue_high, revenue_growth, revenue_year_ago, revenue_num_analysts,
                 period_end_date, fiscal_quarter, fiscal_year, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
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
                    period_end_date = EXCLUDED.period_end_date,
                    fiscal_quarter = EXCLUDED.fiscal_quarter,
                    fiscal_year = EXCLUDED.fiscal_year,
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
                data.get('period_end_date'),
                data.get('fiscal_quarter'),
                data.get('fiscal_year'),
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
                       revenue_num_analysts, period_end_date, fiscal_quarter, fiscal_year, last_updated
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
                    'period_end_date': row[13].isoformat() if row[13] else None,
                    'fiscal_quarter': row[14],
                    'fiscal_year': row[15],
                    'last_updated': row[16].isoformat() if row[16] else None
                }

            return result
        finally:
            self.return_connection(conn)

    def save_eps_trends(self, symbol: str, trends_data: Dict[str, Any]):
        """
        Save EPS trend data showing how estimates changed over 7/30/60/90 days.
        
        Args:
            symbol: Stock symbol
            trends_data: Dict with period keys ('0q', '+1q', '0y', '+1y') containing:
                - current, 7daysAgo, 30daysAgo, 60daysAgo, 90daysAgo
        """
        for period, data in trends_data.items():
            if not data:
                continue
                
            sql = """
                INSERT INTO eps_trends 
                (symbol, period, current_est, days_7_ago, days_30_ago, days_60_ago, days_90_ago, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period) DO UPDATE SET
                    current_est = EXCLUDED.current_est,
                    days_7_ago = EXCLUDED.days_7_ago,
                    days_30_ago = EXCLUDED.days_30_ago,
                    days_60_ago = EXCLUDED.days_60_ago,
                    days_90_ago = EXCLUDED.days_90_ago,
                    last_updated = NOW()
            """
            
            params = (
                symbol.upper(),
                period,
                data.get('current'),
                data.get('7daysAgo'),
                data.get('30daysAgo'),
                data.get('60daysAgo'),
                data.get('90daysAgo'),
            )
            
            self.write_queue.put((sql, params))

    def save_eps_revisions(self, symbol: str, revisions_data: Dict[str, Any]):
        """
        Save EPS revision counts (upward/downward revisions).
        
        Args:
            symbol: Stock symbol
            revisions_data: Dict with period keys ('0q', '+1q', '0y', '+1y') containing:
                - upLast7days, upLast30days, downLast7Days, downLast30days
        """
        for period, data in revisions_data.items():
            if not data:
                continue
                
            sql = """
                INSERT INTO eps_revisions 
                (symbol, period, up_7d, up_30d, down_7d, down_30d, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period) DO UPDATE SET
                    up_7d = EXCLUDED.up_7d,
                    up_30d = EXCLUDED.up_30d,
                    down_7d = EXCLUDED.down_7d,
                    down_30d = EXCLUDED.down_30d,
                    last_updated = NOW()
            """
            
            params = (
                symbol.upper(),
                period,
                data.get('upLast7days'),
                data.get('upLast30days'),
                data.get('downLast7Days'),
                data.get('downLast30days'),
            )
            
            self.write_queue.put((sql, params))

    def save_growth_estimates(self, symbol: str, growth_data: Dict[str, Any]):
        """
        Save growth estimates (stock vs index comparison).
        
        Args:
            symbol: Stock symbol
            growth_data: Dict with period keys ('0q', '+1q', '0y', '+1y', 'LTG') containing:
                - stockTrend, indexTrend
        """
        for period, data in growth_data.items():
            if not data:
                continue
                
            sql = """
                INSERT INTO growth_estimates 
                (symbol, period, stock_trend, index_trend, last_updated)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period) DO UPDATE SET
                    stock_trend = EXCLUDED.stock_trend,
                    index_trend = EXCLUDED.index_trend,
                    last_updated = NOW()
            """
            
            params = (
                symbol.upper(),
                period,
                data.get('stockTrend'),
                data.get('indexTrend'),
            )
            
            self.write_queue.put((sql, params))

    def save_analyst_recommendations(self, symbol: str, recommendations_data: List[Dict[str, Any]]):
        """
        Save monthly analyst buy/hold/sell distribution.
        
        Args:
            symbol: Stock symbol
            recommendations_data: List of dicts with:
                - period (0m, -1m, -2m, -3m), strongBuy, buy, hold, sell, strongSell
        """
        for data in recommendations_data:
            if not data:
                continue
                
            period = data.get('period')
            if period is None:
                continue
                
            sql = """
                INSERT INTO analyst_recommendations 
                (symbol, period_month, strong_buy, buy, hold, sell, strong_sell, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol, period_month) DO UPDATE SET
                    strong_buy = EXCLUDED.strong_buy,
                    buy = EXCLUDED.buy,
                    hold = EXCLUDED.hold,
                    sell = EXCLUDED.sell,
                    strong_sell = EXCLUDED.strong_sell,
                    last_updated = NOW()
            """
            
            params = (
                symbol.upper(),
                period,
                data.get('strongBuy'),
                data.get('buy'),
                data.get('hold'),
                data.get('sell'),
                data.get('strongSell'),
            )
            
            self.write_queue.put((sql, params))

    def update_forward_metrics(self, symbol: str, forward_data: Dict[str, Any]):
        """
        Update forward metrics columns in stock_metrics table.
        
        Args:
            symbol: Stock symbol
            forward_data: Dict containing forward metrics from yfinance info:
                - forward_pe, forward_eps, forward_peg_ratio
                - price_target_high, price_target_low, price_target_mean, price_target_median
                - analyst_rating, analyst_rating_score, analyst_count, recommendation_key
                - earnings_growth, earnings_quarterly_growth, revenue_growth
        """
        sql = """
            UPDATE stock_metrics SET
                forward_pe = COALESCE(%s, forward_pe),
                forward_eps = COALESCE(%s, forward_eps),
                forward_peg_ratio = COALESCE(%s, forward_peg_ratio),
                price_target_high = COALESCE(%s, price_target_high),
                price_target_low = COALESCE(%s, price_target_low),
                price_target_mean = COALESCE(%s, price_target_mean),
                price_target_median = COALESCE(%s, price_target_median),
                analyst_rating = COALESCE(%s, analyst_rating),
                analyst_rating_score = COALESCE(%s, analyst_rating_score),
                analyst_count = COALESCE(%s, analyst_count),
                recommendation_key = COALESCE(%s, recommendation_key),
                earnings_growth = COALESCE(%s, earnings_growth),
                earnings_quarterly_growth = COALESCE(%s, earnings_quarterly_growth),
                revenue_growth = COALESCE(%s, revenue_growth),
                last_updated = NOW()
            WHERE symbol = %s
        """
        
        params = (
            forward_data.get('forward_pe'),
            forward_data.get('forward_eps'),
            forward_data.get('forward_peg_ratio'),
            forward_data.get('price_target_high'),
            forward_data.get('price_target_low'),
            forward_data.get('price_target_mean'),
            forward_data.get('price_target_median'),
            forward_data.get('analyst_rating'),
            forward_data.get('analyst_rating_score'),
            forward_data.get('analyst_count'),
            forward_data.get('recommendation_key'),
            forward_data.get('earnings_growth'),
            forward_data.get('earnings_quarterly_growth'),
            forward_data.get('revenue_growth'),
            symbol.upper(),
        )
        
        self.write_queue.put((sql, params))

    def get_eps_trends(self, symbol: str) -> Dict[str, Any]:
        """Get EPS trend data for a symbol."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period, current_est, days_7_ago, days_30_ago, days_60_ago, days_90_ago
                FROM eps_trends WHERE symbol = %s
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            return {
                row[0]: {
                    'current': row[1],
                    '7_days_ago': row[2],
                    '30_days_ago': row[3],
                    '60_days_ago': row[4],
                    '90_days_ago': row[5],
                } for row in rows
            }
        finally:
            self.return_connection(conn)

    def get_eps_revisions(self, symbol: str) -> Dict[str, Any]:
        """Get EPS revision data for a symbol."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period, up_7d, up_30d, down_7d, down_30d
                FROM eps_revisions WHERE symbol = %s
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            return {
                row[0]: {
                    'up_7d': row[1],
                    'up_30d': row[2],
                    'down_7d': row[3],
                    'down_30d': row[4],
                } for row in rows
            }
        finally:
            self.return_connection(conn)

    def get_growth_estimates(self, symbol: str) -> Dict[str, Any]:
        """Get growth estimate data for a symbol."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period, stock_trend, index_trend
                FROM growth_estimates WHERE symbol = %s
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            return {
                row[0]: {
                    'stock_trend': row[1],
                    'index_trend': row[2],
                } for row in rows
            }
        finally:
            self.return_connection(conn)

    def get_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        """Get analyst recommendation history for a symbol."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT period_month, strong_buy, buy, hold, sell, strong_sell
                FROM analyst_recommendations 
                WHERE symbol = %s
                ORDER BY period_month DESC
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            return [
                {
                    'period': row[0],
                    'strong_buy': row[1],
                    'buy': row[2],
                    'hold': row[3],
                    'sell': row[4],
                    'strong_sell': row[5],
                } for row in rows
            ]
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
            except (json.JSONDecodeError, TypeError):
                value = row[1]

            settings[row[0]] = {
                'value': value,
                'description': row[2]
            }
        return settings

    def init_default_settings(self):
        """Initialize default settings if they don't exist.
        
        NOTE: Algorithm weights and thresholds are stored in algorithm_configurations table,
        NOT here. This only stores feature flags and other app settings.
        """
        logger.info("Initializing default settings (only adds missing settings, does not overwrite existing)")
        defaults = {
            # Feature flags only - weights/thresholds are in algorithm_configurations
            'feature_reddit_enabled': {'value': False, 'desc': 'Enable Reddit social sentiment tab (experimental)'},
            'feature_fred_enabled': {'value': False, 'desc': 'Enable FRED macroeconomic data features'},
            'feature_economy_link_enabled': {'value': False, 'desc': 'Show Economy link in navigation sidebar'},
        }

        current_settings = self.get_all_settings()

        added_count = 0
        for key, data in defaults.items():
            if key not in current_settings:
                self.set_setting(key, data['value'], data['desc'])
                added_count += 1

        # Migration: Remove weight/threshold entries from app_settings (they belong in algorithm_configurations)
        weight_keys_to_remove = [
            'weight_peg', 'weight_consistency', 'weight_debt', 'weight_ownership',
            'peg_excellent', 'peg_good', 'peg_fair',
            'debt_excellent', 'debt_good', 'debt_moderate',
            'inst_own_min', 'inst_own_max',
            'revenue_growth_excellent', 'revenue_growth_good', 'revenue_growth_fair',
            'income_growth_excellent', 'income_growth_good', 'income_growth_fair',
        ]
        removed_count = 0
        for key in weight_keys_to_remove:
            if key in current_settings:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM app_settings WHERE key = %s", (key,))
                conn.commit()
                self.return_connection(conn)
                removed_count += 1
                logger.info(f"Migrated: removed '{key}' from app_settings (now in algorithm_configurations)")

        logger.info(f"Default settings initialization complete: {added_count} new settings added, {removed_count} weight entries migrated out")
    # Backtest Results Methods
    def save_backtest_result(self, result: Dict[str, Any]):
        """Save a backtest result"""
        sql = """
            INSERT INTO backtest_results
             (symbol, backtest_date, years_back, start_price, end_price, total_return,
              historical_score, historical_rating, peg_score, debt_score, ownership_score,
              consistency_score, peg_ratio, earnings_cagr, revenue_cagr, debt_to_equity,
              institutional_ownership, roe, debt_to_earnings, gross_margin)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                 institutional_ownership = EXCLUDED.institutional_ownership,
                 roe = EXCLUDED.roe,
                 debt_to_earnings = EXCLUDED.debt_to_earnings,
                 gross_margin = EXCLUDED.gross_margin
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
            hist_data.get('institutional_ownership'),
            hist_data.get('roe'),
            hist_data.get('debt_to_earnings'),
            hist_data.get('gross_margin')
        )
        self.write_queue.put((sql, args))

    def get_backtest_results(self, years_back: int = None) -> List[Dict[str, Any]]:
        """Get backtest results, optionally filtered by years_back"""
        conn = self.get_connection()
    def get_backtest_results(self, years_back: int = None, symbol: str = None) -> List[Dict[str, Any]]:
        """Fetch saved backtest results from database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        columns = [
            'id', 'symbol', 'backtest_date', 'years_back', 'start_price', 'end_price', 
            'total_return', 'historical_score', 'historical_rating', 'peg_score', 
            'debt_score', 'ownership_score', 'consistency_score', 'peg_ratio', 
            'earnings_cagr', 'revenue_cagr', 'debt_to_equity', 'institutional_ownership', 
            'roe', 'debt_to_earnings', 'created_at', 'gross_margin'
        ]
        
        query_cols = ", ".join(columns)
        
        if years_back and symbol:
            query = f"SELECT {query_cols} FROM backtest_results WHERE years_back = %s AND symbol = %s"
            cursor.execute(query, (years_back, symbol))
        elif years_back:
            query = f"SELECT {query_cols} FROM backtest_results WHERE years_back = %s ORDER BY symbol"
            cursor.execute(query, (years_back,))
        elif symbol:
            query = f"SELECT {query_cols} FROM backtest_results WHERE symbol = %s ORDER BY years_back DESC"
            cursor.execute(query, (symbol,))
        else:
            query = f"SELECT {query_cols} FROM backtest_results ORDER BY years_back, symbol"
            cursor.execute(query)
        
        rows = cursor.fetchall()
        self.return_connection(conn)
        
        return [dict(zip(columns, row)) for row in rows]

    # Algorithm Configuration Methods
    def save_algorithm_config(self, config: Dict[str, Any], character: str = 'lynch', user_id: int = None) -> int:
        """Save an algorithm configuration and return its ID.

        Args:
            config: Configuration dict with weights and thresholds
            character: Character ID this config belongs to (default 'lynch')
            user_id: Optional user ID to associate this config with
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Helper to get value only if relevant to character
        def get_val(key, default, allowed_chars=None):
            if allowed_chars and character not in allowed_chars:
                return None
            return config.get(key, default)

        cursor.execute("""
            INSERT INTO algorithm_configurations
            (name, weight_peg, weight_consistency, weight_debt, weight_ownership, weight_roe, weight_debt_to_earnings, weight_gross_margin,
             peg_excellent, peg_good, peg_fair,
             debt_excellent, debt_good, debt_moderate,
             inst_own_min, inst_own_max,
             revenue_growth_excellent, revenue_growth_good, revenue_growth_fair,
             income_growth_excellent, income_growth_good, income_growth_fair,
             roe_excellent, roe_good, roe_fair,
             debt_to_earnings_excellent, debt_to_earnings_good, debt_to_earnings_fair,
             gross_margin_excellent, gross_margin_good, gross_margin_fair,
             correlation_5yr, correlation_10yr, is_active, character, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            config.get('name', 'Unnamed'),
            # Weights
            get_val('weight_peg', 0.50, ['lynch']),
            get_val('weight_consistency', 0.25, ['lynch', 'buffett']), # Common
            get_val('weight_debt', 0.15, ['lynch']),
            get_val('weight_ownership', 0.10, ['lynch']),
            get_val('weight_roe', 0.35, ['buffett']),
            get_val('weight_debt_to_earnings', 0.20, ['buffett']),
            get_val('weight_gross_margin', 0.20, ['buffett']),
            
            # Lynch Thresholds
            get_val('peg_excellent', 1.0, ['lynch']),
            get_val('peg_good', 1.5, ['lynch']),
            get_val('peg_fair', 2.0, ['lynch']),
            get_val('debt_excellent', 0.5, ['lynch']),
            get_val('debt_good', 1.0, ['lynch']),
            get_val('debt_moderate', 2.0, ['lynch']),
            get_val('inst_own_min', 0.20, ['lynch']),
            get_val('inst_own_max', 0.60, ['lynch']),
            
            # Common Thresholds (Growth)
            get_val('revenue_growth_excellent', 15.0, ['lynch', 'buffett']),
            get_val('revenue_growth_good', 10.0, ['lynch', 'buffett']),
            get_val('revenue_growth_fair', 5.0, ['lynch', 'buffett']),
            get_val('income_growth_excellent', 15.0, ['lynch', 'buffett']),
            get_val('income_growth_good', 10.0, ['lynch', 'buffett']),
            get_val('income_growth_fair', 5.0, ['lynch', 'buffett']),
            
            # Buffett Thresholds
            get_val('roe_excellent', 20.0, ['buffett']),
            get_val('roe_good', 15.0, ['buffett']),
            get_val('roe_fair', 10.0, ['buffett']),
            get_val('debt_to_earnings_excellent', 3.0, ['buffett']),
            get_val('debt_to_earnings_good', 5.0, ['buffett']),
            get_val('debt_to_earnings_fair', 8.0, ['buffett']),
            get_val('gross_margin_excellent', 50.0, ['buffett']),
            get_val('gross_margin_good', 40.0, ['buffett']),
            get_val('gross_margin_fair', 30.0, ['buffett']),
            
            config.get('correlation_5yr'),
            config.get('correlation_10yr'),
            bool(config.get('is_active', False)),  # Explicitly cast to bool for PostgreSQL
            character,
            user_id
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

    def get_user_algorithm_config(self, user_id: int, character: str = 'lynch') -> Optional[Dict[str, Any]]:
        """Get the most recent algorithm configuration for a specific user and character.
           Falls back to the most recent system default (user_id IS NULL) if per-user config not found.

        Args:
            user_id: User ID to fetch configuration for
            character: Character ID (e.g., 'lynch', 'buffett')

        Returns:
            Configuration dict or None if no config exists
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Priority:
        # 1. User specific config (user_id = X)
        # 2. Global default (user_id IS NULL)
        cursor.execute("""
            SELECT * FROM algorithm_configurations
            WHERE character = %s AND (user_id = %s OR user_id IS NULL)
            ORDER BY user_id ASC NULLS LAST, id DESC
            LIMIT 1
        """, (character, user_id))
        
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return None

        colnames = [desc[0] for desc in cursor.description]
        return dict(zip(colnames, row))

    def get_algorithm_config_for_character(self, character_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent algorithm configuration for a specific character.
           This returns global defaults only (where user_id is NULL).

        Args:
            character_id: Character ID (e.g., 'lynch', 'buffett')

        Returns:
            Configuration dict or None if no config exists for this character
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM algorithm_configurations
            WHERE character = %s AND user_id IS NULL
            ORDER BY id DESC
            LIMIT 1
        """, (character_id,))
        row = cursor.fetchone()
        self.return_connection(conn)

        if not row:
            return None

        colnames = [desc[0] for desc in cursor.description]
        return dict(zip(colnames, row))

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
        except Exception:
            conn.rollback()
            raise
        finally:
            self.return_connection(conn)

    def create_feedback(self, 
                        user_id: Optional[int], 
                        email: Optional[str],
                        feedback_text: str,
                        screenshot_data: Optional[str] = None,
                        page_url: Optional[str] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> int:
        """Create a new feedback entry"""
        import json
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_feedback (
                    user_id, email, feedback_text, screenshot_data, page_url, metadata, status
                ) VALUES (%s, %s, %s, %s, %s, %s, 'new')
                RETURNING id
            """, (
                user_id, 
                email, 
                feedback_text, 
                screenshot_data, 
                page_url, 
                json.dumps(metadata) if metadata else None
            ))
            feedback_id = cursor.fetchone()[0]
            conn.commit()
            return feedback_id
        except Exception:
            conn.rollback()
            raise
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

    def update_job_heartbeat(self, job_id: int, extend_minutes: int = 10):
        """Extend the claim expiration time for a running job"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE background_jobs
                SET claim_expires_at = NOW() + INTERVAL '%s minutes'
                WHERE id = %s
            """, (extend_minutes, job_id))
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

    # ==================== Social Sentiment Methods ====================
    
    def save_social_sentiment(self, posts: List[Dict[str, Any]]) -> int:
        """
        Batch save social sentiment posts (from Reddit).
        
        Args:
            posts: List of post dicts with id, symbol, title, score, etc.
            
        Returns:
            Number of posts saved/updated
        """
        if not posts:
            return 0
        
        sql = """
            INSERT INTO social_sentiment 
            (id, symbol, source, subreddit, title, selftext, url, author, 
             score, upvote_ratio, num_comments, sentiment_score, created_utc, published_at,
             conversation_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                score = EXCLUDED.score,
                upvote_ratio = EXCLUDED.upvote_ratio,
                num_comments = EXCLUDED.num_comments,
                sentiment_score = EXCLUDED.sentiment_score,
                conversation_json = EXCLUDED.conversation_json,
                fetched_at = CURRENT_TIMESTAMP
        """
        
        count = 0
        for post in posts:
            try:
                # Serialize conversation data to JSON
                import json
                conversation = post.get('conversation')
                conversation_json = json.dumps(conversation) if conversation else None
                
                args = (
                    post.get('id'),
                    post.get('symbol'),
                    post.get('source', 'reddit'),
                    post.get('subreddit'),
                    post.get('title'),
                    post.get('selftext', '')[:10000],  # Limit text size
                    post.get('url'),
                    post.get('author'),
                    post.get('score', 0),
                    post.get('upvote_ratio'),
                    post.get('num_comments', 0),
                    post.get('sentiment_score'),
                    post.get('created_utc'),
                    post.get('created_at'),
                    conversation_json,
                )
                self.write_queue.put((sql, args))
                count += 1
            except Exception as e:
                logger.error(f"Error saving social sentiment post {post.get('id')}: {e}")
        
        return count
    
    def get_social_sentiment(self, symbol: str, limit: int = 20, 
                            min_score: int = 0) -> List[Dict[str, Any]]:
        """
        Get social sentiment posts for a symbol.
        
        Args:
            symbol: Stock ticker
            limit: Max posts to return
            min_score: Minimum score filter
            
        Returns:
            List of post dicts sorted by score descending
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, source, subreddit, title, selftext, url, author,
                       score, upvote_ratio, num_comments, sentiment_score, 
                       created_utc, published_at, fetched_at, conversation_json
                FROM social_sentiment
                WHERE symbol = %s AND score >= %s
                ORDER BY score DESC
                LIMIT %s
            """, (symbol, min_score, limit))
            
            rows = cursor.fetchall()
            return [{
                'id': row[0],
                'symbol': row[1],
                'source': row[2],
                'subreddit': row[3],
                'title': row[4],
                'selftext': row[5],
                'url': row[6],
                'author': row[7],
                'score': row[8],
                'upvote_ratio': row[9],
                'num_comments': row[10],
                'sentiment_score': row[11],
                'created_utc': row[12],
                'published_at': row[13].isoformat() if row[13] else None,
                'fetched_at': row[14].isoformat() if row[14] else None,
                'conversation': row[15],  # JSONB is auto-parsed by psycopg2
            } for row in rows]
        finally:
            self.return_connection(conn)
    
    def get_social_sentiment_summary(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """
        Get aggregated social sentiment summary for a symbol.
        
        Args:
            symbol: Stock ticker
            days: Number of days to look back
            
        Returns:
            Dict with post_count, avg_score, avg_sentiment, top_subreddits
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as post_count,
                    AVG(score) as avg_score,
                    AVG(sentiment_score) as avg_sentiment,
                    SUM(num_comments) as total_comments
                FROM social_sentiment
                WHERE symbol = %s 
                  AND published_at >= NOW() - INTERVAL '%s days'
            """, (symbol, days))
            
            row = cursor.fetchone()
            
            # Get top subreddits
            cursor.execute("""
                SELECT subreddit, COUNT(*) as cnt
                FROM social_sentiment
                WHERE symbol = %s 
                  AND published_at >= NOW() - INTERVAL '%s days'
                GROUP BY subreddit
                ORDER BY cnt DESC
                LIMIT 5
            """, (symbol, days))
            
            subreddits = [{'name': r[0], 'count': r[1]} for r in cursor.fetchall()]
            
            return {
                'post_count': row[0] or 0,
                'avg_score': round(row[1], 1) if row[1] else 0,
                'avg_sentiment': round(row[2], 2) if row[2] else 0,
                'total_comments': row[3] or 0,
                'top_subreddits': subreddits,
            }
        finally:
            self.return_connection(conn)
    
    # =========================================================================
    # Agent Chat Methods
    # =========================================================================
    
    def create_agent_conversation(self, user_id: int) -> int:
        """
        Create a new agent conversation.
        
        Args:
            user_id: User ID
            
        Returns:
            conversation_id
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_conversations (user_id, created_at, last_message_at)
                VALUES (%s, NOW(), NOW())
                RETURNING id
            """, (user_id,))
            conversation_id = cursor.fetchone()[0]
            conn.commit()
            return conversation_id
        finally:
            self.return_connection(conn)
    
    def get_agent_conversations(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get user's agent conversations, ordered by last_message_at DESC.
        
        Args:
            user_id: User ID
            limit: Maximum number of conversations to return
            
        Returns:
            List of conversation dicts
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, created_at, last_message_at
                FROM agent_conversations
                WHERE user_id = %s
                ORDER BY last_message_at DESC
                LIMIT %s
            """, (user_id, limit))
            
            rows = cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'title': row[1],
                    'created_at': row[2].isoformat() if row[2] else None,
                    'last_message_at': row[3].isoformat() if row[3] else None,
                }
                for row in rows
            ]
        finally:
            self.return_connection(conn)
    
    def get_agent_messages(self, conversation_id: int) -> List[Dict[str, Any]]:
        """
        Get all messages for a conversation, ordered by created_at ASC.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            List of message dicts
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, role, content, tool_calls, created_at
                FROM agent_messages
                WHERE conversation_id = %s
                ORDER BY created_at ASC
            """, (conversation_id,))
            
            rows = cursor.fetchall()
            return [
                {
                    'id': row[0],
                    'role': row[1],
                    'content': row[2],
                    'tool_calls': row[3],
                    'created_at': row[4].isoformat() if row[4] else None,
                }
                for row in rows
            ]
        finally:
            self.return_connection(conn)
    
    def save_agent_message(self, conversation_id: int, role: str, content: str, tool_calls: dict = None):
        """
        Save a message to conversation and update last_message_at.
        
        Args:
            conversation_id: Conversation ID
            role: 'user' or 'assistant'
            content: Message content
            tool_calls: Optional tool execution details (JSON)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Insert message
            import json
            cursor.execute("""
                INSERT INTO agent_messages (conversation_id, role, content, tool_calls, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (conversation_id, role, content, json.dumps(tool_calls) if tool_calls else None))
            
            # Update conversation last_message_at
            cursor.execute("""
                UPDATE agent_conversations
                SET last_message_at = NOW()
                WHERE id = %s
            """, (conversation_id,))
            
            conn.commit()
        finally:
            self.return_connection(conn)
    
    def update_conversation_title(self, conversation_id: int, title: str):
        """
        Update conversation title (called after first message).

        Args:
            conversation_id: Conversation ID
            title: Conversation title (truncated from first message)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE agent_conversations
                SET title = %s
                WHERE id = %s
            """, (title[:50], conversation_id))  # Truncate to 50 chars
            conn.commit()
        finally:
            self.return_connection(conn)

    def delete_agent_conversation(self, conversation_id: int, user_id: int) -> bool:
        """
        Delete an agent conversation (with ownership verification).

        Args:
            conversation_id: Conversation ID to delete
            user_id: User ID (for ownership check)

        Returns:
            True if deleted, False if not found or not owned by user
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Delete only if owned by user (CASCADE will delete messages)
            cursor.execute("""
                DELETE FROM agent_conversations
                WHERE id = %s AND user_id = %s
            """, (conversation_id, user_id))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            self.return_connection(conn)
