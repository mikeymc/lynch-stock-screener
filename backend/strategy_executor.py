# ABOUTME: Orchestrates autonomous investment strategy execution
# ABOUTME: Coordinates screening, scoring, thesis generation, consensus, and trade execution

import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from google import genai

logger = logging.getLogger(__name__)


@dataclass
class ConsensusResult:
    """Result of consensus evaluation between characters."""
    verdict: str  # BUY, WATCH, AVOID, VETO
    score: float
    reasoning: str
    lynch_contributed: bool
    buffett_contributed: bool


@dataclass
class PositionSize:
    """Calculated position size for a trade."""
    shares: int
    estimated_value: float
    position_pct: float
    reasoning: str


@dataclass
class ExitSignal:
    """Signal to exit a position."""
    symbol: str
    quantity: int
    reason: str
    current_value: float
    gain_pct: float


class ConditionEvaluator:
    """Parses and evaluates strategy conditions against stock data."""

    def __init__(self, db):
        self.db = db

    def evaluate_universe(self, conditions: Dict[str, Any]) -> List[str]:
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


class ConsensusEngine:
    """Implements consensus modes for multi-character investment decisions."""

    def evaluate(
        self,
        lynch_result: Dict[str, Any],
        buffett_result: Dict[str, Any],
        mode: str,
        config: Dict[str, Any]
    ) -> ConsensusResult:
        """Evaluate consensus between Lynch and Buffett.

        Args:
            lynch_result: {score: float, status: str}
            buffett_result: {score: float, status: str}
            mode: 'both_agree', 'weighted_confidence', or 'veto_power'
            config: Mode-specific configuration

        Returns:
            ConsensusResult with verdict, score, and reasoning
        """
        if mode == 'both_agree':
            return self.both_agree(lynch_result, buffett_result, config)
        elif mode == 'weighted_confidence':
            return self.weighted_confidence(lynch_result, buffett_result, config)
        elif mode == 'veto_power':
            return self.veto_power(lynch_result, buffett_result, config)
        else:
            raise ValueError(f"Unknown consensus mode: {mode}")

    def both_agree(
        self,
        lynch: Dict[str, Any],
        buffett: Dict[str, Any],
        config: Dict[str, Any]
    ) -> ConsensusResult:
        """Both characters must recommend BUY with score >= threshold."""
        min_score = config.get('min_score', 70)
        buy_statuses = config.get('buy_statuses', ['STRONG_BUY', 'BUY'])

        lynch_approves = (
            lynch.get('score', 0) >= min_score and
            lynch.get('status', '') in buy_statuses
        )
        buffett_approves = (
            buffett.get('score', 0) >= min_score and
            buffett.get('status', '') in buy_statuses
        )

        if lynch_approves and buffett_approves:
            avg_score = (lynch['score'] + buffett['score']) / 2
            return ConsensusResult(
                verdict='BUY',
                score=avg_score,
                reasoning=f"Both agree: Lynch {lynch['score']:.0f} ({lynch['status']}), "
                         f"Buffett {buffett['score']:.0f} ({buffett['status']})",
                lynch_contributed=True,
                buffett_contributed=True
            )
        else:
            reasons = []
            if not lynch_approves:
                reasons.append(f"Lynch: {lynch.get('score', 0):.0f} ({lynch.get('status', 'N/A')})")
            if not buffett_approves:
                reasons.append(f"Buffett: {buffett.get('score', 0):.0f} ({buffett.get('status', 'N/A')})")

            return ConsensusResult(
                verdict='AVOID',
                score=min(lynch.get('score', 0), buffett.get('score', 0)),
                reasoning=f"Disagreement: {'; '.join(reasons)}",
                lynch_contributed=lynch_approves,
                buffett_contributed=buffett_approves
            )

    def weighted_confidence(
        self,
        lynch: Dict[str, Any],
        buffett: Dict[str, Any],
        config: Dict[str, Any]
    ) -> ConsensusResult:
        """Combined weighted score must exceed threshold."""
        lynch_weight = config.get('lynch_weight', 0.5)
        buffett_weight = config.get('buffett_weight', 0.5)
        threshold = config.get('threshold', 70)

        # Normalize weights
        total_weight = lynch_weight + buffett_weight
        lynch_weight /= total_weight
        buffett_weight /= total_weight

        lynch_score = lynch.get('score', 0)
        buffett_score = buffett.get('score', 0)
        combined_score = (lynch_score * lynch_weight) + (buffett_score * buffett_weight)

        if combined_score >= 80:
            verdict = 'BUY'
        elif combined_score >= threshold:
            verdict = 'WATCH'
        else:
            verdict = 'AVOID'

        return ConsensusResult(
            verdict=verdict,
            score=combined_score,
            reasoning=f"Weighted: ({lynch_score:.0f} * {lynch_weight:.0%}) + "
                     f"({buffett_score:.0f} * {buffett_weight:.0%}) = {combined_score:.1f}",
            lynch_contributed=True,
            buffett_contributed=True
        )

    def veto_power(
        self,
        lynch: Dict[str, Any],
        buffett: Dict[str, Any],
        config: Dict[str, Any]
    ) -> ConsensusResult:
        """Either character can veto if strong negative conviction."""
        veto_statuses = config.get('veto_statuses', ['AVOID', 'CAUTION'])
        veto_threshold = config.get('veto_score_threshold', 30)

        lynch_score = lynch.get('score', 0)
        buffett_score = buffett.get('score', 0)
        lynch_status = lynch.get('status', '')
        buffett_status = buffett.get('status', '')

        lynch_vetos = lynch_status in veto_statuses or lynch_score < veto_threshold
        buffett_vetos = buffett_status in veto_statuses or buffett_score < veto_threshold

        if lynch_vetos or buffett_vetos:
            vetoers = []
            if lynch_vetos:
                vetoers.append(f"Lynch ({lynch_score:.0f}, {lynch_status})")
            if buffett_vetos:
                vetoers.append(f"Buffett ({buffett_score:.0f}, {buffett_status})")

            return ConsensusResult(
                verdict='VETO',
                score=min(lynch_score, buffett_score),
                reasoning=f"VETO by {' and '.join(vetoers)}",
                lynch_contributed=not lynch_vetos,
                buffett_contributed=not buffett_vetos
            )

        # No veto - use weighted average
        avg_score = (lynch_score + buffett_score) / 2
        verdict = 'BUY' if avg_score >= 70 else 'WATCH'

        return ConsensusResult(
            verdict=verdict,
            score=avg_score,
            reasoning=f"No veto: Lynch {lynch_score:.0f}, Buffett {buffett_score:.0f}, avg {avg_score:.1f}",
            lynch_contributed=True,
            buffett_contributed=True
        )


