"""Risk management, circuit breakers, anti-churn, and tournament sizing."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import get_settings
from strategies.signal_generation import TradeSignal

logger = logging.getLogger(__name__)

RISK_LAYERS = {
    "soft_halt": 0.20,    # Pause 24h, reduce sizes 50%
    "medium_halt": 0.25,  # Pause 48h, review required
    "hard_halt": 0.28,    # Liquidate all, halt until manual reset
    "dq_line": 0.30,      # Game over (competition rule)
}

MIN_REENTRY_HOURS = 4


@dataclass
class CircuitBreaker:
    breaker_type: str
    is_active: bool = False
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    reason: str = ""
    requires_manual_reset: bool = False


@dataclass
class RiskState:
    position_size_multiplier: float = 1.0
    is_disqualified: bool = False
    requires_liquidation: bool = False
    active_breakers: list[CircuitBreaker] = field(default_factory=list)


class RiskManager:
    """Enforces circuit breakers, anti-churn, and tournament position sizing."""

    SOFT_HALT_HOURS = 24
    MEDIUM_HALT_HOURS = 48
    CONSECUTIVE_LOSS_HALT_HOURS = 4

    def __init__(self):
        self.settings = get_settings()
        self.state = RiskState()
        self._breakers: dict[str, CircuitBreaker] = {}
        self._last_exit_times: dict[str, datetime] = {}

    def _activate_breaker(
        self,
        breaker_type: str,
        reason: str,
        duration_hours: Optional[int] = None,
        requires_manual_reset: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        expires = None if requires_manual_reset else (
            now + timedelta(hours=duration_hours) if duration_hours else None
        )
        breaker = CircuitBreaker(
            breaker_type=breaker_type,
            is_active=True,
            activated_at=now,
            expires_at=expires,
            reason=reason,
            requires_manual_reset=requires_manual_reset,
        )
        self._breakers[breaker_type] = breaker
        self.state.active_breakers = list(self._breakers.values())
        logger.warning("Circuit breaker activated: %s - %s", breaker_type, reason)

    def _deactivate_expired_breakers(self) -> None:
        now = datetime.now(timezone.utc)
        for key, breaker in list(self._breakers.items()):
            if breaker.requires_manual_reset:
                continue
            if breaker.expires_at and now >= breaker.expires_at:
                del self._breakers[key]
                logger.info("Circuit breaker expired: %s", key)
        self.state.active_breakers = list(self._breakers.values())

    def record_exit(self, token: str) -> None:
        self._last_exit_times[token.upper()] = datetime.now(timezone.utc)

    def can_enter_position(self, token: str) -> tuple[bool, str]:
        """Anti-churn: block re-entry within MIN_REENTRY_HOURS of last exit."""
        key = token.upper()
        last_exit = self._last_exit_times.get(key)
        if not last_exit:
            return True, "OK"
        elapsed = datetime.now(timezone.utc) - last_exit
        if elapsed < timedelta(hours=MIN_REENTRY_HOURS):
            remaining = timedelta(hours=MIN_REENTRY_HOURS) - elapsed
            hours_left = remaining.total_seconds() / 3600
            return False, f"Anti-churn: Must wait {hours_left:.1f}h before re-entering {token}"
        return True, "OK"

    def check_portfolio_risk(
        self,
        drawdown_pct: float,
        daily_pnl_pct: float,
        consecutive_losses: int,
    ) -> tuple[bool, str]:
        self._deactivate_expired_breakers()
        self.state.requires_liquidation = False

        if drawdown_pct >= RISK_LAYERS["dq_line"]:
            self.state.is_disqualified = True
            self._activate_breaker("dq_line", "DISQUALIFIED: 30% drawdown exceeded")
            return False, "DISQUALIFIED: 30% max drawdown exceeded"

        if drawdown_pct >= RISK_LAYERS["hard_halt"]:
            if "hard_halt" not in self._breakers:
                self.state.requires_liquidation = True
                self._activate_breaker(
                    "hard_halt",
                    "28% drawdown: liquidate all, halt until manual reset",
                    requires_manual_reset=True,
                )
            return False, "HARD HALT: 28% drawdown — liquidate all positions"

        if drawdown_pct >= RISK_LAYERS["medium_halt"]:
            if "medium_halt" not in self._breakers:
                self._activate_breaker(
                    "medium_halt",
                    "25% drawdown: halt 48h, manual review required",
                    self.MEDIUM_HALT_HOURS,
                )
            return False, "Trading halted: 25% drawdown threshold"

        if drawdown_pct >= RISK_LAYERS["soft_halt"]:
            if "soft_halt" not in self._breakers:
                self.state.position_size_multiplier = 0.5
                self._activate_breaker(
                    "soft_halt",
                    "20% drawdown: halt 24h, position sizes reduced 50%",
                    self.SOFT_HALT_HOURS,
                )
            if self._breakers.get("soft_halt", CircuitBreaker("")).is_active:
                return False, "Trading halted: 20% drawdown cooling period"

        if daily_pnl_pct <= -self.settings.daily_loss_halt:
            if "daily_loss" not in self._breakers:
                self._activate_breaker(
                    "daily_loss",
                    f"Daily loss {daily_pnl_pct*100:.1f}% exceeds 10% limit",
                )
            return False, "Trading halted: daily loss limit exceeded"

        if consecutive_losses >= 3:
            if "consecutive_losses" not in self._breakers:
                self._activate_breaker(
                    "consecutive_losses",
                    "3 consecutive losses: 4 hour cooling period",
                    self.CONSECUTIVE_LOSS_HALT_HOURS,
                )
            if self._breakers.get("consecutive_losses", CircuitBreaker("")).is_active:
                return False, "Trading halted: 3 consecutive losses"

        blocking = [
            b for b in self._breakers.values()
            if b.is_active and b.breaker_type not in ("soft_halt", "medium_halt", "hard_halt", "dq_line")
        ]
        # Re-check timed halts that should block new entries
        for b in self._breakers.values():
            if b.is_active and b.breaker_type in ("soft_halt", "medium_halt", "hard_halt"):
                return False, f"Active breaker: {b.reason}"

        if blocking:
            return False, f"Active breaker: {blocking[0].reason}"

        return True, "Risk checks passed"

    def validate_trade(
        self,
        signal: TradeSignal,
        portfolio_value: float,
        open_positions: int,
        trades_today: int,
        token_eligible: bool,
    ) -> tuple[bool, str]:
        if self.state.is_disqualified:
            return False, "Agent disqualified"

        if not token_eligible:
            return False, f"Token not eligible: {signal.token}"

        if signal.action == "BUY":
            can_enter, churn_reason = self.can_enter_position(signal.token)
            if not can_enter:
                return False, churn_reason

        if trades_today >= self.settings.max_trades_per_day:
            return False, f"Max trades per day ({self.settings.max_trades_per_day}) reached"

        if open_positions >= self.settings.max_concurrent_positions and signal.action == "BUY":
            return False, f"Max concurrent positions ({self.settings.max_concurrent_positions}) reached"

        trade_value = portfolio_value * signal.position_size_pct * self.state.position_size_multiplier
        max_trade = portfolio_value * self.settings.max_position_pct
        if trade_value > max_trade:
            return False, f"Trade size ${trade_value:.2f} exceeds 25% limit (${max_trade:.2f})"

        return True, "Trade validated"

    def calculate_tournament_position_size(self, confidence: float, drawdown_pct: float) -> float:
        """Tournament sizing: aggressive when healthy, conservative near DQ line."""
        base = 0.15
        risk_budget = max(0.0, (RISK_LAYERS["dq_line"] - drawdown_pct) / RISK_LAYERS["dq_line"])

        if drawdown_pct < 0.10:
            multiplier = 1.0
        elif drawdown_pct < 0.20:
            multiplier = 0.7
        else:
            multiplier = 0.4

        size = base * confidence * risk_budget * multiplier * self.state.position_size_multiplier
        return min(size, self.settings.max_position_pct)

    def calculate_position_size(
        self,
        base_size_pct: float,
        confidence: float,
        drawdown_pct: float,
        atr_ratio: float = 1.0,
    ) -> float:
        """Legacy wrapper — delegates to tournament sizing when base is default."""
        if base_size_pct >= 0.14:
            return self.calculate_tournament_position_size(confidence, drawdown_pct)
        risk_budget = max(0, (RISK_LAYERS["dq_line"] - drawdown_pct) / RISK_LAYERS["dq_line"])
        volatility_factor = 1 / (1 + atr_ratio)
        size = base_size_pct * confidence * risk_budget * volatility_factor * self.state.position_size_multiplier
        return min(size, self.settings.max_position_pct)

    def manual_reset(self) -> bool:
        """Reset hard halt after manual review."""
        if "hard_halt" in self._breakers:
            del self._breakers["hard_halt"]
            self.state.requires_liquidation = False
            self.state.active_breakers = list(self._breakers.values())
            logger.info("Hard halt manually reset")
            return True
        return False

    def get_status(self) -> dict:
        self._deactivate_expired_breakers()
        return {
            "is_disqualified": self.state.is_disqualified,
            "requires_liquidation": self.state.requires_liquidation,
            "position_size_multiplier": self.state.position_size_multiplier,
            "risk_layers": RISK_LAYERS,
            "min_reentry_hours": MIN_REENTRY_HOURS,
            "active_breakers": [
                {
                    "type": b.breaker_type,
                    "reason": b.reason,
                    "activated_at": b.activated_at.isoformat() if b.activated_at else None,
                    "expires_at": b.expires_at.isoformat() if b.expires_at else None,
                    "requires_manual_reset": b.requires_manual_reset,
                }
                for b in self.state.active_breakers
            ],
        }
