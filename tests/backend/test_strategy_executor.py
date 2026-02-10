# ABOUTME: Tests for the autonomous investment strategy executor
# ABOUTME: Covers ConsensusEngine, PositionSizer, ExitConditionChecker, and BenchmarkTracker

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import date

# Import the components we're testing
from strategy_executor import (
    ConsensusEngine,
    ConsensusResult,
    PositionSizer,
    PositionSize,
    ExitConditionChecker,
    ExitSignal,
    ConditionEvaluator,
)


class TestConsensusEngine:
    """Tests for the three consensus modes."""

    @pytest.fixture
    def engine(self):
        return ConsensusEngine()

    # =========================================
    # both_agree mode tests
    # =========================================

    def test_both_agree_approves_when_both_above_threshold(self, engine):
        """When both Lynch and Buffett score >= 70 and BUY, should approve."""
        lynch = {'score': 75, 'status': 'BUY'}
        buffett = {'score': 80, 'status': 'BUY'}
        config = {'min_score': 70, 'buy_statuses': ['STRONG_BUY', 'BUY']}

        result = engine.both_agree(lynch, buffett, config)

        assert result.verdict == 'BUY'
        assert result.score == 77.5  # Average
        assert result.lynch_contributed is True
        assert result.buffett_contributed is True

    def test_both_agree_rejects_when_lynch_below_threshold(self, engine):
        """When Lynch < 70, should reject even if Buffett approves."""
        lynch = {'score': 65, 'status': 'HOLD'}
        buffett = {'score': 85, 'status': 'STRONG_BUY'}
        config = {'min_score': 70}

        result = engine.both_agree(lynch, buffett, config)

        assert result.verdict == 'AVOID'
        assert result.lynch_contributed is False
        assert result.buffett_contributed is True

    def test_both_agree_rejects_when_buffett_below_threshold(self, engine):
        """When Buffett < 70, should reject even if Lynch approves."""
        lynch = {'score': 85, 'status': 'STRONG_BUY'}
        buffett = {'score': 60, 'status': 'HOLD'}
        config = {'min_score': 70}

        result = engine.both_agree(lynch, buffett, config)

        assert result.verdict == 'AVOID'
        assert result.lynch_contributed is True
        assert result.buffett_contributed is False

    def test_both_agree_requires_buy_status(self, engine):
        """Even with high scores, status must be BUY/STRONG_BUY."""
        lynch = {'score': 85, 'status': 'HOLD'}  # High score but HOLD
        buffett = {'score': 80, 'status': 'BUY'}
        config = {'min_score': 70, 'buy_statuses': ['STRONG_BUY', 'BUY']}

        result = engine.both_agree(lynch, buffett, config)

        assert result.verdict == 'AVOID'

    # =========================================
    # weighted_confidence mode tests
    # =========================================

    def test_weighted_confidence_equal_weights(self, engine):
        """With equal weights, should average the scores."""
        lynch = {'score': 80, 'status': 'BUY'}
        buffett = {'score': 60, 'status': 'HOLD'}
        config = {'lynch_weight': 0.5, 'buffett_weight': 0.5, 'threshold': 70}

        result = engine.weighted_confidence(lynch, buffett, config)

        assert result.score == 70.0  # (80 + 60) / 2
        assert result.verdict == 'WATCH'  # 70 meets threshold but < 80

    def test_weighted_confidence_buy_above_80(self, engine):
        """Score >= 80 should result in BUY."""
        lynch = {'score': 90, 'status': 'STRONG_BUY'}
        buffett = {'score': 80, 'status': 'BUY'}
        config = {'lynch_weight': 0.5, 'buffett_weight': 0.5, 'threshold': 70}

        result = engine.weighted_confidence(lynch, buffett, config)

        assert result.score == 85.0
        assert result.verdict == 'BUY'

    def test_weighted_confidence_custom_weights(self, engine):
        """Custom weights should be applied correctly."""
        lynch = {'score': 100, 'status': 'STRONG_BUY'}
        buffett = {'score': 50, 'status': 'CAUTION'}
        # Lynch 75%, Buffett 25%
        config = {'lynch_weight': 0.75, 'buffett_weight': 0.25, 'threshold': 70}

        result = engine.weighted_confidence(lynch, buffett, config)

        assert result.score == 87.5  # (100 * 0.75) + (50 * 0.25)
        assert result.verdict == 'BUY'

    def test_weighted_confidence_avoid_below_threshold(self, engine):
        """Score below threshold should result in AVOID."""
        lynch = {'score': 50, 'status': 'CAUTION'}
        buffett = {'score': 60, 'status': 'HOLD'}
        config = {'threshold': 70}

        result = engine.weighted_confidence(lynch, buffett, config)

        assert result.score == 55.0
        assert result.verdict == 'AVOID'

    # =========================================
    # veto_power mode tests
    # =========================================

    def test_veto_power_lynch_vetos_with_avoid_status(self, engine):
        """Lynch with AVOID status should veto the trade."""
        lynch = {'score': 45, 'status': 'AVOID'}
        buffett = {'score': 90, 'status': 'STRONG_BUY'}
        config = {'veto_statuses': ['AVOID', 'CAUTION'], 'veto_score_threshold': 30}

        result = engine.veto_power(lynch, buffett, config)

        assert result.verdict == 'VETO'
        assert 'Lynch' in result.reasoning
        assert result.lynch_contributed is False
        assert result.buffett_contributed is True

    def test_veto_power_buffett_vetos_with_low_score(self, engine):
        """Buffett with score below threshold should veto."""
        lynch = {'score': 80, 'status': 'BUY'}
        buffett = {'score': 25, 'status': 'HOLD'}  # Below 30 threshold
        config = {'veto_statuses': ['AVOID'], 'veto_score_threshold': 30}

        result = engine.veto_power(lynch, buffett, config)

        assert result.verdict == 'VETO'
        assert 'Buffett' in result.reasoning

    def test_veto_power_no_veto_approves(self, engine):
        """Without veto conditions, should use average score."""
        lynch = {'score': 75, 'status': 'BUY'}
        buffett = {'score': 70, 'status': 'BUY'}
        config = {'veto_statuses': ['AVOID'], 'veto_score_threshold': 30}

        result = engine.veto_power(lynch, buffett, config)

        assert result.verdict == 'BUY'
        assert result.score == 72.5

    def test_veto_power_double_veto(self, engine):
        """Both characters vetoing should be reflected in reasoning."""
        lynch = {'score': 20, 'status': 'AVOID'}
        buffett = {'score': 25, 'status': 'CAUTION'}
        config = {'veto_statuses': ['AVOID', 'CAUTION'], 'veto_score_threshold': 30}

        result = engine.veto_power(lynch, buffett, config)

        assert result.verdict == 'VETO'
        assert 'Lynch' in result.reasoning
        assert 'Buffett' in result.reasoning

    # =========================================
    # evaluate dispatcher tests
    # =========================================

    def test_evaluate_dispatches_to_both_agree(self, engine):
        """evaluate() should dispatch to both_agree for that mode."""
        lynch = {'score': 80, 'status': 'BUY'}
        buffett = {'score': 80, 'status': 'BUY'}
        config = {}

        result = engine.evaluate(lynch, buffett, 'both_agree', config)

        assert result.verdict == 'BUY'

    def test_evaluate_dispatches_to_weighted_confidence(self, engine):
        """evaluate() should dispatch to weighted_confidence for that mode."""
        lynch = {'score': 85, 'status': 'BUY'}
        buffett = {'score': 85, 'status': 'BUY'}
        config = {}

        result = engine.evaluate(lynch, buffett, 'weighted_confidence', config)

        assert result.verdict == 'BUY'

    def test_evaluate_dispatches_to_veto_power(self, engine):
        """evaluate() should dispatch to veto_power for that mode."""
        lynch = {'score': 80, 'status': 'BUY'}
        buffett = {'score': 80, 'status': 'BUY'}
        config = {}

        result = engine.evaluate(lynch, buffett, 'veto_power', config)

        assert result.verdict == 'BUY'

    def test_evaluate_raises_for_unknown_mode(self, engine):
        """evaluate() should raise for unknown consensus mode."""
        with pytest.raises(ValueError, match="Unknown consensus mode"):
            engine.evaluate({}, {}, 'invalid_mode', {})