class PositionSizer:
    """Calculates position sizes for trades."""

    def __init__(self, db):
        self.db = db

    def calculate_position(
        self,
        portfolio_id: int,
        symbol: str,
        conviction_score: float,
        method: str,
        rules: Dict[str, Any],
        other_buys: List[Dict[str, Any]] = None,
        current_price: float = None
    ) -> PositionSize:
        """Calculate shares to buy based on sizing method.

        Methods:
        - equal_weight: Divide equally among all positions
        - conviction_weighted: Higher conviction = larger position
        - fixed_pct: Fixed percentage of portfolio per position
        - kelly: Kelly criterion based on expected value

        Args:
            portfolio_id: Portfolio to trade in
            symbol: Stock symbol
            conviction_score: 0-100 score
            method: Sizing method
            rules: Position sizing rules from strategy
            other_buys: Other stocks being bought this run
            current_price: Current stock price (fetched if not provided)

        Returns:
            PositionSize with shares, value, and reasoning
        """
        if other_buys is None:
            other_buys = []

        # Get portfolio state
        summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
        if not summary:
            return PositionSize(0, 0.0, 0.0, "Portfolio not found")

        total_value = summary.get('total_value', 0)
        available_cash = summary.get('cash', 0)
        holdings = summary.get('holdings', {})

        # Get current price if not provided
        if current_price is None:
            current_price = self._fetch_price(symbol)
            if not current_price:
                return PositionSize(0, 0.0, 0.0, f"Price unavailable for {symbol}")

        # Calculate maximum allowed position value
        max_position_pct = rules.get('max_position_pct', 5.0)
        max_position_value = total_value * (max_position_pct / 100)

        # Check current position
        current_shares = holdings.get(symbol, 0)
        current_value = current_shares * current_price

        # Room to add
        room_to_add = max_position_value - current_value
        if room_to_add <= 0:
            return PositionSize(
                0, 0.0, 0.0,
                f"Already at max position ({current_shares} shares = ${current_value:.2f})"
            )

        # Calculate target size based on method
        if method == 'equal_weight':
            target_value = self._size_equal_weight(available_cash, other_buys)
        elif method == 'conviction_weighted':
            target_value = self._size_conviction_weighted(
                available_cash, conviction_score, other_buys
            )
        elif method == 'fixed_pct':
            target_value = self._size_fixed_pct(total_value, rules)
        elif method == 'kelly':
            target_value = self._size_kelly(total_value, conviction_score, rules)
        else:
            target_value = self._size_equal_weight(available_cash, other_buys)

        # Apply constraints
        final_value = min(target_value, room_to_add, available_cash)
        final_value = max(final_value, 0)

        # Apply minimum position size
        min_position = rules.get('min_position_value', 500)
        if 0 < final_value < min_position:
            if available_cash >= min_position:
                final_value = min_position
            else:
                final_value = 0

        shares = int(final_value / current_price)

        return PositionSize(
            shares=shares,
            estimated_value=shares * current_price,
            position_pct=(shares * current_price) / total_value * 100 if total_value > 0 else 0,
            reasoning=f"{method}: ${final_value:.2f} -> {shares} shares @ ${current_price:.2f}"
        )

    def _fetch_price(self, symbol: str) -> Optional[float]:
        """Fetch current price from database."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT price FROM stock_metrics WHERE symbol = %s",
                (symbol,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            self.db.return_connection(conn)

    def _size_equal_weight(
        self,
        available_cash: float,
        other_buys: List[Dict[str, Any]]
    ) -> float:
        """Divide cash equally among all buys."""
        num_buys = len(other_buys) + 1
        return available_cash / num_buys

    def _size_conviction_weighted(
        self,
        available_cash: float,
        conviction_score: float,
        other_buys: List[Dict[str, Any]]
    ) -> float:
        """Weight by conviction score."""
        total_conviction = conviction_score + sum(
            b.get('conviction', 50) for b in other_buys
        )
        if total_conviction == 0:
            return self._size_equal_weight(available_cash, other_buys)

        weight = conviction_score / total_conviction
        return available_cash * weight

    def _size_fixed_pct(
        self,
        total_value: float,
        rules: Dict[str, Any]
    ) -> float:
        """Fixed percentage of portfolio."""
        target_pct = rules.get('fixed_position_pct', 5.0)
        return total_value * (target_pct / 100)

    def _size_kelly(
        self,
        total_value: float,
        conviction_score: float,
        rules: Dict[str, Any]
    ) -> float:
        """Simplified Kelly criterion.

        Full Kelly: f* = (bp - q) / b
        We approximate: p = conviction/100, assuming 1:1 payoff
        Then apply kelly_fraction for safety (typically 0.25 = quarter-Kelly)
        """
        kelly_fraction = rules.get('kelly_fraction', 0.25)

        # Convert conviction (0-100) to probability (0.5-1.0)
        p = max(0.5, conviction_score / 100)
        q = 1 - p

        # Assume 1:1 payoff (b=1)
        b = 1
        kelly_pct = (b * p - q) / b

        # Apply fractional Kelly and cap
        safe_pct = kelly_pct * kelly_fraction
        safe_pct = max(0, min(safe_pct, 0.25))  # Cap at 25%

        return total_value * safe_pct


class ExitConditionChecker:
    """Checks existing positions against exit conditions."""

    def __init__(self, db):
        self.db = db

    def check_exits(
        self,
        portfolio_id: int,
        exit_conditions: Dict[str, Any],
        scoring_func=None
    ) -> List[ExitSignal]:
        """Check all holdings against exit conditions.

        Exit conditions format:
        {
            "profit_target_pct": 50,      # Sell if up 50%
            "stop_loss_pct": -20,         # Sell if down 20%
            "max_hold_days": 365,         # Sell after 1 year
            "score_degradation": {
                "lynch_below": 40,
                "buffett_below": 40
            }
        }

        Args:
            portfolio_id: Portfolio to check
            exit_conditions: Exit rules
            scoring_func: Optional function to re-score stocks (for degradation check)

        Returns:
            List of ExitSignal for positions that should be sold
        """
        if not exit_conditions:
            return []

        exits = []
        holdings = self.db.get_portfolio_holdings_detailed(portfolio_id, use_live_prices=False)

        for holding in holdings:
            signal = self._check_holding(holding, exit_conditions, scoring_func)
            if signal:
                exits.append(signal)

        return exits

    def _check_holding(
        self,
        holding: Dict[str, Any],
        conditions: Dict[str, Any],
        scoring_func
    ) -> Optional[ExitSignal]:
        """Check a single holding against exit conditions."""
        symbol = holding['symbol']
        quantity = holding['quantity']
        current_value = holding.get('current_value', 0)
        cost_basis = holding.get('total_cost', 0)

        if cost_basis > 0:
            gain_pct = ((current_value - cost_basis) / cost_basis) * 100
        else:
            gain_pct = 0

        # Check profit target
        profit_target = conditions.get('profit_target_pct')
        if profit_target and gain_pct >= profit_target:
            return ExitSignal(
                symbol=symbol,
                quantity=quantity,
                reason=f"Profit target hit: {gain_pct:.1f}% >= {profit_target}%",
                current_value=current_value,
                gain_pct=gain_pct
            )

        # Check stop loss
        stop_loss = conditions.get('stop_loss_pct')
        if stop_loss and gain_pct <= stop_loss:
            return ExitSignal(
                symbol=symbol,
                quantity=quantity,
                reason=f"Stop loss hit: {gain_pct:.1f}% <= {stop_loss}%",
                current_value=current_value,
                gain_pct=gain_pct
            )

        # Check hold duration (would need transaction dates)
        # TODO: Implement max_hold_days check

        # Check score degradation
        degradation = conditions.get('score_degradation')
        if degradation and scoring_func:
            signal = self._check_score_degradation(
                symbol, quantity, current_value, gain_pct, degradation, scoring_func
            )
            if signal:
                return signal

        return None

    def _check_score_degradation(
        self,
        symbol: str,
        quantity: int,
        current_value: float,
        gain_pct: float,
        degradation: Dict[str, Any],
        scoring_func
    ) -> Optional[ExitSignal]:
        """Check if stock scores have degraded below thresholds."""
        try:
            scores = scoring_func(symbol)
            lynch_threshold = degradation.get('lynch_below')
            buffett_threshold = degradation.get('buffett_below')

            if lynch_threshold and scores.get('lynch_score', 100) < lynch_threshold:
                return ExitSignal(
                    symbol=symbol,
                    quantity=quantity,
                    reason=f"Lynch score degraded: {scores['lynch_score']:.0f} < {lynch_threshold}",
                    current_value=current_value,
                    gain_pct=gain_pct
                )

            if buffett_threshold and scores.get('buffett_score', 100) < buffett_threshold:
                return ExitSignal(
                    symbol=symbol,
                    quantity=quantity,
                    reason=f"Buffett score degraded: {scores['buffett_score']:.0f} < {buffett_threshold}",
                    current_value=current_value,
                    gain_pct=gain_pct
                )
        except Exception as e:
            logger.warning(f"Failed to check score degradation for {symbol}: {e}")

        return None


class HoldingReevaluator:
    """Checks if held positions still meet entry criteria."""

    def __init__(self, db, condition_evaluator, lynch_criteria):
        self.db = db
        self.condition_evaluator = condition_evaluator
        self.lynch_criteria = lynch_criteria

    def check_holdings(
        self,
        portfolio_id: int,
        strategy_conditions: Dict[str, Any],
        reevaluation_config: Dict[str, Any]
    ) -> List[ExitSignal]:
        """Check all holdings against re-evaluation criteria.

        Args:
            portfolio_id: Portfolio to check
            strategy_conditions: Strategy conditions (universe filters, scoring requirements)
            reevaluation_config: Re-evaluation configuration with:
                - enabled: bool
                - check_universe_filters: bool
                - check_scoring_requirements: bool
                - grace_period_days: int

        Returns:
            List of ExitSignal for positions that fail re-evaluation
        """
        if not reevaluation_config.get('enabled', False):
            return []

        holdings = self.db.get_portfolio_holdings(portfolio_id)
        if not holdings:
            return []

        entry_dates = self.db.get_position_entry_dates(portfolio_id)
        grace_period = reevaluation_config.get('grace_period_days', 30)

        exits = []
        for symbol, quantity in holdings.items():
            # Apply grace period
            entry_info = entry_dates.get(symbol, {})
            days_held = entry_info.get('days_held', 0)
            if days_held < grace_period:
                logger.debug(f"Skipping {symbol} re-evaluation: within grace period ({days_held}/{grace_period} days)")
                continue

            # Check universe filters
            if reevaluation_config.get('check_universe_filters', True):
                exit_signal = self._check_universe_compliance(
                    symbol, quantity, strategy_conditions
                )
                if exit_signal:
                    exits.append(exit_signal)
                    continue

            # Check scoring requirements
            if reevaluation_config.get('check_scoring_requirements', True):
                exit_signal = self._check_scoring_compliance(
                    symbol, quantity, strategy_conditions
                )
                if exit_signal:
                    exits.append(exit_signal)
                    continue

            # Update last evaluated date
            self.db.update_position_evaluation_date(portfolio_id, symbol)

        return exits

    def _check_universe_compliance(
        self,
        symbol: str,
        quantity: int,
        conditions: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """Check if position still passes universe filters."""
        try:
            # Evaluate universe with just this symbol
            passing_symbols = self.condition_evaluator.evaluate_universe(conditions)

            if symbol not in passing_symbols:
                # Get current price for exit signal
                price = self._get_current_price(symbol)
                current_value = quantity * price if price else 0

                return ExitSignal(
                    symbol=symbol,
                    quantity=quantity,
                    reason=f"Re-evaluation: No longer passes universe filters",
                    current_value=current_value,
                    gain_pct=0.0  # Will be calculated by caller if needed
                )
        except Exception as e:
            logger.warning(f"Failed universe compliance check for {symbol}: {e}")

        return None

    def _check_scoring_compliance(
        self,
        symbol: str,
        quantity: int,
        conditions: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """Check if position still meets scoring requirements."""
        try:
            from lynch_criteria import SCORE_THRESHOLDS

            scoring_reqs = conditions.get('scoring_requirements', [])
            if not scoring_reqs:
                return None

            # Default thresholds
            lynch_req = SCORE_THRESHOLDS.get('BUY', 60)
            buffett_req = SCORE_THRESHOLDS.get('BUY', 60)

            for req in scoring_reqs:
                if req.get('character') == 'lynch':
                    lynch_req = req.get('min_score', lynch_req)
                elif req.get('character') == 'buffett':
                    buffett_req = req.get('min_score', buffett_req)

            # Score the stock
            lynch_result = self.lynch_criteria.evaluate_stock(symbol, character_id='lynch')
            buffett_result = self.lynch_criteria.evaluate_stock(symbol, character_id='buffett')

            lynch_score = lynch_result.get('overall_score', 0) if lynch_result else 0
            buffett_score = buffett_result.get('overall_score', 0) if buffett_result else 0

            # Check if still meets requirements (OR logic: at least one must pass)
            lynch_pass = lynch_score >= lynch_req
            buffett_pass = buffett_score >= buffett_req

            if not (lynch_pass or buffett_pass):
                price = self._get_current_price(symbol)
                current_value = quantity * price if price else 0

                return ExitSignal(
                    symbol=symbol,
                    quantity=quantity,
                    reason=f"Re-evaluation: Scores degraded (Lynch {lynch_score:.0f} < {lynch_req}, Buffett {buffett_score:.0f} < {buffett_req})",
                    current_value=current_value,
                    gain_pct=0.0
                )

        except Exception as e:
            logger.warning(f"Failed scoring compliance check for {symbol}: {e}")

        return None

    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from database."""
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT price FROM stock_metrics WHERE symbol = %s", (symbol,))
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            self.db.return_connection(conn)


