# ABOUTME: Alert evaluation job mixin for the background worker
# ABOUTME: Handles checking alerts, LLM-based evaluation, and automated trade execution

import json
import logging
import os
from datetime import datetime, date
from typing import Dict, Any

import portfolio_service  # Import portfolio service for automated trading

logger = logging.getLogger(__name__)


class AlertJobsMixin:
    """Mixin for check_alerts job and alert evaluation helpers"""

    def _run_check_alerts(self, job_id: int, params: Dict[str, Any]):
        """Check all active alerts and trigger if conditions are met using LLM evaluation."""
        logger.info(f"Running check_alerts job {job_id}")

        try:
            active_alerts = self.db.get_all_active_alerts()
            logger.info(f"Checking {len(active_alerts)} active alerts")

            triggered_count = 0

            for alert in active_alerts:
                try:
                    is_triggered = False
                    trigger_message = ""

                    symbol = alert['symbol']
                    condition_description = alert.get('condition_description')
                    condition_type = alert['condition_type']
                    condition_params = alert['condition_params']

                    # ALERT LOGIC REFINEMENT:
                    # If this is an automated trading alert, we MUST wait for market open.
                    # If we evaluate it now and it triggers, the trade will fail (or be skipped),
                    # and the alert will be consumed/marked 'triggered'.
                    # By skipping evaluation here, we effectively "hold off" until market open.
                    if alert.get('action_type') and not portfolio_service.is_market_open():
                        # Optional: Log periodically or just debug to avoid spamming logs every 5s
                        # logger.debug(f"Skipping trading alert {alert['id']} - Market Closed")
                        continue

                    # Fetch latest stock data
                    metrics = self.db.get_stock_metrics(symbol)
                    if not metrics:
                        logger.warning(f"No metrics found for {symbol}, skipping alert {alert['id']}")
                        continue

                    # Use LLM-based evaluation if condition_description is present
                    if condition_description:
                        is_triggered, trigger_message = self._evaluate_alert_with_llm(
                            symbol, condition_description, metrics
                        )
                    else:
                        # Fall back to legacy hardcoded logic for backward compatibility
                        is_triggered, trigger_message = self._evaluate_alert_legacy(
                            symbol, condition_type, condition_params, metrics
                        )

                    if is_triggered:
                        logger.info(f"Alert {alert['id']} triggered: {trigger_message}")

                        # Execute automated trade if configured
                        action_type = alert.get('action_type')
                        trade_result_msg = ""

                        if action_type and alert.get('portfolio_id'):
                            try:
                                logger.info(f"Executing automated trade for alert {alert['id']}")
                                action_payload = alert.get('action_payload') or {}
                                portfolio_id = alert['portfolio_id']
                                quantity = action_payload.get('quantity', 0)
                                action_note = alert.get('action_note') or "Automated trade via Alert"

                                # Map action_type to transaction_type
                                transaction_type = None
                                if action_type == 'market_buy':
                                    transaction_type = 'BUY'
                                elif action_type == 'market_sell':
                                    transaction_type = 'SELL'

                                if transaction_type and quantity > 0:
                                    trade_result = portfolio_service.execute_trade(
                                        db=self.db,
                                        portfolio_id=portfolio_id,
                                        symbol=symbol,
                                        transaction_type=transaction_type,
                                        quantity=quantity,
                                        note=f"{action_note} (Triggered by Alert {alert['id']})"
                                    )

                                    if trade_result['success']:
                                        trade_price = trade_result['price_per_share']
                                        transaction_id = trade_result.get('transaction_id')
                                        trade_result_msg = f" [Auto-Trade: Executed {transaction_type} {quantity} shares @ ${trade_price:.2f}]"
                                        
                                        # Link trade back to Strategy Decision if applicable
                                        decision_id = action_payload.get('decision_id')
                                        if decision_id:
                                            try:
                                                self.db.update_strategy_decision(
                                                    decision_id=decision_id,
                                                    transaction_id=transaction_id,
                                                    trade_price=trade_price,
                                                    position_value=quantity * trade_price,
                                                    shares_traded=quantity,
                                                    decision_reasoning=f"{alert.get('message', '')} [Executed via Alert {alert['id']}]"
                                                )
                                                logger.info(f"Linked Alert Trade {transaction_id} to Decision {decision_id}")
                                            except Exception as e:
                                                logger.error(f"Failed to link trade to decision {decision_id}: {e}")
                                    else:
                                        trade_result_msg = f" [Auto-Trade Failed: {trade_result.get('error')}]"
                                else:
                                    trade_result_msg = " [Auto-Trade Skipped: Invalid configuration]"

                            except Exception as e:
                                logger.error(f"Failed to execute automated trade for alert {alert['id']}: {e}")
                                trade_result_msg = f" [Auto-Trade Error: {str(e)}]"

                        self.db.update_alert_status(
                            alert['id'],
                            status='triggered',
                            triggered_at=datetime.now(),
                            message=trigger_message + trade_result_msg
                        )
                        triggered_count += 1
                    else:
                        # Even if not triggered, update last_checked timestamp
                        # We pass the existing status ('active') to keep it unchanged
                        self.db.update_alert_status(
                            alert['id'],
                            status=alert['status']
                        )

                except Exception as e:
                    logger.error(f"Error checking alert {alert['id']}: {e}")
                    continue

            self.db.complete_job(job_id, result={'triggered_count': triggered_count})

        except Exception as e:
            logger.error(f"Check alerts job failed: {e}")
            self.db.fail_job(job_id, str(e))

    def _evaluate_alert_with_llm(self, symbol: str, condition_description: str,
                                  metrics: Dict[str, Any]) -> tuple[bool, str]:
        """
        Evaluate an alert condition using LLM.

        Args:
            symbol: Stock symbol
            condition_description: Natural language condition description
            metrics: Current stock metrics

        Returns:
            Tuple of (is_triggered: bool, message: str)
        """
        try:
            # Fetch context for the alert
            context = self._get_alert_context(symbol)

            # Construct prompt
            prompt = self._construct_alert_prompt(symbol, condition_description, metrics, context)

            logger.debug(f"[LLM Debug] Evaluating {symbol} alert. Condition: {condition_description}")
            # logger.debug(f"[LLM Debug] Prompt: {prompt}")

            # Generate analysis using Gemini
            model_name = 'gemini-2.0-flash'
            
            try:
                # Configure the client
                # We need to use the genai library directly as in other parts of the codebase
                from google import genai
                
                if not os.getenv('GEMINI_API_KEY'):
                    logger.error("GEMINI_API_KEY not found")
                    return False, "GEMINI_API_KEY not found"
                    
                genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
                model = genai.GenerativeModel(model_name)
                
                response = model.generate_content(prompt)
                
                if not response or not response.text:
                    logger.error(f"Empty response from LLM for alert {symbol}")
                    return False, "Empty response from LLM"

                # Parse the response (extract JSON)
                response_text = response.text
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}')
                
                if start_idx != -1 and end_idx != -1:
                    json_str = response_text[start_idx:end_idx+1]
                    result = json.loads(json_str)
                    logger.debug(f"[LLM Debug] Result: {result}")
                    return result.get('triggered', False), result.get('reason', '')
                else:
                    logger.error(f"Could not find JSON in LLM response: {response_text}")
                    return False, "Invalid LLM response format"

            except Exception as e:
                logger.error(f"Error calling Gemini: {e}")
                return False, f"LLM Error: {str(e)}"

        except Exception as e:
            logger.error(f"Error evaluating alert with LLM: {e}")
            return False, f"Error: {str(e)}"

    def _get_alert_context(self, symbol: str) -> Dict[str, Any]:
        """Fetch additional context for alert evaluation (events, trades, historical data)."""
        context = {}
        try:
            # Get recent insider trades (last 30 days effectively covered by limit=10 most recent)
            trades = self.db.get_insider_trades(symbol, limit=10)
            if trades:
                context['recent_insider_trades'] = trades

            # Get recent material events (last 10 events)
            events = self.db.get_material_events(symbol, limit=10)
            if events:
                # Simplify events to reduce token usage
                simple_events = []
                for e in events:
                    simple_events.append({
                        'date': e.get('filing_date') or e.get('datetime'),
                        'headline': e.get('headline'),
                        'description': e.get('description'),
                        'event_type': e.get('event_type')
                    })
                context['recent_material_events'] = simple_events

            # Get earnings history for computing CAGR, ROE, PEG
            earnings = self.db.get_earnings_history(symbol, 'annual')
            if earnings:
                # Keep last 6 years to enable 5-year growth calculations
                context['earnings_history'] = earnings[:6]

            # Get 52-week price data for P/E range calculations
            last_year = datetime.now().year - 1
            weekly = self.db.get_weekly_prices(symbol, start_year=last_year)
            if weekly and weekly.get('prices'):
                prices = weekly['prices'][-52:]  # Last 52 weeks
                if prices:
                    context['price_52w'] = {
                        'high': max(prices),
                        'low': min(prices),
                        'mean': sum(prices) / len(prices)
                    }

        except Exception as e:
            logger.warning(f"Error fetching alert context for {symbol}: {e}")

        return context

    def _construct_alert_prompt(self, symbol: str, condition: str, metrics: Dict[str, Any], context: Dict[str, Any] = None) -> str:
        """Construct the prompt for LLM alert evaluation."""

        # Helper for JSON serialization
        def json_serial(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            return str(obj)

        prompt = f"""You are a financial alert system. Evaluate if the following stock alert condition is met.

Stock: {symbol}
Condition: "{condition}"

Current Metrics:
{json.dumps(metrics, indent=2, default=json_serial)}
"""

        if context:
            prompt += f"""
Context (historical data, events, trades):
{json.dumps(context, indent=2, default=json_serial)}

Derived Metrics (compute from context if needed):
- CAGR: Use earnings_history to compute 5-year growth. Formula: ((end/start)^(1/years) - 1) * 100
- ROE: net_income / shareholder_equity * 100 (from latest year in earnings_history)
- PEG: pe_ratio / earnings_growth_rate
- 52-week P/E range: Use price_52w (high/low/mean) with TTM EPS derived from current price/pe_ratio
"""

        prompt += """
Return JSON only:
{
    "triggered": true/false,
    "reason": "explanation of why it triggered or why not"
}
"""
        return prompt

    def _format_metrics_for_llm(self, symbol: str, metrics: Dict[str, Any]) -> str:
        """Format stock metrics into a readable string for LLM context."""
        key_metrics = [
            ('Price', metrics.get('price')),
            ('P/E Ratio', metrics.get('pe_ratio')),
            ('PEG Ratio', metrics.get('peg_ratio')),
            ('Market Cap', metrics.get('market_cap')),
            ('Revenue', metrics.get('revenue')),
            ('5-Year Earnings Growth (CAGR)', metrics.get('earnings_cagr')),
            ('5-Year Revenue Growth (CAGR)', metrics.get('revenue_cagr')),
            ('ROE', metrics.get('roe')),
            ('Gross Margin', metrics.get('gross_margin')),
            ('Debt/Equity', metrics.get('debt_to_equity')),
            ('Institutional Ownership', metrics.get('institutional_ownership')),
            ('Dividend Yield', metrics.get('dividend_yield')),
            ('Beta', metrics.get('beta')),
        ]

        formatted = []
        for name, value in key_metrics:
            if value is not None:
                if name == 'Market Cap':
                    formatted.append(f"  - {name}: ${value:,.0f}")
                elif name == 'Revenue':
                    formatted.append(f"  - {name}: ${value:,.0f}")
                elif name in ['Gross Margin', '5-Year Earnings Growth (CAGR)', '5-Year Revenue Growth (CAGR)', 'ROE']:
                    # These are already stored as percentages (e.g., 51.2), not decimals (0.512)
                    formatted.append(f"  - {name}: {value:.2f}%")
                elif name in ['Institutional Ownership', 'Dividend Yield']:
                    # These are stored as decimals (0.512), so use .2% to multiply by 100
                    formatted.append(f"  - {name}: {value:.2%}" if isinstance(value, (int, float)) else f"  - {name}: {value}")
                elif isinstance(value, float):
                    formatted.append(f"  - {name}: ${value:.2f}" if name == 'Price' else f"  - {name}: {value:.2f}")
                else:
                    formatted.append(f"  - {name}: {value}")

        return '\n'.join(formatted) if formatted else "  No metrics available"

    def _evaluate_alert_legacy(self, symbol: str, condition_type: str,
                                condition_params: Dict[str, Any],
                                metrics: Dict[str, Any]) -> tuple[bool, str]:
        """
        Legacy hardcoded alert evaluation for backward compatibility.

        Supports 'price' and 'pe_ratio' condition types.
        """
        current_price = metrics.get('price')
        current_pe = metrics.get('pe_ratio')

        if condition_type == 'price':
            threshold = condition_params.get('threshold')
            operator = condition_params.get('operator')

            if operator == 'above' and current_price and current_price >= threshold:
                return True, f"{symbol} price is ${current_price}, above target ${threshold}"
            elif operator == 'below' and current_price and current_price <= threshold:
                return True, f"{symbol} price is ${current_price}, below target ${threshold}"

        elif condition_type == 'pe_ratio':
            threshold = condition_params.get('threshold')
            operator = condition_params.get('operator')

            if operator == 'above' and current_pe and current_pe >= threshold:
                return True, f"{symbol} P/E is {current_pe}, above target {threshold}"
            elif operator == 'below' and current_pe and current_pe <= threshold:
                return True, f"{symbol} P/E is {current_pe}, below target {threshold}"

        return False, ""
