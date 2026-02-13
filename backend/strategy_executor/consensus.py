# ABOUTME: Implements consensus modes for multi-character investment decisions
# ABOUTME: Supports both_agree, weighted_confidence, and veto_power modes

from typing import Dict, Any
from strategy_executor.models import ConsensusResult


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

        # No veto - use the strategy's consensus threshold
        avg_score = (lynch_score + buffett_score) / 2
        threshold = config.get('threshold', 70)
        verdict = 'BUY' if avg_score >= threshold else 'WATCH'

        return ConsensusResult(
            verdict=verdict,
            score=avg_score,
            reasoning=f"No veto: Lynch {lynch_score:.0f}, Buffett {buffett_score:.0f}, avg {avg_score:.1f}",
            lynch_contributed=True,
            buffett_contributed=True
        )