class TestPositionSizer:
    """Tests for position sizing logic."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        # Default portfolio summary
        db.get_portfolio_summary.return_value = {
            'total_value': 100000,
            'cash': 50000,
            'holdings': {}
        }
        # Default price
        conn = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = (100.0,)  # $100 per share
        conn.cursor.return_value = cursor
        db.get_connection.return_value = conn
        db.return_connection = Mock()
        return db

    @pytest.fixture
    def sizer(self, mock_db):
        return PositionSizer(mock_db)

    def test_equal_weight_single_buy(self, sizer, mock_db):
        """Single buy should use all available cash."""
        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=80,
            method='equal_weight',
            rules={'max_position_pct': 50},
            other_buys=[],
            current_price=100.0
        )

        # With $50k cash and 1 buy, should use ~$50k
        # Max position is 50% of $100k = $50k
        assert result.shares == 500  # $50k / $100 per share
        assert result.estimated_value == 50000

    def test_equal_weight_multiple_buys(self, sizer, mock_db):
        """Multiple buys should split cash equally."""
        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=80,
            method='equal_weight',
            rules={'max_position_pct': 50},
            other_buys=[{'symbol': 'MSFT'}, {'symbol': 'GOOGL'}],  # 2 other buys
            current_price=100.0
        )

        # With $50k cash and 3 buys, each gets ~$16,666
        # But capped by max_position_pct = 50% = $50k
        expected_value = 50000 / 3  # ~$16,666
        assert result.shares == int(expected_value / 100)

    def test_conviction_weighted_high_conviction(self, sizer, mock_db):
        """Higher conviction should get larger allocation."""
        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=90,
            method='conviction_weighted',
            rules={'max_position_pct': 50},
            other_buys=[{'symbol': 'MSFT', 'conviction': 30}],  # Low conviction competitor
            current_price=100.0
        )

        # AAPL has 90/(90+30) = 75% of conviction
        # Should get 75% of $50k = $37,500
        expected = 50000 * (90 / 120)  # ~$37,500
        assert result.shares == int(expected / 100)

    def test_fixed_pct_sizing(self, sizer, mock_db):
        """Fixed percentage should allocate that % of portfolio."""
        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=80,
            method='fixed_pct',
            rules={'fixed_position_pct': 10, 'max_position_pct': 50},
            other_buys=[],
            current_price=100.0
        )

        # 10% of $100k = $10k
        assert result.shares == 100
        assert result.estimated_value == 10000

    def test_kelly_criterion_high_conviction(self, sizer, mock_db):
        """Kelly with high conviction should allocate more."""
        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=90,
            method='kelly',
            rules={'kelly_fraction': 0.25, 'max_position_pct': 50},
            other_buys=[],
            current_price=100.0
        )

        # With 90% conviction and quarter-Kelly:
        # p = 0.9, q = 0.1, b = 1
        # kelly_pct = (1 * 0.9 - 0.1) / 1 = 0.8
        # safe_pct = 0.8 * 0.25 = 0.2 (20%)
        # But capped at 25% by Kelly logic
        assert result.shares > 0

    def test_respects_max_position_pct(self, sizer, mock_db):
        """Should not exceed max_position_pct even with high conviction."""
        # Set up a portfolio with $100k cash
        mock_db.get_portfolio_summary.return_value = {
            'total_value': 100000,
            'cash': 100000,
            'holdings': {}
        }

        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=100,
            method='equal_weight',
            rules={'max_position_pct': 5},  # Only 5%
            other_buys=[],
            current_price=100.0
        )

        # Max is 5% of $100k = $5k
        assert result.estimated_value <= 5000

    def test_existing_position_limits_additional(self, sizer, mock_db):
        """If already holding shares, should only add up to max."""
        mock_db.get_portfolio_summary.return_value = {
            'total_value': 100000,
            'cash': 50000,
            'holdings': {'AAPL': 30}  # Already holding 30 shares = $3000
        }

        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=80,
            method='fixed_pct',
            rules={'fixed_position_pct': 5, 'max_position_pct': 5},  # Max $5k total
            other_buys=[],
            current_price=100.0
        )

        # Already at $3k, max is $5k, so can only add $2k = 20 shares
        assert result.shares == 20

    def test_at_max_position_returns_zero(self, sizer, mock_db):
        """If already at max position, should return 0 shares."""
        mock_db.get_portfolio_summary.return_value = {
            'total_value': 100000,
            'cash': 50000,
            'holdings': {'AAPL': 50}  # 50 shares = $5000 = 5% already
        }

        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=80,
            method='fixed_pct',
            rules={'fixed_position_pct': 5, 'max_position_pct': 5},
            other_buys=[],
            current_price=100.0
        )

        assert result.shares == 0
        assert 'max position' in result.reasoning.lower()

    def test_minimum_position_value(self, sizer, mock_db):
        """If calculated value < min, either bump to min or skip."""
        mock_db.get_portfolio_summary.return_value = {
            'total_value': 100000,
            'cash': 500,  # Low cash
            'holdings': {}
        }

        result = sizer.calculate_position(
            portfolio_id=1,
            symbol='AAPL',
            conviction_score=80,
            method='equal_weight',
            rules={'min_position_value': 1000, 'max_position_pct': 50},
            other_buys=[],
            current_price=100.0
        )

        # Only $500 cash, min is $1000 - should skip
        assert result.shares == 0


class TestExitConditionChecker:
    """Tests for exit condition checking."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        return db

    @pytest.fixture
    def checker(self, mock_db):
        return ExitConditionChecker(mock_db)

    def test_profit_target_triggers_exit(self, checker, mock_db):
        """Position up 50% should trigger profit target exit."""
        mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': 'AAPL',
            'quantity': 100,
            'total_cost': 10000,
            'current_value': 15000  # Up 50%
        }]

        exits = checker.check_exits(
            portfolio_id=1,
            exit_conditions={'profit_target_pct': 50}
        )

        assert len(exits) == 1
        assert exits[0].symbol == 'AAPL'
        assert 'Profit target' in exits[0].reason

    def test_stop_loss_triggers_exit(self, checker, mock_db):
        """Position down 25% should trigger stop loss exit."""
        mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': 'AAPL',
            'quantity': 100,
            'total_cost': 10000,
            'current_value': 7500  # Down 25%
        }]

        exits = checker.check_exits(
            portfolio_id=1,
            exit_conditions={'stop_loss_pct': -20}
        )

        assert len(exits) == 1
        assert 'Stop loss' in exits[0].reason

    def test_no_exit_within_bounds(self, checker, mock_db):
        """Position within profit/loss bounds should not exit."""
        mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': 'AAPL',
            'quantity': 100,
            'total_cost': 10000,
            'current_value': 11000  # Up 10%
        }]

        exits = checker.check_exits(
            portfolio_id=1,
            exit_conditions={'profit_target_pct': 50, 'stop_loss_pct': -20}
        )

        assert len(exits) == 0

    def test_multiple_positions_checked(self, checker, mock_db):
        """Should check all positions and return appropriate exits."""
        mock_db.get_portfolio_holdings_detailed.return_value = [
            {'symbol': 'AAPL', 'quantity': 100, 'total_cost': 10000, 'current_value': 16000},  # +60%
            {'symbol': 'MSFT', 'quantity': 50, 'total_cost': 5000, 'current_value': 5500},    # +10%
            {'symbol': 'GOOGL', 'quantity': 20, 'total_cost': 4000, 'current_value': 3000},   # -25%
        ]

        exits = checker.check_exits(
            portfolio_id=1,
            exit_conditions={'profit_target_pct': 50, 'stop_loss_pct': -20}
        )

        symbols = [e.symbol for e in exits]
        assert 'AAPL' in symbols  # Profit target
        assert 'GOOGL' in symbols  # Stop loss
        assert 'MSFT' not in symbols  # In bounds

    def test_empty_exit_conditions(self, checker, mock_db):
        """Empty exit conditions should return no exits."""
        mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': 'AAPL',
            'quantity': 100,
            'total_cost': 10000,
            'current_value': 20000  # Up 100%
        }]

        exits = checker.check_exits(portfolio_id=1, exit_conditions={})

        assert len(exits) == 0

    def test_score_degradation_triggers_exit(self, checker, mock_db):
        """Low Lynch/Buffett score should trigger exit."""
        mock_db.get_portfolio_holdings_detailed.return_value = [{
            'symbol': 'AAPL',
            'quantity': 100,
            'total_cost': 10000,
            'current_value': 11000
        }]

        def mock_scoring(symbol):
            return {'lynch_score': 35, 'buffett_score': 60}  # Lynch below 40

        exits = checker.check_exits(
            portfolio_id=1,
            exit_conditions={'score_degradation': {'lynch_below': 40, 'buffett_below': 40}},
            scoring_func=mock_scoring
        )

        assert len(exits) == 1
        assert 'Lynch score degraded' in exits[0].reason


