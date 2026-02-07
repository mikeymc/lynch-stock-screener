# ABOUTME: Application settings and algorithm configuration management
# ABOUTME: Handles key-value settings, default initialization, and per-user algorithm configs

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import json

logger = logging.getLogger(__name__)


class SettingsMixin:

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
            # psycopg3 automatically decodes JSONB
            value = result[0]

            return {
                'key': key,
                'value': value,
                'description': result[1]
            }

    def set_setting(self, key: str, value: Any, description: str = None):
        logger.info(f"Setting configuration: key='{key}', value={value}")
        conn = self.get_connection()
        cursor = conn.cursor()

        # psycopg3 auto-adapts dicts/lists to JSONB, but primitive types
        # (bool, int, str) need explicit wrapping via Json()
        from psycopg.types.json import Json
        json_value = Json(value)

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
            # psycopg3 automatically decodes JSONB to Python objects (bool, dict, list)
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
