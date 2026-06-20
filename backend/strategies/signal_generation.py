"""Signal scoring and selection."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TradeSignal:
    strategy: str
    action: str  # BUY, SELL, HOLD, ENTER_LP
    token: str
    token_to: Optional[str] = None
    confidence: float = 0.0
    expected_return: float = 0.0
    risk: float = 1.0
    position_size_pct: float = 0.10
    reason: str = ""
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.06

    @property
    def opportunity_score(self) -> float:
        if self.risk <= 0:
            return 0
        return (self.expected_return * self.confidence) / self.risk


def select_best_signal(signals: list[TradeSignal], threshold: float = 0.01) -> Optional[TradeSignal]:
    if not signals:
        return None
    best = max(signals, key=lambda s: s.opportunity_score)
    if best.opportunity_score < threshold:
        return None
    return best
