# ABOUTME: Core database class providing connection pooling, background writes, and schema initialization
# ABOUTME: Handles PostgreSQL connections via psycopg3 with health checking and batch write operations

import psycopg
from psycopg_pool import ConnectionPool
import threading
import os
import queue
import time
import logging
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any, List, Set
import json

logger = logging.getLogger(__name__)


class DatabaseCore:
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
        # Initialize schema
        logger.info("Initializing database schema...")
        init_conn = self.connection_pool.getconn()
        try:
            # Use Advisory Lock to serialize schema migration across multiple workers
            # Lock ID: 8675309 (Arbitrary integer for this app's schema lock)
            LOCK_ID = 8675309
            cursor = init_conn.cursor()

            logger.info("Acquiring schema migration lock...")
            cursor.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))

            try:
                logger.info("Schema migration lock acquired. Checking/Updating schema...")
                self._init_schema_with_connection(init_conn)

                # Migration: Drop unused screening tables (refactored to use on-demand scoring)
                try:
                    cursor.execute("""
                        DROP TABLE IF EXISTS screening_results CASCADE;
                        DROP TABLE IF EXISTS screening_sessions CASCADE;
                    """)
                    # We commit everything at the end of the locked block
                    logger.info("Migration: Dropped screening_sessions and screening_results tables")
                except Exception as e:
                    logger.warning(f"Migration warning (drop screening tables): {e}")
                    # Don't rollback the whole thing just for this, but proceed

                logger.info("Database schema initialized successfully")

            finally:
                # Always release the lock
                logger.info("Releasing schema migration lock...")
                cursor.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
                init_conn.commit()

        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}", exc_info=True)
            try:
                init_conn.rollback()
            except:
                pass
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