class TestStrategyExecutorIntegration:
    """Integration tests for the full strategy execution pipeline."""

    @pytest.fixture
    def mock_db(self):
        """Set up a mock database with all required methods."""
        db = Mock()

        # Strategy lookup
        db.get_strategy.return_value = {
            'id': 1,
            'portfolio_id': 1,
            'enabled': True,
            'conditions': {
                'universe': {'filters': []},
                'scoring_requirements': [
                    {'character': 'lynch', 'min_score': 60},
                    {'character': 'buffett', 'min_score': 60}
                ],
                'require_thesis': True,
                'thesis_verdict_required': ['BUY']
            },
            'consensus_mode': 'both_agree',
            'consensus_threshold': 70,
            'position_sizing': {'method': 'equal_weight', 'max_position_pct': 10},
            'exit_conditions': {'profit_target_pct': 50, 'stop_loss_pct': -20}
        }

        # Run tracking
        db.create_strategy_run.return_value = 1
        db.update_strategy_run = Mock()
        db.append_to_run_log = Mock()
        db.create_strategy_decision = Mock()

        # Portfolio
        db.get_portfolio_summary.return_value = {
            'total_value': 100000,
            'cash': 50000,
            'holdings': {}
        }
        db.get_portfolio_holdings.return_value = {}
        db.get_portfolio_holdings_detailed.return_value = []

        # Benchmark
        db.get_benchmark_snapshot.return_value = {'spy_price': 500.0}
        db.save_benchmark_snapshot = Mock()
        db.get_strategy_inception_data.return_value = {
            'portfolio_value': 100000,
            'spy_price': 480.0
        }
        db.save_strategy_performance = Mock()

        # Stock data for screener
        conn = Mock()
        cursor = Mock()
        cursor.fetchall.return_value = [('AAPL',), ('MSFT',)]
        cursor.fetchone.return_value = (150.0,)  # Price
        conn.cursor.return_value = cursor
        db.get_connection.return_value = conn
        db.return_connection = Mock()

        # Stock metrics for thesis
        db.get_stock_metrics.return_value = {
            'symbol': 'AAPL',
            'price': 150.0,
            'pe_ratio': 25,
            'market_cap': 2500000000000
        }
        db.get_earnings_history.return_value = []

        return db

    @pytest.fixture
    def mock_lynch_criteria(self):
        """Mock Lynch criteria that returns predictable scores."""
        import pandas as pd

        criteria = Mock()

        def evaluate(symbol, character_id='lynch'):
            if character_id == 'lynch':
                return {'overall_score': 75, 'overall_status': 'BUY'}
            else:  # buffett
                return {'overall_score': 80, 'overall_status': 'BUY'}

        criteria.evaluate_stock = Mock(side_effect=evaluate)

        def evaluate_batch(df, config):
            """Return scored DataFrame matching production evaluate_batch output."""
            result = df[['symbol']].copy()
            result['overall_score'] = 75.0
            result['overall_status'] = 'BUY'
            return result

        criteria.evaluate_batch = Mock(side_effect=evaluate_batch)
        return criteria

    @pytest.fixture
    def mock_analyst(self):
        """Mock analyst that generates predictable theses."""
        analyst = Mock()

        def generate(*args, **kwargs):
            yield "## Bottom Line\n**BUY** - Strong fundamentals and growth potential."

        analyst.get_or_generate_analysis = Mock(side_effect=generate)
        return analyst

    def _make_stock_vectors_mock(self):
        """Create a mock StockVectors that returns a DataFrame with AAPL and MSFT."""
        import pandas as pd
        mock_vectors_class = MagicMock()
        mock_vectors_instance = MagicMock()
        mock_vectors_instance.load_vectors.return_value = pd.DataFrame({
            'symbol': ['AAPL', 'MSFT'],
            'price': [150.0, 300.0],
            'peg_ratio': [1.5, 1.2],
            'debt_to_equity': [0.5, 0.3],
            'institutional_ownership': [0.6, 0.7],
        })
        mock_vectors_class.return_value = mock_vectors_instance
        return mock_vectors_class

    def test_full_pipeline_buy_decision(self, mock_db, mock_lynch_criteria, mock_analyst):
        """Test full pipeline from screening through trade execution."""
        from strategy_executor import StrategyExecutor
        import sys

        # Patch portfolio_service (imported locally in _execute_trades)
        with patch.dict('sys.modules', {'portfolio_service': MagicMock()}):
            import sys
            mock_portfolio = sys.modules['portfolio_service']
            mock_portfolio.execute_trade.return_value = {'success': True}

            # Patch yfinance for benchmark
            with patch.dict('sys.modules', {'yfinance': MagicMock()}):
                mock_yf = sys.modules['yfinance']
                mock_yf.Ticker.return_value.fast_info = {'lastPrice': 500.0}

                # Patch StockVectors for vectorized scoring
                with patch('stock_vectors.StockVectors', self._make_stock_vectors_mock()):
                    executor = StrategyExecutor(
                        db=mock_db,
                        analyst=mock_analyst,
                        lynch_criteria=mock_lynch_criteria
                    )

                    result = executor.execute_strategy(strategy_id=1)

        # Verify pipeline completed
        assert result['status'] == 'completed'
        assert result['stocks_screened'] == 2
        assert result['stocks_scored'] > 0

        # Verify batch scoring was called (vectorized path)
        assert mock_lynch_criteria.evaluate_batch.call_count >= 2

        # Verify thesis was generated
        assert mock_analyst.get_or_generate_analysis.call_count > 0

        # Verify decisions were recorded
        assert mock_db.create_strategy_decision.call_count > 0

    def test_thesis_verdict_filtering(self, mock_db, mock_lynch_criteria):
        """Test that stocks with wrong thesis verdict are filtered out."""
        from strategy_executor import StrategyExecutor
        import sys

        # Analyst that returns AVOID verdict
        mock_analyst = Mock()
        mock_analyst.get_or_generate_analysis = Mock(
            return_value=iter(["## Bottom Line\n**AVOID** - Too risky."])
        )

        with patch.dict('sys.modules', {'portfolio_service': MagicMock()}):
            mock_portfolio = sys.modules['portfolio_service']
            mock_portfolio.execute_trade.return_value = {'success': True}

            with patch.dict('sys.modules', {'yfinance': MagicMock()}):
                mock_yf = sys.modules['yfinance']
                mock_yf.Ticker.return_value.fast_info = {'lastPrice': 500.0}

                # Patch StockVectors for vectorized scoring
                with patch('stock_vectors.StockVectors', self._make_stock_vectors_mock()):
                    executor = StrategyExecutor(
                        db=mock_db,
                        analyst=mock_analyst,
                        lynch_criteria=mock_lynch_criteria
                    )

                    result = executor.execute_strategy(strategy_id=1)

        # No trades should be executed because thesis verdict is AVOID, not BUY
        assert result['trades_executed'] == 0

    def test_disabled_strategy_skipped(self, mock_db, mock_lynch_criteria, mock_analyst):
        """Disabled strategies should be skipped."""
        from strategy_executor import StrategyExecutor

        mock_db.get_strategy.return_value['enabled'] = False

        executor = StrategyExecutor(
            db=mock_db,
            analyst=mock_analyst,
            lynch_criteria=mock_lynch_criteria
        )

        result = executor.execute_strategy(strategy_id=1)

        assert result['status'] == 'skipped'
        assert 'disabled' in result['reason'].lower()


