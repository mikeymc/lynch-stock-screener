# ABOUTME: Parses and evaluates strategy conditions against stock data
# ABOUTME: Applies universe filters to return candidate symbols

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class UniverseFilter:
    """Parses and evaluates strategy conditions against stock data."""

    def __init__(self, db):
        self.db = db

    def filter_universe(self, conditions: Dict[str, Any]) -> List[str]:
        """Apply universe filters to return candidate symbols.

        Args:
            conditions: Strategy conditions with 'universe' key containing filters

        Returns:
            List of symbols that match all filters
        """
        filters = conditions.get('universe', {}).get('filters', [])
        if not filters:
            # No filters = return all screened stocks
            return self._get_all_screened_symbols()

        symbols = self._get_all_screened_symbols()
        for filter_spec in filters:
            symbols = self._apply_filter(symbols, filter_spec)

        return symbols

    def _get_all_screened_symbols(self) -> List[str]:
        """Get all symbols from the screening results."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT symbol FROM stock_metrics
                WHERE price IS NOT NULL
            """)
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.db.return_connection(conn)

    def _apply_filter(self, symbols: List[str], filter_spec: Dict[str, Any]) -> List[str]:
        """Apply a single filter to the symbol list.

        Filter spec format:
        {
            "field": "price_vs_52wk_high",  # or market_cap, pe_ratio, etc.
            "operator": "<=",  # <, >, <=, >=, ==, !=
            "value": -20
        }
        """
        field = filter_spec.get('field')
        operator = filter_spec.get('operator')
        value = filter_spec.get('value')

        if not all([field, operator, value is not None]):
            return symbols

        # Map field names to database columns
        field_mapping = {
            'symbol': 'symbol',
            'price_vs_52wk_high': 'price_change_52w_pct',
            'market_cap': 'market_cap',
            'pe_ratio': 'pe_ratio',
            'peg_ratio': 'peg_ratio',
            'debt_to_equity': 'debt_to_equity',
            'price': 'price',
            'sector': 'sector',
        }

        db_field = field_mapping.get(field, field)

        # Build SQL operator
        op_mapping = {
            '<': '<', '>': '>', '<=': '<=', '>=': '>=',
            '==': '=', '!=': '<>'
        }
        sql_op = op_mapping.get(operator, '=')

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            placeholders = ', '.join(['%s'] * len(symbols))
            query = f"""
                SELECT symbol FROM stock_metrics
                WHERE symbol IN ({placeholders})
                AND {db_field} {sql_op} %s
            """
            cursor.execute(query, symbols + [value])
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.db.return_connection(conn)
