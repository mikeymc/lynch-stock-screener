# ABOUTME: Strategy management tool executors for the Smart Chat Agent
# ABOUTME: Handles reading, updating, and inspecting investment strategies and their run history

import json
from typing import Dict, Any, Optional


class StrategyToolsMixin:
    """Mixin providing strategy management tool executor methods."""

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _get_portfolio_strategy(self, portfolio_id: int, user_id: int) -> Dict[str, Any]:
        """
        Fetch portfolio, verify ownership, and return the associated strategy dict.

        Returns the strategy dict on success, or {'error': ..., 'success': False} on failure.
        Callers check for 'error' key to short-circuit.
        """
        portfolio = self.db.get_portfolio(portfolio_id)
        if not portfolio:
            return {"success": False, "error": f"Portfolio {portfolio_id} not found."}
        if portfolio['user_id'] != user_id:
            return {"success": False, "error": "Portfolio not found or unauthorized access."}
        strategy_id = portfolio.get('strategy_id')
        if not strategy_id:
            return {"success": False, "error": f"Portfolio {portfolio_id} is not an autonomous portfolio."}
        strategy = self.db.get_strategy(strategy_id)
        if not strategy:
            return {"success": False, "error": f"Strategy not found for portfolio {portfolio_id}."}
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

    def _get_portfolio_strategy_config(self, portfolio_id: int, user_id: int) -> Dict[str, Any]:
        """Get full strategy configuration for an autonomous portfolio."""
        try:
            result = self._get_portfolio_strategy(portfolio_id, user_id)
            if 'error' in result:
                return result
            strategy = self._parse_json_fields(result)
            return {"success": True, "strategy": strategy}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _update_portfolio_strategy(
        self,
        portfolio_id: int,
        user_id: int,
        name: str = None,
        description: str = None,
        enabled: bool = None,
        consensus_mode: str = None,
        consensus_threshold: float = None,
        veto_score_threshold: float = None,
        position_sizing_method: str = None,
        max_position_pct: float = None,
        max_positions: int = None,
        profit_target_pct: float = None,
        stop_loss_pct: float = None,
        addition_lynch_min: float = None,
        addition_buffett_min: float = None,
        min_position_value: float = None,
        filters=None,
    ) -> Dict[str, Any]:
        """
        Modify any strategy field for an autonomous portfolio conversationally.

        position_sizing and exit_conditions use read-modify-write (preserves unmentioned fields).
        filters fully replaces conditions.filters.
        Direct fields (name, enabled, consensus_mode, etc.) map straight through.
        """
        try:
            result = self._get_portfolio_strategy(portfolio_id, user_id)
            if 'error' in result:
                return result

            strategy = self._parse_json_fields(result)
            strategy_id = strategy['id']
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
            if position_sizing_method is not None or max_position_pct is not None or max_positions is not None or min_position_value is not None:
                existing_ps = strategy.get('position_sizing') or {}
                if position_sizing_method is not None:
                    existing_ps['method'] = position_sizing_method
                if max_position_pct is not None:
                    existing_ps['max_position_pct'] = max_position_pct
                if max_positions is not None:
                    existing_ps['max_positions'] = max_positions
                if min_position_value is not None:
                    existing_ps['min_position_value'] = min_position_value
                update_kwargs['position_sizing'] = existing_ps

            # exit_conditions: read-modify-write
            if profit_target_pct is not None or stop_loss_pct is not None:
                existing_ec = strategy.get('exit_conditions') or {}
                if profit_target_pct is not None:
                    existing_ec['profit_target_pct'] = profit_target_pct
                if stop_loss_pct is not None:
                    existing_ec['stop_loss_pct'] = stop_loss_pct
                update_kwargs['exit_conditions'] = existing_ec

            if filters is not None or addition_lynch_min is not None or addition_buffett_min is not None or veto_score_threshold is not None:
                existing_conditions = strategy.get('conditions') or {}
                if filters is not None:
                    existing_conditions['filters'] = filters
                
                if veto_score_threshold is not None:
                    existing_conditions['veto_score_threshold'] = veto_score_threshold

                if addition_lynch_min is not None or addition_buffett_min is not None:
                    addition_reqs = existing_conditions.get('addition_scoring_requirements') or []
                    
                    if addition_lynch_min is not None:
                        lynch_idx = next((i for i, r in enumerate(addition_reqs) if r['character'] == 'lynch'), -1)
                        if lynch_idx >= 0:
                            addition_reqs[lynch_idx]['min_score'] = addition_lynch_min
                        else:
                            addition_reqs.append({"character": "lynch", "min_score": addition_lynch_min})
                            
                    if addition_buffett_min is not None:
                        buffett_idx = next((i for i, r in enumerate(addition_reqs) if r['character'] == 'buffett'), -1)
                        if buffett_idx >= 0:
                            addition_reqs[buffett_idx]['min_score'] = addition_buffett_min
                        else:
                            addition_reqs.append({"character": "buffett", "min_score": addition_buffett_min})
                    
                    existing_conditions['addition_scoring_requirements'] = addition_reqs
                
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

    def _get_portfolio_strategy_activity(
        self,
        portfolio_id: int,
        user_id: int,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Get recent run history with trade counts and performance for an autonomous portfolio."""
        try:
            result = self._get_portfolio_strategy(portfolio_id, user_id)
            if 'error' in result:
                return result

            strategy_id = result['id']
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

    def _get_portfolio_strategy_decisions(
        self,
        portfolio_id: int,
        user_id: int,
        run_id: int = None,
        filter: str = 'all',
    ) -> Dict[str, Any]:
        """
        Get per-symbol scoring and reasoning for an autonomous portfolio's strategy run.

        run_id defaults to the most recent run.
        filter: 'all' | 'trades' (BUY+SELL) | 'buys' | 'sells'
        """
        try:
            result = self._get_portfolio_strategy(portfolio_id, user_id)
            if 'error' in result:
                return result

            strategy_id = result['id']

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
