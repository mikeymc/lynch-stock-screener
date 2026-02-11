# ABOUTME: Portfolio management tool executors for the Smart Chat Agent
# ABOUTME: Handles paper trading operations including portfolio CRUD, buy/sell, and strategies

from typing import Dict, Any, List
import portfolio_service


class PortfolioToolsMixin:
    """Mixin providing portfolio management tool executor methods."""

    # =========================================================================
    # Portfolio Management Executor Methods
    # =========================================================================

    def _create_portfolio(self, name: str, user_id: int, initial_cash: float = 100000.0) -> Dict[str, Any]:
        """Create a new paper trading portfolio."""
        try:
            portfolio_id = self.db.create_portfolio(user_id=user_id, name=name, initial_cash=initial_cash)
            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "name": name,
                "initial_cash": initial_cash,
                "message": f"Portfolio '{name}' created successfully with ${initial_cash:,.2f}."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_my_portfolios(self, user_id: int) -> Dict[str, Any]:
        """List all portfolios for a user."""
        try:
            portfolios = self.db.get_user_portfolios(user_id)
            summaries = []
            for p in portfolios:
                summary = self.db.get_portfolio_summary(p['id'], use_live_prices=False) # fast summary
                summaries.append(summary)

            return {
                "success": True,
                "portfolios": summaries
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_portfolio_status(self, portfolio_id: int, user_id: int) -> Dict[str, Any]:
        """Get detailed status of a specific portfolio."""
        try:
            # Verify ownership
            portfolio = self.db.get_portfolio(portfolio_id)
            if not portfolio or portfolio['user_id'] != user_id:
                return {"success": False, "error": "Portfolio not found or unauthorized access."}

            summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=True)
            return {
                "success": True,
                "status": summary
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _buy_stock(self, portfolio_id: int, ticker: str, quantity: int, user_id: int, note: str = None) -> Dict[str, Any]:
        """Buy stock in a portfolio."""
        try:
            # Verify ownership
            portfolio = self.db.get_portfolio(portfolio_id)
            if not portfolio or portfolio['user_id'] != user_id:
                return {"success": False, "error": "Portfolio not found or unauthorized access."}

            result = portfolio_service.execute_trade(
                db=self.db,
                portfolio_id=portfolio_id,
                symbol=ticker.upper(),
                transaction_type='BUY',
                quantity=quantity,
                note=note
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _sell_stock(self, portfolio_id: int, ticker: str, quantity: int, user_id: int, note: str = None) -> Dict[str, Any]:
        """Sell stock from a portfolio."""
        try:
            # Verify ownership
            portfolio = self.db.get_portfolio(portfolio_id)
            if not portfolio or portfolio['user_id'] != user_id:
                return {"success": False, "error": "Portfolio not found or unauthorized access."}

            result = portfolio_service.execute_trade(
                db=self.db,
                portfolio_id=portfolio_id,
                symbol=ticker.upper(),
                transaction_type='SELL',
                quantity=quantity,
                note=note
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_strategy_templates(self) -> Dict[str, Any]:
        """Return available strategy templates."""
        from strategy_templates import FILTER_TEMPLATES
        return {
            "success": True,
            "templates": [
                {
                    "id": k,
                    "name": v["name"],
                    "description": v["description"],
                    "use_case": v["use_case"],
                    "filter_count": len(v["filters"])
                }
                for k, v in FILTER_TEMPLATES.items()
            ]
        }

    def _create_strategy(
        self,
        name: str,
        user_id: int,
        template_id: str = None,
        filters: List[Dict] = None,
        portfolio_id: str = "new",
        portfolio_name: str = None,
        initial_cash: float = 100000.0,
        enable_now: bool = False,
        consensus_mode: str = None,
        consensus_threshold: float = None,
        position_sizing_method: str = None,
        max_position_pct: float = None,
        profit_target_pct: float = None,
        stop_loss_pct: float = None
    ) -> Dict[str, Any]:
        """Create a new investment strategy conversationally."""
        from strategy_templates import FILTER_TEMPLATES, STRATEGY_DEFAULTS

        # Load template if specified
        if template_id:
            if template_id not in FILTER_TEMPLATES:
                return {"success": False, "error": f"Unknown template: {template_id}"}
            template = FILTER_TEMPLATES[template_id]
            final_filters = template["filters"]
            if filters:  # Allow override
                final_filters = filters
        elif filters:
            final_filters = filters
        else:
            return {"success": False, "error": "Must provide either template_id or filters"}

        # Handle portfolio creation
        actual_portfolio_id = portfolio_id
        if portfolio_id == "new":
            pf_name = portfolio_name or f"{name} Portfolio"
            actual_portfolio_id = self.db.create_portfolio(user_id, pf_name, initial_cash)

        # Build conditions
        conditions = {
            "filters": final_filters,
            "require_thesis": True,
            "scoring_requirements": [
                {"character": "lynch", "min_score": 60},
                {"character": "buffett", "min_score": 60}
            ],
            "thesis_verdict_required": ["BUY"]
        }

        # Build position sizing
        position_sizing = {
            "method": position_sizing_method or STRATEGY_DEFAULTS["position_sizing"]["method"],
            "max_position_pct": max_position_pct or STRATEGY_DEFAULTS["position_sizing"]["max_position_pct"]
        }

        # Build exit conditions
        exit_conditions = {}
        if profit_target_pct is not None:
            exit_conditions["profit_target_pct"] = profit_target_pct
        if stop_loss_pct is not None:
            exit_conditions["stop_loss_pct"] = stop_loss_pct

        # Create strategy
        strategy_id = self.db.create_strategy(
            user_id=user_id,
            portfolio_id=actual_portfolio_id,
            name=name,
            description=f"Created via chat agent",
            conditions=conditions,
            consensus_mode=consensus_mode or STRATEGY_DEFAULTS["consensus_mode"],
            consensus_threshold=consensus_threshold or STRATEGY_DEFAULTS["consensus_threshold"],
            position_sizing=position_sizing,
            exit_conditions=exit_conditions,
            schedule_cron=STRATEGY_DEFAULTS["schedule_cron"]
        )

        # Enable if requested
        if enable_now:
            self.db.update_strategy(user_id, strategy_id, enabled=True)

        return {
            "success": True,
            "strategy_id": strategy_id,
            "portfolio_id": actual_portfolio_id,
            "enabled": enable_now,
            "message": f"Strategy '{name}' created successfully" + (" and enabled" if enable_now else ""),
            "strategy_url": f"/strategies/{strategy_id}"
        }