class BenchmarkTracker:
    """Tracks strategy performance vs S&P 500."""

    def __init__(self, db):
        self.db = db

    def record_daily_benchmark(self) -> Dict[str, Any]:
        """Record daily SPY price. Call once per day after market close."""
        try:
            import yfinance as yf
            spy = yf.Ticker("SPY")
            price = spy.fast_info.get('lastPrice')

            if not price:
                raise ValueError("Could not fetch SPY price")

            today = date.today()
            self.db.save_benchmark_snapshot(today, price)

            return {'date': today, 'spy_price': price}
        except Exception as e:
            logger.error(f"Failed to record benchmark: {e}")
            raise

    def record_strategy_performance(
        self,
        strategy_id: int,
        portfolio_value: float
    ) -> Dict[str, Any]:
        """Record strategy performance and calculate alpha."""
        today = date.today()

        # Get inception data
        inception = self.db.get_strategy_inception_data(strategy_id)

        if inception:
            inception_value = inception['portfolio_value']
            inception_spy = inception['spy_price']
        else:
            # First run - current values as inception
            inception_value = portfolio_value
            benchmark = self.db.get_benchmark_snapshot(today)
            inception_spy = benchmark['spy_price'] if benchmark else None

        # Get current SPY
        benchmark = self.db.get_benchmark_snapshot(today)
        current_spy = benchmark['spy_price'] if benchmark else None

        # Calculate returns
        if inception_value and inception_value > 0:
            portfolio_return_pct = ((portfolio_value - inception_value) / inception_value) * 100
        else:
            portfolio_return_pct = 0

        if inception_spy and inception_spy > 0 and current_spy:
            spy_return_pct = ((current_spy - inception_spy) / inception_spy) * 100
        else:
            spy_return_pct = 0

        alpha = portfolio_return_pct - spy_return_pct

        # Save performance
        self.db.save_strategy_performance(
            strategy_id, today, portfolio_value,
            portfolio_return_pct, spy_return_pct, alpha
        )

        return {
            'date': today,
            'portfolio_value': portfolio_value,
            'portfolio_return_pct': portfolio_return_pct,
            'spy_return_pct': spy_return_pct,
            'alpha': alpha
        }

    def get_performance_series(
        self,
        strategy_id: int,
        days: int = 365
    ) -> List[Dict[str, Any]]:
        """Get time series of performance for charting."""
        from datetime import timedelta
        start_date = date.today() - timedelta(days=days)
        return self.db.get_strategy_performance(strategy_id, start_date)


