# ABOUTME: Strategy management tool executors for the Smart Chat Agent
# ABOUTME: Handles reading, updating, and inspecting investment strategies and their run history

import json
from typing import Dict, Any, Optional


class StrategyToolsMixin:
    """Mixin providing strategy management tool executor methods."""

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _verify_strategy_ownership(self, strategy_id: int, user_id: int) -> Dict[str, Any]:
        """
        Fetch strategy and verify it belongs to user_id.

        Returns the strategy dict on success, or {'error': ..., 'success': False} on failure.
        Callers check for 'error' key to short-circuit.
        """
        strategy = self.db.get_strategy(strategy_id)
        if not strategy:
            return {"success": False, "error": f"Strategy {strategy_id} not found."}
        if strategy['user_id'] != user_id:
            return {"success": False, "error": "Strategy not found or unauthorized access."}
        return dict(strategy)

    @staticmethod
    def _parse_json_fields(strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON string fields that the DB may return as strings."""
        for field in ('conditions', 'position_sizing', 'exit_conditions'):
            if field in strategy and isinstance(strategy[field], str):
                try:
                    strategy[field] = json.loads(strategy[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return strategy

    # =========================================================================
    # Strategy Management Executor Methods
    # =========================================================================

    def _get_my_strategies(self, user_id: int) -> Dict[str, Any]:
        """List all strategies for the user with status, alpha, and last run info."""
        try:
            strategies = self.db.get_user_strategies(user_id)
            return {
                "success": True,
                "strategies": [dict(s) for s in strategies],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_strategy(self, strategy_id: int, user_id: int) -> Dict[str, Any]:
        """Get full strategy configuration including filters, consensus, sizing, and schedule."""
        try:
            result = self._verify_strategy_ownership(strategy_id, user_id)
            if 'error' in result:
                return result
            strategy = self._parse_json_fields(result)
            return {"success": True, "strategy": strategy}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _update_strategy(
        self,
        strategy_id: int,
        user_id: int,
        name: str = None,
        description: str = None,
        enabled: bool = None,
        consensus_mode: str = None,
        consensus_threshold: float = None,
        position_sizing_method: str = None,
        max_position_pct: float = None,
        max_positions: int = None,
        profit_target_pct: float = None,
        stop_loss_pct: float = None,
        filters=None,
    ) -> Dict[str, Any]:
        """
        Modify any strategy field conversationally.

        position_sizing and exit_conditions use read-modify-write (preserves unmentioned fields).
        filters fully replaces conditions.filters.
        Direct fields (name, enabled, consensus_mode, etc.) map straight through.
        """
        try:
            result = self._verify_strategy_ownership(strategy_id, user_id)
            if 'error' in result:
                return result

            strategy = self._parse_json_fields(result)
            update_kwargs = {}

            # Direct scalar fields
            if name is not None:
                update_kwargs['name'] = name
            if description is not None:
                update_kwargs['description'] = description
            if enabled is not None:
                update_kwargs['enabled'] = enabled
            if consensus_mode is not None:
                update_kwargs['consensus_mode'] = consensus_mode
            if consensus_threshold is not None:
                update_kwargs['consensus_threshold'] = consensus_threshold

            # position_sizing: read-modify-write
            if position_sizing_method is not None or max_position_pct is not None or max_positions is not None:
                existing_ps = strategy.get('position_sizing') or {}
                if position_sizing_method is not None:
                    existing_ps['method'] = position_sizing_method
                if max_position_pct is not None:
                    existing_ps['max_position_pct'] = max_position_pct
                if max_positions is not None:
                    existing_ps['max_positions'] = max_positions
                update_kwargs['position_sizing'] = existing_ps

            # exit_conditions: read-modify-write
            if profit_target_pct is not None or stop_loss_pct is not None:
                existing_ec = strategy.get('exit_conditions') or {}
                if profit_target_pct is not None:
                    existing_ec['profit_target_pct'] = profit_target_pct
                if stop_loss_pct is not None:
                    existing_ec['stop_loss_pct'] = stop_loss_pct
                update_kwargs['exit_conditions'] = existing_ec

            # filters: fully replaces conditions.filters
            if filters is not None:
                existing_conditions = strategy.get('conditions') or {}
                existing_conditions['filters'] = filters
                update_kwargs['conditions'] = existing_conditions

            if not update_kwargs:
                return {"success": False, "error": "No fields to update were provided."}

            self.db.update_strategy(user_id, strategy_id, **update_kwargs)
            return {
                "success": True,
                "strategy_id": strategy_id,
                "message": f"Strategy updated successfully.",
                "updated_fields": list(update_kwargs.keys()),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_strategy_activity(
        self,
        strategy_id: int,
        user_id: int,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Get recent run history with trade counts and performance."""
        try:
            result = self._verify_strategy_ownership(strategy_id, user_id)
            if 'error' in result:
                return result

            runs = self.db.get_strategy_runs(strategy_id, limit)
            all_perf = self.db.get_strategy_performance(strategy_id)
            # Slice performance to match limit
            performance = all_perf[-limit:] if all_perf else []

            return {
                "success": True,
                "strategy_id": strategy_id,
                "runs": [dict(r) for r in runs],
                "performance": [dict(p) for p in performance],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_strategy_decisions(
        self,
        strategy_id: int,
        user_id: int,
        run_id: int = None,
        filter: str = 'all',
    ) -> Dict[str, Any]:
        """
        Get per-symbol scoring and reasoning for a strategy run.

        run_id defaults to the most recent run.
        filter: 'all' | 'trades' (BUY+SELL) | 'buys' | 'sells'
        """
        try:
            result = self._verify_strategy_ownership(strategy_id, user_id)
            if 'error' in result:
                return result

            # Resolve run_id
            if run_id is None:
                runs = self.db.get_strategy_runs(strategy_id, 1)
                if not runs:
                    return {"success": False, "error": "No runs found for this strategy."}
                run_id = runs[0]['id']

            decisions = self.db.get_run_decisions(run_id)

            # Apply filter
            filter_map = {
                'buys': lambda d: d.get('final_decision') == 'BUY',
                'sells': lambda d: d.get('final_decision') == 'SELL',
                'trades': lambda d: d.get('final_decision') in ('BUY', 'SELL'),
                'all': lambda d: True,
            }
            predicate = filter_map.get(filter, filter_map['all'])
            filtered = [d for d in decisions if predicate(d)]

            return {
                "success": True,
                "strategy_id": strategy_id,
                "run_id": run_id,
                "filter": filter,
                "decisions": filtered,
                "total": len(decisions),
                "shown": len(filtered),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
