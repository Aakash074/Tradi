"""Russian Doll nested drawdown circuit breakers."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RussianDollState:
    position_size_multiplier: float = 1.0
    max_positions: int = 4
    trading_halted: bool = False
    halt_reason: str = ""


class RussianDollRisk:
    """Nested circuit breakers — harder stops as drawdown increases."""

    def __init__(self, halt_at: float = 0.25):
        self.halt_at = halt_at
        self.state = RussianDollState()

    def check_drawdown(self, current_dd: float) -> bool:
        if current_dd > self.halt_at:
            self.state.trading_halted = True
            self.state.halt_reason = f"CRITICAL: Trading halted at {self.halt_at * 100:.0f}% drawdown"
            self.state.position_size_multiplier = 0.0
            logger.warning(self.state.halt_reason)
            return False

        self.state.trading_halted = False
        self.state.halt_reason = ""

        if current_dd > 0.12:
            self.state.position_size_multiplier = 0.25
            self.state.max_positions = 2
        elif current_dd > 0.08:
            self.state.position_size_multiplier = 0.5
            self.state.max_positions = 3
        else:
            self.state.position_size_multiplier = 1.0
            self.state.max_positions = 4

        return True

    def get_status(self) -> dict:
        return {
            "position_size_multiplier": self.state.position_size_multiplier,
            "max_positions": self.state.max_positions,
            "trading_halted": self.state.trading_halted,
            "halt_reason": self.state.halt_reason,
            "halt_at_pct": self.halt_at * 100,
        }