class TestConditionEvaluator:
    """Tests for screening condition evaluation."""

    @pytest.fixture
    def mock_db(self):
        db = Mock()
        return db

    @pytest.fixture
    def evaluator(self, mock_db):
        return ConditionEvaluator(mock_db)

    def test_empty_filters_returns_all_symbols(self, evaluator, mock_db):
        """No filters should return all screened symbols."""
        # Mock getting all symbols
        conn = Mock()
        cursor = Mock()
        cursor.fetchall.return_value = [('AAPL',), ('MSFT',), ('GOOGL',)]
        conn.cursor.return_value = cursor
        mock_db.get_connection.return_value = conn
        mock_db.return_connection = Mock()

        symbols = evaluator.filter_universe({'universe': {'filters': []}})

        assert 'AAPL' in symbols
        assert 'MSFT' in symbols
        assert 'GOOGL' in symbols

    def test_price_filter_applied(self, evaluator, mock_db):
        """Price filter should narrow down results."""
        conn = Mock()
        cursor = Mock()

        # First call returns all symbols
        # Second call returns filtered symbols
        cursor.fetchall.side_effect = [
            [('AAPL',), ('MSFT',), ('GOOGL',)],  # All symbols
            [('AAPL',), ('GOOGL',)]  # After price filter
        ]
        conn.cursor.return_value = cursor
        mock_db.get_connection.return_value = conn
        mock_db.return_connection = Mock()

        conditions = {
            'universe': {
                'filters': [
                    {'field': 'price', 'operator': '<=', 'value': 200}
                ]
            }
        }

        symbols = evaluator.filter_universe(conditions)

        # Should have called filter query
        assert len(symbols) == 2
