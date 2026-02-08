# ABOUTME: Database DDL schema initialization for all application tables
# ABOUTME: Contains CREATE TABLE statements and schema migrations

import logging

logger = logging.getLogger(__name__)


class SchemaMixin:

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
                prev_close REAL,
                price_change REAL,
                price_change_pct REAL,
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

                -- prev_close (for daily change calculation)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'stock_metrics' AND column_name = 'prev_close') THEN
                    ALTER TABLE stock_metrics ADD COLUMN prev_close REAL;
                END IF;

                -- price_change (dollar amount change from previous close)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'stock_metrics' AND column_name = 'price_change') THEN
                    ALTER TABLE stock_metrics ADD COLUMN price_change REAL;
                END IF;

                -- price_change_pct (percentage change from previous close)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'stock_metrics' AND column_name = 'price_change_pct') THEN
                    ALTER TABLE stock_metrics ADD COLUMN price_change_pct REAL;
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
                total_debt REAL,
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
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'earnings_history' AND column_name = 'total_debt') THEN
                    ALTER TABLE earnings_history ADD COLUMN total_debt REAL;
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
            CREATE TABLE IF NOT EXISTS deliberations (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                symbol TEXT NOT NULL,
                deliberation_text TEXT NOT NULL,
                final_verdict TEXT CHECK (final_verdict IN ('BUY', 'WATCH', 'AVOID')),
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model_version TEXT,
                PRIMARY KEY (user_id, symbol),
                FOREIGN KEY (symbol) REFERENCES stocks(symbol)
            )
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

        # Migration: Add expertise_level column to users table
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'users' AND column_name = 'expertise_level') THEN
                    ALTER TABLE users ADD COLUMN expertise_level TEXT DEFAULT 'practicing';
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

        # Paper trading portfolios (must be created before alerts migration that references it)
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

        # Migration: Add automated trading columns to alerts
        cursor.execute("""
            DO $$
            BEGIN
                -- action_type (market_buy, market_sell, etc.)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alerts' AND column_name = 'action_type') THEN
                    ALTER TABLE alerts ADD COLUMN action_type TEXT;
                END IF;

                -- action_payload (JSON details like quantity)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alerts' AND column_name = 'action_payload') THEN
                    ALTER TABLE alerts ADD COLUMN action_payload JSONB;
                END IF;

                -- portfolio_id (target portfolio for the trade)
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alerts' AND column_name = 'portfolio_id') THEN
                    ALTER TABLE alerts ADD COLUMN portfolio_id INTEGER REFERENCES portfolios(id);
                END IF;

                -- action_note
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'alerts' AND column_name = 'action_note') THEN
                    ALTER TABLE alerts ADD COLUMN action_note TEXT;
                END IF;
            END $$;
        """)

        # Initialize remaining schema (misplaced code wrapper)
        self._init_rest_of_schema(conn)

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
                tier TEXT DEFAULT 'light',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        # Migration: Add tier column to background_jobs if it doesn't exist
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name = 'background_jobs' AND column_name = 'tier') THEN
                    ALTER TABLE background_jobs ADD COLUMN tier TEXT DEFAULT 'light';
                END IF;
            END $$;
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
                value JSONB,
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

        # Feature flag: Algorithm Tuning / Optimization
        cursor.execute("SELECT 1 FROM app_settings WHERE key = 'feature_algorithm_optimization_enabled'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO app_settings (key, value, description)
                VALUES ('feature_algorithm_optimization_enabled', 'false'::jsonb, 'Enable algorithm tuning/optimization features')
            """)
            conn.commit()

        # Migration: Convert app_settings.value to JSONB if it's currently TEXT
        cursor.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'app_settings' AND column_name = 'value'
        """)
        dtype = cursor.fetchone()
        if dtype and dtype[0] == 'text':
            logger.info("Migrating app_settings.value from TEXT to JSONB...")
            try:
                # 1. Fix known non-JSON formatting issues before casting
                cursor.execute("UPDATE app_settings SET value = TRIM(value)")

                # 2. Fix bare strings that might resemble bools but should be bools (or handled as such)
                # 'true' -> true (bool), '"true"' -> "true" (string).
                # We want boolean features to be boolean.
                cursor.execute("UPDATE app_settings SET value = 'true' WHERE value = '\"true\"' OR value = 'true'")
                cursor.execute("UPDATE app_settings SET value = 'false' WHERE value = '\"false\"' OR value = 'false'")

                # 3. Perform the alteration
                cursor.execute("ALTER TABLE app_settings ALTER COLUMN value TYPE JSONB USING value::jsonb")
                conn.commit()
                logger.info("Migration complete: app_settings.value is now JSONB")
            except Exception as e:
                logger.error(f"Failed to migrate app_settings to JSONB: {e}")
                conn.rollback()

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
            CREATE INDEX IF NOT EXISTS idx_news_articles_symbol_datetime
            ON news_articles(symbol, datetime DESC)
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

        # Migration: Add dividend_payment_date to portfolio_transactions
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'portfolio_transactions'
                    AND column_name = 'dividend_payment_date'
                ) THEN
                    ALTER TABLE portfolio_transactions ADD COLUMN dividend_payment_date DATE;
                END IF;
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

        # Migration: Add position_type column for tracking new vs addition trades
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'portfolio_transactions'
                    AND column_name = 'position_type'
                ) THEN
                    ALTER TABLE portfolio_transactions
                    ADD COLUMN position_type VARCHAR(20) CHECK (position_type IN ('new', 'addition', 'exit'));
                END IF;
            END $$;
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

        # Position entry tracking (for re-evaluation grace periods)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_entry_tracking (
                portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                symbol VARCHAR(10) NOT NULL,
                first_buy_date DATE NOT NULL,
                last_evaluated_date DATE,
                PRIMARY KEY (portfolio_id, symbol)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_position_entry_tracking_portfolio
            ON position_entry_tracking(portfolio_id)
        """)

        # ============================================================
        # Autonomous Investment Strategy Tables
        # ============================================================

        # Investment strategies defined by users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS investment_strategies (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,

                -- Screening conditions (JSON with universe filters, scoring requirements)
                conditions JSONB NOT NULL,

                -- Consensus configuration
                consensus_mode TEXT NOT NULL DEFAULT 'both_agree'
                    CHECK (consensus_mode IN ('both_agree', 'weighted_confidence', 'veto_power')),
                consensus_threshold REAL DEFAULT 70.0,

                -- Position sizing configuration
                position_sizing JSONB NOT NULL DEFAULT '{"method": "equal_weight", "max_position_pct": 5.0}',

                -- Exit conditions (profit targets, stop losses, quality rules)
                exit_conditions JSONB DEFAULT '{}',

                -- Execution schedule (cron format)
                schedule_cron TEXT DEFAULT '0 9 * * 1-5',
                enabled BOOLEAN DEFAULT true,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategies_user
            ON investment_strategies(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategies_enabled
            ON investment_strategies(enabled, schedule_cron)
        """)

        # Strategy execution runs (one per scheduled execution)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_runs (
                id SERIAL PRIMARY KEY,
                strategy_id INTEGER NOT NULL REFERENCES investment_strategies(id) ON DELETE CASCADE,

                -- Execution metadata
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),

                -- Summary statistics
                stocks_screened INTEGER DEFAULT 0,
                stocks_scored INTEGER DEFAULT 0,
                theses_generated INTEGER DEFAULT 0,
                trades_executed INTEGER DEFAULT 0,

                -- Benchmark data at time of run
                spy_price REAL,
                portfolio_value REAL,

                -- Error info if failed
                error_message TEXT,

                -- Full run log (JSON array of events)
                run_log JSONB DEFAULT '[]'
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_strategy
            ON strategy_runs(strategy_id, started_at DESC)
        """)

        # Thesis Refresh Queue (for dedicated background job)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS thesis_refresh_queue (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
                reason TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
                attempts INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_thesis_queue_status_priority
            ON thesis_refresh_queue(status, priority DESC)
        """)

        # Individual stock decisions within a run
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_decisions (
                id SERIAL PRIMARY KEY,
                run_id INTEGER NOT NULL REFERENCES strategy_runs(id) ON DELETE CASCADE,
                symbol TEXT NOT NULL,

                -- Scoring results from each character
                lynch_score REAL,
                lynch_status TEXT,
                buffett_score REAL,
                buffett_status TEXT,

                -- Combined/consensus result
                consensus_score REAL,
                consensus_verdict TEXT CHECK (consensus_verdict IN ('BUY', 'WATCH', 'AVOID', 'VETO')),

                -- Thesis generation results
                thesis_verdict TEXT CHECK (thesis_verdict IN ('BUY', 'WATCH', 'AVOID')),
                thesis_summary TEXT,
                thesis_full TEXT,

                -- DCF results
                dcf_fair_value REAL,
                dcf_upside_pct REAL,

                -- Final decision and execution
                final_decision TEXT CHECK (final_decision IN ('BUY', 'SKIP', 'HOLD', 'SELL')),
                decision_reasoning TEXT,

                -- If trade executed
                transaction_id INTEGER REFERENCES portfolio_transactions(id),
                shares_traded INTEGER,
                trade_price REAL,
                position_value REAL,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_run
            ON strategy_decisions(run_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_decisions_symbol
            ON strategy_decisions(symbol)
        """)

        # Benchmark tracking (daily SPY snapshots)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS benchmark_snapshots (
                id SERIAL PRIMARY KEY,
                snapshot_date DATE NOT NULL UNIQUE,
                spy_price REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_benchmark_date
            ON benchmark_snapshots(snapshot_date)
        """)

        # Strategy performance vs benchmark
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_performance (
                id SERIAL PRIMARY KEY,
                strategy_id INTEGER NOT NULL REFERENCES investment_strategies(id) ON DELETE CASCADE,
                snapshot_date DATE NOT NULL,

                portfolio_value REAL NOT NULL,
                portfolio_return_pct REAL,
                spy_return_pct REAL,
                alpha REAL,

                UNIQUE(strategy_id, snapshot_date)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_perf_strategy
            ON strategy_performance(strategy_id, snapshot_date)
        """)

        # Initialize feature_dashboard_enabled setting (default: false)
        cursor.execute("SELECT 1 FROM app_settings WHERE key = 'feature_dashboard_enabled'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO app_settings (key, value, description)
                VALUES ('feature_dashboard_enabled', 'false', 'Show Dashboard link in navigation sidebar')
            """)
            conn.commit()

        # System User Migration (Shared Cache)
        # 1. Ensure System User (ID 0) exists
        cursor.execute("""
            INSERT INTO users (id, google_id, email, name)
            VALUES (0, 'system_user', 'system@lynch.app', 'System')
            ON CONFLICT (id) DO NOTHING;
        """)

        # 2. Migrate existing theses from User 1 to User 0 (if not conflicting)
        cursor.execute("""
            UPDATE lynch_analyses
            SET user_id = 0
            WHERE user_id = 1
            AND NOT EXISTS (
                SELECT 1 FROM lynch_analyses target
                WHERE target.user_id = 0
                AND target.symbol = lynch_analyses.symbol
                AND target.character_id = lynch_analyses.character_id
            );
        """)

        # 3. Migrate existing deliberations from User 1 to User 0
        cursor.execute("""
            UPDATE deliberations
            SET user_id = 0
            WHERE user_id = 1
            AND NOT EXISTS (
                SELECT 1 FROM deliberations target
                WHERE target.user_id = 0
                AND target.symbol = deliberations.symbol
            );
        """)

        conn.commit()
