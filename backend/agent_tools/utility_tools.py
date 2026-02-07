# ABOUTME: Utility tool executors for the Smart Chat Agent
# ABOUTME: Handles alerts management, FRED economic data, and analyst sentiment

from typing import Dict, Any
from fred_service import get_fred_service, SUPPORTED_SERIES


class UtilityToolsMixin:
    """Mixin providing utility tool executor methods."""

    def _manage_alerts(self, action: str, ticker: str = None, condition_description: str = None,
                      condition_type: str = None, threshold: float = None, operator: str = None,
                      alert_id: int = None, user_id: int = None,
                      action_type: str = None, action_quantity: int = None,
                      portfolio_name: str = None, action_note: str = None) -> Dict[str, Any]:
        """
        Manage user alerts: create, list, or delete.

        Supports two modes:
        1. Flexible natural language conditions (recommended): Use condition_description parameter
        2. Legacy hardcoded conditions: Use condition_type, threshold, operator parameters

        Args:
            action: Action to perform ('create', 'list', or 'delete')
            ticker: Stock symbol (for create)
            condition_description: Natural language description of alert condition (e.g., "notify me when AAPL drops below $145")
            condition_type: Legacy condition type ('price', 'pe_ratio')
            threshold: Legacy threshold value
            operator: Legacy operator ('above' or 'below')
            alert_id: Alert ID (for delete)
            user_id: User ID
        """
        if not user_id:
            return {"error": "Authentication required. Cannot manage alerts without a valid user session."}

        if action == "create":
            if not ticker:
                return {"error": "Missing required parameter 'ticker' for creating an alert."}

            # Helper: Resolve portfolio if trading action requested
            portfolio_id = None
            action_payload = None

            if action_type:
                if not action_quantity or action_quantity <= 0:
                    return {"error": "Trading action requires a positive 'action_quantity'."}
                if not portfolio_name:
                    return {"error": "Trading action requires 'portfolio_name'."}

                portfolio = self.db.get_portfolio_by_name(user_id, portfolio_name)
                if not portfolio:
                    return {"error": f"Portfolio '{portfolio_name}' not found."}

                portfolio_id = portfolio['id']
                action_payload = {"quantity": action_quantity}

            ticker = ticker.upper()

            # Prefer condition_description (flexible LLM-based alerts)
            if condition_description:
                try:
                    # Create flexible LLM-based alert
                    alert_id = self.db.create_alert(
                        user_id=user_id,
                        symbol=ticker,
                        condition_type='custom',  # Mark as LLM-evaluated
                        condition_params={},  # Empty params for custom alerts
                        condition_description=condition_description,
                        action_type=action_type,
                        action_payload=action_payload,
                        portfolio_id=portfolio_id,
                        action_note=action_note
                    )
                    return {
                        "message": f"Successfully created alert for {ticker}.",
                        "alert_details": {
                            "id": alert_id,
                            "ticker": ticker,
                            "condition": condition_description
                        }
                    }
                except Exception as e:
                    return {"error": f"Failed to create alert: {str(e)}"}

            # Fallback to legacy hardcoded alerts
            elif condition_type and threshold is not None and operator:
                condition_params = {
                    "threshold": threshold,
                    "operator": operator
                }

                try:
                    alert_id = self.db.create_alert(
                        user_id=user_id,
                        symbol=ticker,
                        condition_type=condition_type,
                        condition_params=condition_params
                    )
                    return {
                        "message": f"Successfully created alert for {ticker}.",
                        "alert_details": {
                            "id": alert_id,
                            "ticker": ticker,
                            "condition": f"{condition_type} {operator} {threshold}"
                        }
                    }
                except Exception as e:
                    return {"error": f"Failed to create alert: {str(e)}"}
            else:
                return {"error": "Must provide either 'condition_description' for flexible alerts or all of (condition_type, threshold, operator) for legacy alerts."}

        elif action == "list":
            try:
                alerts = self.db.get_alerts(user_id)
                if not alerts:
                    return {"message": "You have no active alerts."}

                # Format for display
                formatted_alerts = []
                for a in alerts:
                    # Prefer condition_description if available
                    if a.get('condition_description'):
                        condition_str = a['condition_description']
                    else:
                        # Fallback to legacy format
                        params = a['condition_params']
                        condition_str = f"{a['condition_type']} {params.get('operator')} {params.get('threshold')}"

                    formatted_alerts.append({
                        "id": a['id'],
                        "symbol": a['symbol'],
                        "condition": condition_str,
                        "status": a['status'],
                        "created_at": a['created_at'].strftime('%Y-%m-%d')
                    })

                return {"alerts": formatted_alerts}
            except Exception as e:
                return {"error": f"Failed to list alerts: {str(e)}"}

        elif action == "delete":
            if not alert_id:
                return {"error": "Missing required parameter 'alert_id' for delete action."}

            try:
                success = self.db.delete_alert(alert_id, user_id)
                if success:
                    return {"message": f"Successfully deleted alert {alert_id}."}
                else:
                    return {"error": f"Alert {alert_id} not found or could not be deleted."}
            except Exception as e:
                return {"error": f"Failed to delete alert: {str(e)}"}

        else:
            return {"error": f"Unknown action: {action}"}

    # =========================================================================
    # FRED Macroeconomic Data Tools
    # =========================================================================

    def _get_fred_series(self, series_id: str, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """Get historical observations for a FRED economic data series."""
        fred = get_fred_service()
        if not fred.is_available():
            return {"error": "FRED API key not configured"}

        result = fred.get_series(series_id, start_date=start_date, end_date=end_date)

        if 'error' in result:
            return result

        # Limit observations for chat context (last 24 data points)
        observations = result.get('observations', [])
        if len(observations) > 24:
            observations = observations[-24:]

        return {
            "series_id": result['series_id'],
            "name": result['name'],
            "frequency": result['frequency'],
            "units": result['units'],
            "description": result['description'],
            "latest_value": result['latest']['value'] if result['latest'] else None,
            "latest_date": result['latest']['date'] if result['latest'] else None,
            "observations": observations,
            "observation_count": len(observations),
            "total_available": result['observation_count']
        }

    def _get_economic_indicators(self) -> Dict[str, Any]:
        """Get current values of key macroeconomic indicators."""
        fred = get_fred_service()
        if not fred.is_available():
            return {"error": "FRED API key not configured"}

        result = fred.get_economic_summary()

        if 'error' in result:
            return result

        # Format for easy reading by the LLM
        indicators = result.get('indicators', {})
        formatted = {}
        for series_id, data in indicators.items():
            formatted[data['name']] = {
                "value": data['value'],
                "units": data['units'],
                "date": data['date'],
                "change": data.get('change'),
                "series_id": series_id
            }

        return {
            "indicators": formatted,
            "fetched_at": result.get('fetched_at'),
            "available_series": list(SUPPORTED_SERIES.keys())
        }

    def _get_analyst_sentiment(self, ticker: str) -> Dict[str, Any]:
        """Get comprehensive analyst sentiment data including trends, revisions, and recommendation history."""
        ticker = ticker.upper()

        # Get all sentiment data from database
        eps_trends = self.db.get_eps_trends(ticker)
        eps_revisions = self.db.get_eps_revisions(ticker)
        recommendations = self.db.get_analyst_recommendations(ticker)
        growth = self.db.get_growth_estimates(ticker)
        metrics = self.db.get_stock_metrics(ticker)

        if not eps_trends and not eps_revisions and not recommendations and not growth:
            return {"error": f"No analyst sentiment data found for {ticker}"}

        # Calculate trend direction for key periods
        trend_summary = {}
        for period in ['0q', '+1q', '0y', '+1y']:
            if period in eps_trends:
                trend = eps_trends[period]
                current = trend.get('current')
                ago_30 = trend.get('30_days_ago')
                if current and ago_30:
                    change_pct = round(((current - ago_30) / abs(ago_30)) * 100, 1)
                    trend_summary[period] = {
                        "current_estimate": round(current, 2),
                        "30_days_ago": round(ago_30, 2),
                        "change_pct": change_pct,
                        "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
                    }

        # Calculate revision momentum
        revision_summary = {}
        for period in ['0q', '+1q', '0y', '+1y']:
            if period in eps_revisions:
                rev = eps_revisions[period]
                up = rev.get('up_30d') or 0
                down = rev.get('down_30d') or 0
                net = up - down
                if up > 0 or down > 0:
                    revision_summary[period] = {
                        "up_revisions": up,
                        "down_revisions": down,
                        "net": net,
                        "sentiment": "bullish" if net > 0 else "bearish" if net < 0 else "neutral"
                    }

        # Format recommendation history (last 3 months)
        rec_history = []
        for rec in recommendations[:3]:
            total = (rec.get('strong_buy') or 0) + (rec.get('buy') or 0) + (rec.get('hold') or 0) + (rec.get('sell') or 0) + (rec.get('strong_sell') or 0)
            if total > 0:
                bullish = (rec.get('strong_buy') or 0) + (rec.get('buy') or 0)
                bearish = (rec.get('sell') or 0) + (rec.get('strong_sell') or 0)
                rec_history.append({
                    "period": rec.get('period'),
                    "strong_buy": rec.get('strong_buy'),
                    "buy": rec.get('buy'),
                    "hold": rec.get('hold'),
                    "sell": rec.get('sell'),
                    "strong_sell": rec.get('strong_sell'),
                    "bullish_pct": round((bullish / total) * 100, 1),
                    "bearish_pct": round((bearish / total) * 100, 1)
                })

        return {
            "ticker": ticker,
            "recommendation_key": metrics.get('recommendation_key') if metrics else None,
            "analyst_count": metrics.get('analyst_count') if metrics else None,
            "eps_trends": trend_summary,
            "revision_momentum": revision_summary,
            "recommendation_history": rec_history,
            "growth_estimates": growth
        }