class StrategyExecutor:
    """Main orchestrator for autonomous strategy execution."""

    def __init__(self, db, analyst=None, lynch_criteria=None):
        self.db = db
        self.condition_evaluator = ConditionEvaluator(db)
        self.consensus_engine = ConsensusEngine()
        self.position_sizer = PositionSizer(db)
        self.exit_checker = ExitConditionChecker(db)
        self.benchmark_tracker = BenchmarkTracker(db)

        # Lazily initialize analyst and lynch_criteria if not provided
        self._analyst = analyst
        self._lynch_criteria = lynch_criteria
        self._holding_reevaluator = None

    @property
    def analyst(self):
        """Lazy initialization of StockAnalyst."""
        if self._analyst is None:
            from stock_analyst import StockAnalyst
            self._analyst = StockAnalyst(self.db)
        return self._analyst

    @property
    def lynch_criteria(self):
        """Lazy initialization of LynchCriteria."""
        if self._lynch_criteria is None:
            from lynch_criteria import LynchCriteria
            from earnings_analyzer import EarningsAnalyzer
            analyzer = EarningsAnalyzer(self.db)
            self._lynch_criteria = LynchCriteria(self.db, analyzer)
        return self._lynch_criteria

    @property
    def holding_reevaluator(self):
        """Lazy initialization of HoldingReevaluator."""
        if self._holding_reevaluator is None:
            self._holding_reevaluator = HoldingReevaluator(
                self.db,
                self.condition_evaluator,
                self.lynch_criteria
            )
        return self._holding_reevaluator

    def execute_strategy(self, strategy_id: int, limit: Optional[int] = None) -> Dict[str, Any]:
        """Execute a strategy run.
        
        Args:
            strategy_id: ID of strategy to run
            limit: Optional limit on number of stocks to score
            
        Returns:
            Summary of the run with statistics
        """
        # Load strategy
        print(f"Loading strategy {strategy_id}...")
        strategy = self.db.get_strategy(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        if not strategy.get('enabled', True):
            return {'status': 'skipped', 'reason': 'Strategy is disabled'}

        print(f"✓ Strategy loaded: {strategy.get('name', 'Unnamed')}")

        # Create run record
        run_id = self.db.create_strategy_run(strategy_id)
        print(f"✓ Created run record: {run_id}\n")

        try:
            # Record benchmark
            print("Recording benchmark (SPY price)...")
            self.benchmark_tracker.record_daily_benchmark()
            print("✓ Benchmark recorded\n")

            # Get portfolio state
            portfolio_id = strategy['portfolio_id']
            summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
            portfolio_value = summary['total_value'] if summary else 0

            self.db.update_strategy_run(
                run_id,
                portfolio_value=portfolio_value,
                spy_price=self._get_spy_price()
            )

            # Phase 1: Screen candidates
            print("=" * 60)
            print("PHASE 1: SCREENING")
            print("=" * 60)
            self._log_event(run_id, "Starting screening phase")
            conditions = strategy.get('conditions', {})
            all_candidates = self.condition_evaluator.evaluate_universe(conditions)

            # Apply limit if requested
            if limit and limit > 0:
                print(f"  Limiting candidates to {limit} per request (found {len(all_candidates)})")
                all_candidates = all_candidates[:limit]

            # Separate held vs new positions
            holdings = self.db.get_portfolio_holdings(portfolio_id)
            held_symbols = set(holdings.keys())
            new_candidates = [s for s in all_candidates if s not in held_symbols]
            held_candidates = [s for s in all_candidates if s in held_symbols]

            print(f"  Universe breakdown:")
            print(f"    New positions: {len(new_candidates)}")
            print(f"    Position additions: {len(held_candidates)}")
            if held_candidates:
                print(f"    Held stocks in universe: {held_candidates}")

            self.db.update_strategy_run(run_id, stocks_screened=len(all_candidates))
            self._log_event(run_id, f"Screened {len(all_candidates)} candidates ({len(new_candidates)} new, {len(held_candidates)} additions)")
            print(f"✓ Screened {len(all_candidates)} total candidates\n")

            # Phase 2: Score candidates (with differentiated thresholds)
            print("=" * 60)
            print("PHASE 2: SCORING")
            print("=" * 60)

            # Score new positions with standard thresholds
            scored_new = []
            if new_candidates:
                print(f"  Scoring {len(new_candidates)} new position candidates...")
                scored_new = self._score_candidates(new_candidates, conditions, run_id, is_addition=False)
                print(f"  ✓ {len(scored_new)} new positions passed requirements\n")

            # Score additions with higher thresholds
            scored_additions = []
            if held_candidates:
                print(f"  Scoring {len(held_candidates)} position addition candidates (higher thresholds)...")
                scored_additions = self._score_candidates(held_candidates, conditions, run_id, is_addition=True)
                print(f"  ✓ {len(scored_additions)} additions passed requirements\n")

            # Combine scored candidates
            scored = scored_new + scored_additions
            self.db.update_strategy_run(run_id, stocks_scored=len(scored))
            print(f"✓ Scored {len(scored)} stocks that passed requirements\n")

            # Phase 3: Generate theses (if required)
            print("=" * 60)
            print("PHASE 3: THESIS GENERATION")
            print("=" * 60)
            if conditions.get('require_thesis', False):
                user_id = strategy.get('user_id')
                enriched = self._generate_theses(scored, run_id, user_id)
                self.db.update_strategy_run(run_id, theses_generated=len(enriched))
                print(f"✓ Generated {len(enriched)} theses\n")
            else:
                print("Skipping (thesis not required)\n")
                enriched = scored

            # Phase 4: Deliberate (Lynch and Buffett discuss their theses)
            print("=" * 60)
            print("PHASE 4: DELIBERATION")
            print("=" * 60)
            user_id = strategy.get('user_id')
            decisions = self._deliberate(enriched, run_id, conditions, user_id)
            print(f"✓ {len(decisions)} BUY decisions made\n")

            # Phase 4.5: Process dividends (ensures cash reflects latest dividends before trades)
            print("=" * 60)
            print("PHASE 4.5: DIVIDEND PROCESSING")
            print("=" * 60)
            try:
                from dividend_manager import DividendManager
                dividend_mgr = DividendManager(self.db)
                dividend_mgr.process_all_portfolios()
                print("✓ Dividend processing complete\n")
                self._log_event(run_id, "Processed dividends for all portfolios")
            except Exception as e:
                logger.warning(f"Dividend processing failed (non-critical): {e}")
                print(f"⚠ Dividend processing failed: {e}\n")

            # Phase 5: Check exits
            print("=" * 60)
            print("PHASE 5: EXIT CHECKS")
            print("=" * 60)
            exit_conditions = strategy.get('exit_conditions', {})
            exits = self.exit_checker.check_exits(
                portfolio_id,
                exit_conditions,
                scoring_func=self._get_current_scores
            )
            print(f"✓ Found {len(exits)} positions to exit\n")

            # Phase 5.5: Holding Re-evaluation (check if held positions still meet criteria)
            print("=" * 60)
            print("PHASE 5.5: HOLDING RE-EVALUATION")
            print("=" * 60)
            reevaluation_config = conditions.get('holding_reevaluation', {})
            if reevaluation_config.get('enabled', False):
                reevaluation_exits = self.holding_reevaluator.check_holdings(
                    portfolio_id,
                    conditions,
                    reevaluation_config
                )
                if reevaluation_exits:
                    print(f"✓ Re-evaluation flagged {len(reevaluation_exits)} positions for exit:")
                    for exit_signal in reevaluation_exits:
                        print(f"    {exit_signal.symbol}: {exit_signal.reason}")
                    exits.extend(reevaluation_exits)
                    self._log_event(run_id, f"Re-evaluation: {len(reevaluation_exits)} positions flagged for exit")
                else:
                    print("✓ All held positions still meet criteria")
            else:
                print("Skipping (re-evaluation not enabled)\n")

            # Phase 6: Execute trades
            print("=" * 60)
            print("PHASE 6: TRADE EXECUTION")
            print("=" * 60)
            trades_executed = self._execute_trades(
                decisions, exits, strategy, run_id
            )
            print(f"✓ Executed {trades_executed} trades\n")

            # Phase 7: Record performance
            new_summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
            new_value = new_summary['total_value'] if new_summary else portfolio_value

            perf = self.benchmark_tracker.record_strategy_performance(strategy_id, new_value)

            # Complete run
            self.db.update_strategy_run(
                run_id,
                status='completed',
                completed_at=datetime.now(),
                trades_executed=trades_executed
            )

            return {
                'status': 'completed',
                'run_id': run_id,
                'stocks_screened': len(candidates),
                'stocks_scored': len(scored),
                'theses_generated': len(enriched) if conditions.get('require_thesis') else 0,
                'trades_executed': trades_executed,
                'alpha': perf.get('alpha', 0)
            }

        except Exception as e:
            logger.error(f"Strategy execution failed: {e}")
            self.db.update_strategy_run(
                run_id,
                status='failed',
                completed_at=datetime.now(),
                error_message=str(e)
            )
            raise

    def _get_spy_price(self) -> Optional[float]:
        """Get current SPY price from benchmark snapshots."""
        benchmark = self.db.get_benchmark_snapshot(date.today())
        return benchmark['spy_price'] if benchmark else None

    def _get_current_scores(self, symbol: str) -> Dict[str, Any]:
        """Get current Lynch and Buffett scores for a symbol.

        Used by ExitConditionChecker for score degradation checks.
        """
        scores = {}
        try:
            lynch_result = self.lynch_criteria.evaluate_stock(symbol, character_id='lynch')
            if lynch_result:
                scores['lynch_score'] = lynch_result.get('overall_score', 0)
                scores['lynch_status'] = lynch_result.get('overall_status', 'N/A')

            buffett_result = self.lynch_criteria.evaluate_stock(symbol, character_id='buffett')
            if buffett_result:
                scores['buffett_score'] = buffett_result.get('overall_score', 0)
                scores['buffett_status'] = buffett_result.get('overall_status', 'N/A')
        except Exception as e:
            logger.warning(f"Failed to get scores for {symbol}: {e}")

        return scores

    def _log_event(self, run_id: int, message: str):
        """Log an event to the run log."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'message': message
        }
        self.db.append_to_run_log(run_id, event)
        logger.info(f"[Run {run_id}] {message}")

    def _score_candidates(
        self,
        candidates: List[str],
        conditions: Dict[str, Any],
        run_id: int,
        is_addition: bool = False
    ) -> List[Dict[str, Any]]:
        """Score candidates with Lynch and Buffett scoring.

        Args:
            candidates: List of symbols to score
            conditions: Strategy conditions with scoring requirements
            run_id: Current run ID for logging
            is_addition: If True, use higher thresholds for position additions

        Returns:
            List of stocks that passed scoring requirements
        """
        from lynch_criteria import SCORE_THRESHOLDS
        scored = []
        scoring_reqs = conditions.get('scoring_requirements', [])

        # Parse scoring requirements (Default to 'BUY' threshold - 60)
        # We use OR logic: A stock must meet AT LEAST ONE criteria to pass.
        default_min = SCORE_THRESHOLDS.get('BUY', 60)
        lynch_req = default_min
        buffett_req = default_min

        # For additions, use higher thresholds if configured
        if is_addition:
            addition_reqs = conditions.get('addition_scoring_requirements', [])
            if addition_reqs:
                # Use explicit addition requirements
                for req in addition_reqs:
                    if req.get('character') == 'lynch':
                        lynch_req = req.get('min_score', default_min)
                    elif req.get('character') == 'buffett':
                        buffett_req = req.get('min_score', default_min)
            else:
                # Default: +10 higher than base requirements
                for req in scoring_reqs:
                    if req.get('character') == 'lynch':
                        lynch_req = req.get('min_score', default_min) + 10
                    elif req.get('character') == 'buffett':
                        buffett_req = req.get('min_score', default_min) + 10
                # If no base requirements, use default + 10
                if not scoring_reqs:
                    lynch_req = default_min + 10
                    buffett_req = default_min + 10
        else:
            # New positions: use standard requirements
            for req in scoring_reqs:
                if req.get('character') == 'lynch':
                    lynch_req = req.get('min_score', default_min)
                elif req.get('character') == 'buffett':
                    buffett_req = req.get('min_score', default_min)

        position_type = "addition" if is_addition else "new position"
        self._log_event(run_id, f"Scoring {len(candidates)} {position_type} candidates (Lynch: {lynch_req}, Buffett: {buffett_req})")

        for symbol in candidates:
            try:
                stock_data = {
                    'symbol': symbol,
                    'position_type': 'addition' if is_addition else 'new'
                }
                type_label = "ADDITION" if is_addition else "NEW"
                print(f"  Scoring {symbol} ({type_label})...")

                # Score with Lynch
                print(f"    - Evaluating with Lynch criteria...")
                lynch_result = self.lynch_criteria.evaluate_stock(symbol, character_id='lynch')
                if lynch_result:
                    stock_data['lynch_score'] = lynch_result.get('overall_score', 0)
                    stock_data['lynch_status'] = lynch_result.get('overall_status', 'N/A')
                    print(f"      Lynch: {stock_data['lynch_score']:.0f} ({stock_data['lynch_status']})")
                else:
                    stock_data['lynch_score'] = 0
                    stock_data['lynch_status'] = 'ERROR'
                    print(f"      Lynch: ERROR")

                # Score with Buffett
                print(f"    - Evaluating with Buffett criteria...")
                buffett_result = self.lynch_criteria.evaluate_stock(symbol, character_id='buffett')
                if buffett_result:
                    stock_data['buffett_score'] = buffett_result.get('overall_score', 0)
                    stock_data['buffett_status'] = buffett_result.get('overall_status', 'N/A')
                    print(f"      Buffett: {stock_data['buffett_score']:.0f} ({stock_data['buffett_status']})")
                else:
                    stock_data['buffett_score'] = 0
                    stock_data['buffett_status'] = 'ERROR'
                    print(f"      Buffett: ERROR")

                # Check if passes scoring requirements (OR Logic)
                # Pass if ANY requirement is met
                lynch_pass = stock_data['lynch_score'] >= lynch_req
                buffett_pass = stock_data['buffett_score'] >= buffett_req
                
                passes = lynch_pass or buffett_pass
                
                if passes:
                    scored.append(stock_data)
                    # Create reasoning string for log
                    reason_parts = []
                    if lynch_pass:
                        reason_parts.append(f"Lynch {stock_data['lynch_score']:.0f} >= {lynch_req}")
                    if buffett_pass:
                        reason_parts.append(f"Buffett {stock_data['buffett_score']:.0f} >= {buffett_req}")

                    reason_str = ", ".join(reason_parts)

                    threshold_note = " (higher bar for additions)" if is_addition else ""
                    print(f"    ✓ PASSED requirements ({reason_str}){threshold_note}")
                    logger.debug(
                        f"{symbol}: PASSED as {type_label} ({reason_str})"
                    )
                else:
                    fail_reasons = []
                    if not lynch_pass:
                        fail_reasons.append(f"Lynch {stock_data['lynch_score']:.0f} < {lynch_req}")
                    if not buffett_pass:
                        fail_reasons.append(f"Buffett {stock_data['buffett_score']:.0f} < {buffett_req}")


                    fail_str = ", ".join(fail_reasons)
                    threshold_note = " (higher bar for additions)" if is_addition else ""
                    print(f"    ✗ FAILED requirements ({fail_str}){threshold_note}")

            except Exception as e:
                logger.warning(f"Failed to score {symbol}: {e}")
                continue

        self._log_event(run_id, f"Scoring complete: {len(scored)}/{len(candidates)} {position_type}s passed requirements")
        return scored

    def _generate_theses(
        self,
        scored: List[Dict[str, Any]],
        run_id: int,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """Generate investment theses for scored stocks.

        Generates theses from BOTH Lynch and Buffett characters, each with
        their own verdict (BUY/WATCH/AVOID).

        Args:
            scored: List of scored stock data
            run_id: Current run ID for logging
            user_id: User ID who owns the strategy (for saving analyses)

        Returns:
            List of stocks enriched with thesis data from both characters
        """
        self._log_event(run_id, f"Generating theses for {len(scored)} stocks")
        enriched = []

        for stock in scored:
            symbol = stock['symbol']
            print(f"  Generating theses for {symbol}...")

            try:
                # Get stock data for thesis generation
                stock_metrics = self.db.get_stock_metrics(symbol)
                if not stock_metrics:
                    logger.warning(f"No metrics for {symbol}, skipping thesis")
                    stock['lynch_thesis_verdict'] = None
                    stock['buffett_thesis_verdict'] = None
                    enriched.append(stock)
                    continue

                # Get earnings history
                history = self.db.get_earnings_history(symbol)

                # Generate Lynch thesis
                print(f"    - Generating Lynch thesis...")
                lynch_thesis_text = ""
                for chunk in self.analyst.get_or_generate_analysis(
                    user_id=user_id,
                    symbol=symbol,
                    stock_data=stock_metrics,
                    history=history or [],
                    use_cache=True,
                    character_id='lynch'
                ):
                    lynch_thesis_text += chunk

                lynch_verdict = self._extract_thesis_verdict(lynch_thesis_text)
                stock['lynch_thesis'] = lynch_thesis_text
                stock['lynch_thesis_verdict'] = lynch_verdict
                
                # Fetch timestamp for cache invalidation
                lynch_meta = self.db.get_lynch_analysis(user_id, symbol, character_id='lynch')
                stock['lynch_thesis_timestamp'] = lynch_meta.get('generated_at') if lynch_meta else None
                
                print(f"      Lynch verdict: {lynch_verdict}")

                # Generate Buffett thesis
                print(f"    - Generating Buffett thesis...")
                buffett_thesis_text = ""
                for chunk in self.analyst.get_or_generate_analysis(
                    user_id=user_id,
                    symbol=symbol,
                    stock_data=stock_metrics,
                    history=history or [],
                    use_cache=True,
                    character_id='buffett'
                ):
                    buffett_thesis_text += chunk

                buffett_verdict = self._extract_thesis_verdict(buffett_thesis_text)
                stock['buffett_thesis'] = buffett_thesis_text
                stock['buffett_thesis_verdict'] = buffett_verdict
                
                # Fetch timestamp for cache invalidation
                buffett_meta = self.db.get_lynch_analysis(user_id, symbol, character_id='buffett')
                stock['buffett_thesis_timestamp'] = buffett_meta.get('generated_at') if buffett_meta else None
                
                print(f"      Buffett verdict: {buffett_verdict}")

                logger.debug(f"{symbol}: Lynch={lynch_verdict}, Buffett={buffett_verdict}")
                enriched.append(stock)

            except Exception as e:
                logger.warning(f"Failed to generate thesis for {symbol}: {e}")
                stock['lynch_thesis_verdict'] = None
                stock['buffett_thesis_verdict'] = None
                enriched.append(stock)

        self._log_event(run_id, f"Thesis generation complete for {len(enriched)} stocks")
        return enriched

    def _conduct_deliberation(
        self,
        user_id: int,
        symbol: str,
        lynch_thesis: str,
        lynch_verdict: str,
        buffett_thesis: str,
        buffett_verdict: str,
        lynch_timestamp: Optional[datetime] = None,
        buffett_timestamp: Optional[datetime] = None
    ) -> tuple[str, str]:
        """Conduct deliberation between Lynch and Buffett to reach consensus.

        Args:
            user_id: User ID who owns the strategy
            symbol: Stock symbol
            lynch_thesis: Lynch's full thesis text
            lynch_verdict: Lynch's verdict (BUY/WATCH/AVOID)
            buffett_thesis: Buffett's full thesis text
            buffett_verdict: Buffett's verdict (BUY/WATCH/AVOID)
            lynch_timestamp: Timestamp when Lynch thesis was generated
            buffett_timestamp: Timestamp when Buffett thesis was generated

        Returns:
            Tuple of (deliberation_text, final_verdict)
        """
        import os
        import time
        from google.genai.types import GenerateContentConfig

        # Check cache first
        # Check cache first
        cached = self.db.get_deliberation(user_id, symbol)
        if cached:
            # Check for invalidation based on timestamps
            is_stale = False
            cached_time = cached['generated_at']
            
            # Ensure timezone awareness for comparison if needed
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=None) # Assume naive if inputs are naive
                
            invalidation_reason = ""
            
            if lynch_timestamp:
                if lynch_timestamp.tzinfo is None:
                    lynch_timestamp = lynch_timestamp.replace(tzinfo=None)
                if cached_time < lynch_timestamp:
                    is_stale = True
                    invalidation_reason = f"Lynch thesis newer ({lynch_timestamp} > {cached_time})"
            
            if not is_stale and buffett_timestamp:
                if buffett_timestamp.tzinfo is None:
                    buffett_timestamp = buffett_timestamp.replace(tzinfo=None)
                if cached_time < buffett_timestamp:
                    is_stale = True
                    invalidation_reason = f"Buffett thesis newer ({buffett_timestamp} > {cached_time})"
            
            if not is_stale:
                logger.info(f"[Deliberation] Using cached deliberation for {symbol}")
                print(f"    Using cached deliberation from {cached['generated_at']}")
                return cached['deliberation_text'], cached['final_verdict']
            else:
                logger.info(f"[Deliberation] Cache invalid for {symbol}: {invalidation_reason}")
                print(f"    Cache invalid: {invalidation_reason}")
                print(f"    Regenerating deliberation...")

        print(f"    No cached deliberation found, generating new one...")

        # Create deliberation prompt
        prompt = f"""You are facilitating a discussion between Peter Lynch and Warren Buffett about {symbol}.

LYNCH'S THESIS (Verdict: {lynch_verdict}):
{lynch_thesis}

BUFFETT'S THESIS (Verdict: {buffett_verdict}):
{buffett_thesis}

Now have them discuss these theses together. They should:
1. Acknowledge each other's key points
2. Discuss where they agree or disagree
3. Consider whether either should revise their verdict based on the other's insights
4. Reach a final consensus verdict

Format the output as a discussion between them, ending with:

## Final Consensus
**[BUY/WATCH/AVOID]**

Reasoning: [Brief explanation of their final decision]
"""

        # Retry configuration
        models = ['gemini-3-flash-preview', 'gemini-2.5-flash']
        max_retries = 3
        client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

        for model in models:
            retry_count = 0
            base_delay = 1

            while retry_count <= max_retries:
                try:
                    logger.info(f"[Deliberation] Sending request to {model} (attempt {retry_count + 1}/{max_retries + 1})...")
                    response = client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=GenerateContentConfig(
                            temperature=0.7,
                            top_p=0.95,
                            max_output_tokens=8192
                        )
                    )

                    deliberation_text = response.text

                    # Extract final verdict
                    final_verdict = self._extract_thesis_verdict(deliberation_text)

                    # Cache the deliberation
                    self.db.save_deliberation(
                        user_id=user_id,
                        symbol=symbol,
                        deliberation_text=deliberation_text,
                        final_verdict=final_verdict,
                        model_version=model
                    )

                    logger.info(f"[Deliberation] Success with {model}, cached for future use")
                    return deliberation_text, final_verdict

                except Exception as e:
                    error_msg = str(e)
                    retry_count += 1

                    if retry_count <= max_retries:
                        delay = base_delay * (2 ** (retry_count - 1))
                        logger.warning(f"[Deliberation] {model} failed (attempt {retry_count}/{max_retries + 1}): {error_msg}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.warning(f"[Deliberation] {model} failed after {max_retries + 1} attempts: {error_msg}")
                        break

        # All models failed
        raise Exception(f"Deliberation failed for {symbol} after trying all models with retries")

    def _extract_thesis_verdict(self, thesis_text: str) -> Optional[str]:
        """Extract BUY/WATCH/AVOID verdict from thesis text.

        The thesis typically starts with '## Bottom Line' followed by
        **BUY**, **WATCH**, or **AVOID**.
        """
        if not thesis_text:
            print("      WARNING: No thesis text to extract verdict from")
            return None

        # Look for verdict markers
        text_upper = thesis_text.upper()

        # Check for explicit verdict patterns
        if '**BUY**' in thesis_text or 'VERDICT: BUY' in text_upper:
            print("      Found BUY verdict (explicit)")
            return 'BUY'
        elif '**WATCH**' in thesis_text or 'VERDICT: WATCH' in text_upper:
            print("      Found WATCH verdict (explicit)")
            return 'WATCH'
        elif '**AVOID**' in thesis_text or 'VERDICT: AVOID' in text_upper:
            print("      Found AVOID verdict (explicit)")
            return 'AVOID'

        # Fallback: look in first 500 chars for verdict keywords
        first_section = text_upper[:500]
        if 'BUY' in first_section and 'AVOID' not in first_section:
            print("      Found BUY verdict (fallback in first 500 chars)")
            return 'BUY'
        elif 'AVOID' in first_section:
            print("      Found AVOID verdict (fallback in first 500 chars)")
            return 'AVOID'
        elif 'WATCH' in first_section or 'HOLD' in first_section:
            print("      Found WATCH verdict (fallback in first 500 chars)")
            return 'WATCH'

        print(f"      WARNING: Could not extract verdict. First 200 chars: {thesis_text[:200]}")
        return None

    def _deliberate(
        self,
        enriched: List[Dict[str, Any]],
        run_id: int,
        conditions: Dict[str, Any] = None,
        user_id: int = None
    ) -> List[Dict[str, Any]]:
        """Apply consensus logic to determine final decisions.

        For stocks with theses, conducts deliberation between Lynch and Buffett.
        Otherwise, uses score-based consensus evaluation.

        Args:
            enriched: Stocks with scores and optional thesis data
            run_id: Current run ID for logging
            conditions: Strategy conditions (for thesis_verdict_required filtering)
            user_id: User ID who owns the strategy

        Returns:
            List of stocks with BUY decisions
        """
        decisions = []
        conditions = conditions or {}
        thesis_verdicts_required = conditions.get('thesis_verdict_required', [])

        for stock in enriched:
            symbol = stock['symbol']

            # If we have both theses, conduct deliberation
            lynch_thesis = stock.get('lynch_thesis')
            buffett_thesis = stock.get('buffett_thesis')

            if lynch_thesis and buffett_thesis:
                print(f"  Conducting deliberation for {symbol}...")

                try:
                    deliberation_text, final_verdict = self._conduct_deliberation(
                        user_id=user_id,
                        symbol=symbol,
                        lynch_thesis=lynch_thesis,
                        lynch_verdict=stock.get('lynch_thesis_verdict', 'UNKNOWN'),
                        buffett_thesis=buffett_thesis,
                        buffett_verdict=stock.get('buffett_thesis_verdict', 'UNKNOWN'),
                        lynch_timestamp=stock.get('lynch_thesis_timestamp'),
                        buffett_timestamp=stock.get('buffett_thesis_timestamp')
                    )

                    stock['deliberation'] = deliberation_text
                    stock['final_verdict'] = final_verdict
                    print(f"    Final verdict after deliberation: {final_verdict}")
                    print(f"    Deliberation text length: {len(deliberation_text) if deliberation_text else 0} chars")

                except Exception as e:
                    logger.error(f"Deliberation failed for {symbol}: {e}")
                    stock['final_verdict'] = None
                    stock['deliberation'] = None
                    print(f"    Deliberation FAILED: {e}")

                # Check if final verdict meets requirements
                if thesis_verdicts_required:
                    final_verdict = stock.get('final_verdict')
                    if final_verdict not in thesis_verdicts_required:
                        # Record as SKIP
                        self.db.create_strategy_decision(
                            run_id=run_id,
                            symbol=symbol,
                            lynch_score=stock.get('lynch_score'),
                            lynch_status=stock.get('lynch_status'),
                            buffett_score=stock.get('buffett_score'),
                            buffett_status=stock.get('buffett_status'),
                            consensus_score=None,
                            consensus_verdict=final_verdict,
                            thesis_verdict=final_verdict,
                            thesis_summary=stock.get('deliberation', '')[:500] if stock.get('deliberation') else None,
                            thesis_full=stock.get('deliberation'),
                            final_decision='SKIP',
                            decision_reasoning=f"Deliberation verdict '{final_verdict}' not in required: {thesis_verdicts_required}"
                        )
                        continue

                # If verdict is BUY, add to decisions
                if stock.get('final_verdict') == 'BUY':
                    decisions.append(stock)
                    final_decision = 'BUY'
                else:
                    final_decision = 'SKIP'

                # Record decision
                self.db.create_strategy_decision(
                    run_id=run_id,
                    symbol=symbol,
                    lynch_score=stock.get('lynch_score'),
                    lynch_status=stock.get('lynch_status'),
                    buffett_score=stock.get('buffett_score'),
                    buffett_status=stock.get('buffett_status'),
                    consensus_score=None,
                    consensus_verdict=stock.get('final_verdict'),
                    thesis_verdict=stock.get('final_verdict'),
                    thesis_summary=stock.get('deliberation', '')[:500] if stock.get('deliberation') else None,
                    thesis_full=stock.get('deliberation'),
                    final_decision=final_decision,
                    decision_reasoning=f"Deliberation result: {stock.get('final_verdict')}"
                )

            else:
                # No theses available - SKIP
                # We now strictly require AI deliberation to trade.
                print(f"    ⚠ Skipping {symbol}: No theses generated for deliberation")
                self.db.create_strategy_decision(
                    run_id=run_id,
                    symbol=symbol,
                    lynch_score=stock.get('lynch_score'),
                    lynch_status=stock.get('lynch_status'),
                    buffett_score=stock.get('buffett_score'),
                    buffett_status=stock.get('buffett_status'),
                    consensus_score=None,
                    consensus_verdict='SKIP',
                    thesis_verdict=None,
                    thesis_summary=None,
                    thesis_full=None,
                    final_decision='SKIP',
                    decision_reasoning="Skipped: No theses generated for AI deliberation"
                )

        return decisions

    def _calculate_all_positions(
        self,
        buy_decisions: List[Dict[str, Any]],
        portfolio_id: int,
        available_cash: float,
        method: str,
        rules: Dict[str, Any],
        run_id: int
    ) -> List[Dict[str, Any]]:
        """Phase 1: Calculate all positions with priority ordering.

        Calculates position sizes for all buy decisions, prioritizes by conviction,
        and ensures total doesn't exceed available cash.

        Args:
            buy_decisions: List of stocks with BUY decisions
            portfolio_id: Portfolio to trade in
            available_cash: Current available cash
            method: Position sizing method
            rules: Position sizing rules
            run_id: Current run ID for logging

        Returns:
            List of dicts with: {symbol, decision, position, priority_score}
            Sorted by priority (highest conviction first)
        """
        if not buy_decisions:
            return []

        print("\n  Phase 1: Calculating all positions with priority ordering...")
        self._log_event(run_id, f"Phase 1: Calculating positions for {len(buy_decisions)} buy decisions")

        # Calculate positions for all decisions
        positions_data = []
        for decision in buy_decisions:
            symbol = decision['symbol']
            conviction = decision.get('consensus_score', 50)

            try:
                position = self.position_sizer.calculate_position(
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    conviction_score=conviction,
                    method=method,
                    rules=rules,
                    other_buys=[d for d in buy_decisions if d != decision]
                )

                # Calculate priority score
                # Primary: conviction score (higher = more priority)
                # Secondary: position size (smaller = more priority for diversification)
                priority_score = conviction - (position.position_pct * 0.1)

                positions_data.append({
                    'symbol': symbol,
                    'decision': decision,
                    'position': position,
                    'conviction': conviction,
                    'priority_score': priority_score
                })

                print(f"    {symbol}: {position.shares} shares (${position.estimated_value:,.2f}), "
                      f"conviction={conviction:.0f}, priority={priority_score:.1f}")

            except Exception as e:
                logger.error(f"Failed to calculate position for {symbol}: {e}")
                continue

        # Sort by priority (highest first)
        positions_data.sort(key=lambda x: x['priority_score'], reverse=True)

        # Calculate total cash needed
        total_requested = sum(p['position'].estimated_value for p in positions_data)
        print(f"\n  Total requested: ${total_requested:,.2f}, Available: ${available_cash:,.2f}")
        self._log_event(run_id, f"Total requested: ${total_requested:,.2f}, Available: ${available_cash:,.2f}")

        # If we exceed available cash, need to rebalance
        if total_requested > available_cash:
            print(f"  ⚠ Insufficient cash! Selecting highest priority positions...")
            self._log_event(run_id, f"Insufficient cash. Prioritizing highest conviction positions.")

            # Select positions that fit in budget (greedy by priority)
            selected = []
            remaining_cash = available_cash

            for pos_data in positions_data:
                if pos_data['position'].estimated_value <= remaining_cash:
                    selected.append(pos_data)
                    remaining_cash -= pos_data['position'].estimated_value
                    print(f"    ✓ Selected {pos_data['symbol']} (${pos_data['position'].estimated_value:,.2f})")
                else:
                    print(f"    ✗ Skipped {pos_data['symbol']} (${pos_data['position'].estimated_value:,.2f}) - insufficient cash")
                    self._log_event(run_id, f"Skipped {pos_data['symbol']} - insufficient cash")

            positions_data = selected
            print(f"  Selected {len(positions_data)}/{len(buy_decisions)} positions, "
                  f"using ${available_cash - remaining_cash:,.2f} of ${available_cash:,.2f}")
            self._log_event(run_id, f"Selected {len(positions_data)} positions totaling ${available_cash - remaining_cash:,.2f}")
        else:
            print(f"  ✓ All positions fit within available cash")

        return positions_data

    def _execute_trades(
        self,
        buy_decisions: List[Dict[str, Any]],
        exits: List[ExitSignal],
        strategy: Dict[str, Any],
        run_id: int
    ) -> int:
        """Execute buy and sell trades with two-phase cash tracking."""
        import portfolio_service

        portfolio_id = strategy['portfolio_id']
        position_rules = strategy.get('position_sizing', {})
        method = position_rules.get('method', 'equal_weight')

        trades_executed = 0
        
        # Check market status
        is_market_open = portfolio_service.is_market_open()
        
        # If market is closed, we need user_id to create alerts
        user_id = None
        if not is_market_open:
            # We need to fetch the portfolio to get the user_id
            try:
                portfolio = self.db.get_portfolio(portfolio_id)
                if portfolio:
                    user_id = portfolio.get('user_id')
            except Exception as e:
                logger.error(f"Failed to fetch portfolio {portfolio_id} for user lookup: {e}")

            if not user_id:
                logger.error(f"Could not determine user_id for portfolio {portfolio_id}, cannot queue off-hours trades.")
                # We can either return or attempt to process (which will fail for trades). 
                # Let's proceed but warn.
        
        if not is_market_open:
            print(f"   Market is closed. Queuing trades for next open via Alerts.")
            self._log_event(run_id, "Market closed. Queuing transactions for next market open.")

        # Execute sells first (to free up cash)
        print("\n  Executing SELL orders...")
        cash_freed = 0.0
        for exit_signal in exits:
            try:
                if is_market_open:
                    result = portfolio_service.execute_trade(
                        portfolio_id=portfolio_id,
                        symbol=exit_signal.symbol,
                        transaction_type='SELL',
                        quantity=exit_signal.quantity,
                        note=exit_signal.reason,
                        position_type='exit',
                        db=self.db
                    )
                    if result.get('success'):
                        trades_executed += 1
                        cash_freed += exit_signal.current_value
                        self._log_event(run_id, f"SELL {exit_signal.symbol}: {exit_signal.reason}")
                        print(f"    ✓ SOLD {exit_signal.symbol}: {exit_signal.quantity} shares "
                              f"(freed ${exit_signal.current_value:,.2f})")
                elif user_id:
                    alert_id = self.db.create_alert(
                        user_id=user_id,
                        symbol=exit_signal.symbol,
                        condition_type='price_above',
                        condition_params={'threshold': 0},
                        condition_description=f"Strategy Queue: Sell {exit_signal.quantity} {exit_signal.symbol} at Open",
                        action_type='market_sell',
                        action_payload={'quantity': exit_signal.quantity},
                        portfolio_id=portfolio_id,
                        action_note=f"Queued Strategy Sell (Run {run_id}): {exit_signal.reason}"
                    )
                    logger.info(f"Queued sell alert {alert_id} for {exit_signal.symbol}")
                    self._log_event(run_id, f"QUEUED SELL {exit_signal.symbol}: {exit_signal.quantity} shares (Alert {alert_id})")
                    trades_executed += 1

            except Exception as e:
                logger.error(f"Failed to execute/queue sell for {exit_signal.symbol}: {e}")
                print(f"    ✗ Failed to sell {exit_signal.symbol}: {e}")

        # Get current cash after sells
        summary = self.db.get_portfolio_summary(portfolio_id, use_live_prices=False)
        available_cash = summary.get('cash', 0) if summary else 0
        print(f"\n  Available cash after sells: ${available_cash:,.2f} "
              f"(freed ${cash_freed:,.2f} from {len(exits)} sells)")
        self._log_event(run_id, f"Available cash: ${available_cash:,.2f}")

        # Phase 1: Calculate all positions with priority ordering
        prioritized_positions = self._calculate_all_positions(
            buy_decisions=buy_decisions,
            portfolio_id=portfolio_id,
            available_cash=available_cash,
            method=method,
            rules=position_rules,
            run_id=run_id
        )

        # Phase 2: Execute buys in priority order with real-time cash tracking
        if prioritized_positions:
            print(f"\n  Phase 2: Executing {len(prioritized_positions)} BUY orders in priority order...")
            self._log_event(run_id, f"Phase 2: Executing {len(prioritized_positions)} buys")

            running_cash = available_cash

            for pos_data in prioritized_positions:
                symbol = pos_data['symbol']
                position = pos_data['position']
                decision = pos_data['decision']

                print(f"\n  Executing {symbol}:")
                print(f"    Shares: {position.shares}")
                print(f"    Value: ${position.estimated_value:,.2f}")
                print(f"    Cash before: ${running_cash:,.2f}")

                if position.shares > 0:
                    # Get position type from decision
                    pos_type = decision.get('position_type', 'new')

                    if is_market_open:
                        result = portfolio_service.execute_trade(
                            portfolio_id=portfolio_id,
                            symbol=symbol,
                            transaction_type='BUY',
                            quantity=position.shares,
                            note=f"Strategy buy ({pos_type}): {decision.get('consensus_reasoning', '')}",
                            position_type=pos_type,
                            db=self.db
                        )
                        if result.get('success'):
                            trades_executed += 1
                            running_cash -= position.estimated_value
                            self._log_event(
                                run_id,
                                f"BUY {symbol}: {position.shares} shares, ${position.estimated_value:,.2f} spent, ${running_cash:,.2f} remaining"
                            )
                            print(f"    ✓ Trade executed successfully")
                            print(f"    Cash after: ${running_cash:,.2f}")
                        else:
                            error = result.get('error', 'Unknown error')
                            print(f"    ✗ Trade failed: {error}")
                            logger.warning(f"Trade execution failed for {symbol}: {error}")
                            self._log_event(run_id, f"BUY {symbol} FAILED: {error}")
                    elif user_id:
                        alert_id = self.db.create_alert(
                            user_id=user_id,
                            symbol=symbol,
                            condition_type='price_above',
                            condition_params={'threshold': 0},
                            condition_description=f"Strategy Queue: Buy {position.shares} {symbol} at Open",
                            action_type='market_buy',
                            action_payload={'quantity': position.shares},
                            portfolio_id=portfolio_id,
                            action_note=f"Queued Strategy Buy (Run {run_id}): {decision.get('consensus_reasoning', '')}"
                        )
                        logger.info(f"Queued buy alert {alert_id} for {symbol}")
                        self._log_event(
                            run_id,
                            f"QUEUED BUY {symbol}: {position.shares} shares (Alert {alert_id})"
                        )
                        print(f"    ✓ Trade queued for market open (Alert {alert_id})")
                        trades_executed += 1
                        running_cash -= position.estimated_value
                else:
                    print(f"    ⚠ Skipping trade: {position.reasoning}")
                    logger.info(f"Skipping {symbol} buy: {position.reasoning}")
        else:
            print("\n  No buy positions to execute")

        return trades_executed
