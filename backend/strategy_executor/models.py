# ABOUTME: Data classes for strategy execution results
# ABOUTME: Defines ConsensusResult, PositionSize, and ExitSignal

from dataclasses import dataclass
from typing import Optional, Dict, Any


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
    target_value: Optional[float] = None
    drift: Optional[float] = None
    price_used: Optional[float] = None


@dataclass
class ExitSignal:
    """Signal to exit a position."""
    symbol: str
    quantity: int
    reason: str
    current_value: Optional[float] = None  # None means: compute from price at execution time
    gain_pct: Optional[float] = None
    exit_type: str = 'full'  # 'full' = entire position; 'trim' = partial sell


@dataclass
class TargetAllocation:
    """Target allocation for a single stock."""
    symbol: str
    conviction: float
    target_value: float
    current_value: float
    drift: float  # target - current
    price: float
    source_data: Optional[Dict[str, Any]] = None
    quantity: int = 0
