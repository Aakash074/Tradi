"""Main orchestration loop for Tradi trading agent."""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from agent.momentum_breakout import MomentumBreakout
from agent.portfolio import PortfolioTracker
from agent.position_manager import apply_lock_in_ratchet
from agent.regime_switcher import RegimeSwitcher
from agent.risk_manager import RiskManager
from agent.whale_shadow import WhaleShadow
from config import get_settings
from data.bnb_sdk import BNBAIAgentSDK
from data.cmchub_client import CMCHubClient
from data.twak_wrapper import TWAKWrapper
from strategies.regime_detection import MarketRegime, get_regime_strategy_label
from strategies.signal_generation import TradeSignal, select_best_signal
from validation.token_validator import TokenValidator

logger = logging.getLogger(__name__)


class TradiOrchestrator:
    """Coordinates data, strategies, risk, and execution."""

    LOOP_INTERVAL_SECONDS = 900  # 15 minutes
    KEEPALIVE_HOUR_UTC = 20
    MAX_HOLD_HOURS = 48

    def __init__(self):
        self.settings = get_settings()
        self.validator = TokenValidator()
        self.cmc = CMCHubClient()
        self.twak = TWAKWrapper()
        self.bnb_sdk = BNBAIAgentSDK()
        self.portfolio = PortfolioTracker()
        self.risk = RiskManager()
        self.regime_switcher = RegimeSwitcher(self.cmc, self.validator)
        self.whale_shadow = WhaleShadow(self.validator)
        self.momentum_breakout = MomentumBreakout(self.cmc, self.validator)
        self._running = False
        self._open_positions: list[dict] = []
        self._activity_log: list[dict] = []
        self._trade_history: list[dict] = []
        self._regime_metrics: dict = {}

    async def initialize(self) -> dict:
        results = {}
        ok, msg = await self.twak.create_wallet()
        results["wallet"] = {"success": ok, "message": msg}
        address = await self.twak.get_wallet_address()
        results["wallet_address"] = address

        ok, msg = await self.twak.register_competition()
        results["competition_registration"] = {"success": ok, "message": msg}

        ok, agent_id = await self.bnb_sdk.register_agent("Tradi")
        results["agent_identity"] = {"success": ok, "agent_id": agent_id}

        logger.info("Tradi initialized: wallet=%s agent=%s", address, agent_id)
        return results

    def _log_activity(
        self, strategy: str, action: str, token: str, message: str, eligible: bool = True
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy": strategy,
            "action": action,
            "token": token,
            "message": message,
            "eligible": eligible,
        }
        self._activity_log.insert(0, entry)
        self._activity_log = self._activity_log[:200]
        logger.info("[%s] %s %s %s [ELIGIBLE: %s]", strategy, action, token, message, "YES" if eligible else "NO")

    async def evaluate_strategies(self) -> list[TradeSignal]:
        # Refresh regime before strategy evaluation
        await self.regime_switcher.detect_and_update_regime()
        self._regime_metrics = getattr(self.regime_switcher, "_last_metrics", {})

        regime_signals = await self.regime_switcher.scan_opportunities()
        whale_signals = await self.whale_shadow.detect_whale_signals()
        momentum_signals = await self.momentum_breakout.scan_breakouts()

        all_signals = regime_signals + whale_signals + momentum_signals

        filtered = []
        for signal in all_signals:
            if signal.action == "HOLD":
                filtered.append(signal)
                continue
            valid, reason = self.validator.validate_signal(signal.token)
            if not valid:
                self._log_activity(signal.strategy, signal.action, signal.token, reason, eligible=False)
                continue
            if signal.token_to:
                pair_valid, pair_reason = self.validator.validate_pair(signal.token, signal.token_to)
                if not pair_valid and signal.token_to not in ("BNB", "BUSD"):
                    self._log_activity(signal.strategy, signal.action, signal.token, pair_reason, eligible=False)
                    continue
            filtered.append(signal)

        return filtered

    def _apply_priority_rules(self, signals: list[TradeSignal]) -> list[TradeSignal]:
        regime = self.regime_switcher.current_regime
        boosted = []
        for signal in signals:
            score = signal.opportunity_score
            if signal.strategy == "REGIME" and regime in (MarketRegime.TRENDING, MarketRegime.VOLATILE):
                score *= 1.2
            if signal.strategy == "MOMENTUM" and regime == MarketRegime.TRENDING:
                score *= 1.25
            if signal.strategy == "WHALE" and signal.confidence > 0.85:
                score *= 1.15
            boosted.append((score, signal))
        boosted.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in boosted]

    async def _update_position_prices(self) -> None:
        for pos in self._open_positions:
            token = pos.get("token_to") or pos.get("token")
            if not token:
                continue
            try:
                price = await self.cmc.get_price(token)
                pos["current_price"] = price
                entry = pos.get("entry_price", price)
                if entry:
                    pos["unrealized_pnl_pct"] = (price - entry) / entry
            except Exception as e:
                logger.warning("Price update failed for %s: %s", token, e)

    async def _apply_ratchet(self) -> list[dict]:
        portfolio_value = self.portfolio.state.total_value_usd
        return apply_lock_in_ratchet(
            self._open_positions,
            portfolio_value,
            log_fn=self._log_activity,
        )

    async def _liquidate_all_positions(self) -> list[dict]:
        """Emergency liquidation when hard halt triggers."""
        results = []
        for pos in list(self._open_positions):
            token = pos.get("token_to") or pos.get("token")
            self.risk.record_exit(token)
            pos["status"] = "closed"
            pos["closed_at"] = datetime.now(timezone.utc).isoformat()
            pos["exit_reason"] = "Hard halt liquidation"
            self._trade_history.insert(0, {**pos, "action": "SELL"})
            results.append(pos)
            self._log_activity("RISK", "LIQUIDATE", token, "Hard halt: liquidated all positions")
        self._open_positions.clear()
        return results

    async def _check_position_exits(self) -> None:
        """Exit on stop loss, max hold, or trailing stop."""
        now = datetime.now(timezone.utc)
        to_close = []

        for pos in self._open_positions:
            token = pos.get("token_to") or pos.get("token")
            entry = pos.get("entry_price", 0)
            current = pos.get("current_price", entry)
            opened = pos.get("timestamp")

            if entry and current:
                pnl_pct = (current - entry) / entry
                stop = pos.get("stop_loss")
                if stop and current <= stop:
                    to_close.append((pos, f"Stop loss hit ({pnl_pct*100:.1f}%)"))
                    continue
                if pnl_pct <= -0.03 and pos.get("strategy") == "MOMENTUM":
                    to_close.append((pos, "3% hard stop (momentum)"))
                    continue

            if opened:
                opened_dt = datetime.fromisoformat(opened.replace("Z", "+00:00"))
                if now - opened_dt > timedelta(hours=self.MAX_HOLD_HOURS):
                    to_close.append((pos, f"Max hold {self.MAX_HOLD_HOURS}h exceeded"))

        for pos, reason in to_close:
            token = pos.get("token_to") or pos.get("token")
            self.risk.record_exit(token)
            pos["status"] = "closed"
            pos["closed_at"] = now.isoformat()
            pos["exit_reason"] = reason
            self._open_positions.remove(pos)
            self._trade_history.insert(0, {**pos, "action": "SELL"})
            self._log_activity(pos.get("strategy", "SYSTEM"), "SELL", token, reason)

    async def execute_signal(self, signal: TradeSignal) -> Optional[dict]:
        portfolio = self.portfolio.to_dict()
        drawdown = portfolio["drawdown_pct"] / 100
        daily_pnl = portfolio["daily_pnl_pct"] / 100

        can_trade, risk_reason = self.risk.check_portfolio_risk(
            drawdown, daily_pnl, portfolio["consecutive_losses"]
        )
        if not can_trade:
            if self.risk.state.requires_liquidation:
                await self._liquidate_all_positions()
            self._log_activity(signal.strategy, "REJECTED", signal.token, risk_reason)
            return None

        # Tournament position sizing
        signal.position_size_pct = self.risk.calculate_tournament_position_size(
            signal.confidence, drawdown
        )

        valid, validate_reason = self.risk.validate_trade(
            signal,
            portfolio["total_value_usd"],
            len(self._open_positions),
            portfolio["trades_today"],
            self.validator.is_eligible(signal.token),
        )
        if not valid:
            self._log_activity(signal.strategy, "REJECTED", signal.token, validate_reason)
            return None

        if signal.action == "HOLD":
            self._log_activity(signal.strategy, signal.action, signal.token, signal.reason)
            return {"action": signal.action, "token": signal.token, "reason": signal.reason}

        trade_amount = portfolio["total_value_usd"] * signal.position_size_pct
        from_token = "USDT"
        to_token = signal.token

        quote = await self.twak.get_swap_quote(from_token, to_token, trade_amount)
        if not quote:
            self._log_activity(signal.strategy, "FAILED", signal.token, "Failed to get swap quote")
            return None

        await asyncio.sleep(random.uniform(0.5, 1.0))

        result = await self.twak.execute_swap(quote.quote_id, slippage=0.5)
        if not result.success:
            self._log_activity(signal.strategy, "FAILED", signal.token, result.error or "Swap failed")
            return None

        price = await self.cmc.get_price(signal.token)
        trade_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy": signal.strategy,
            "action": signal.action,
            "token_from": from_token,
            "token_to": to_token,
            "amount_usd": trade_amount,
            "entry_price": price,
            "current_price": price,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "eligible": True,
            "tx_hash": result.tx_hash,
            "status": "open",
            "unrealized_pnl_pct": 0.0,
        }
        self._trade_history.insert(0, trade_record)
        self._open_positions.append(
            {
                **trade_record,
                "stop_loss": price * (1 - signal.stop_loss_pct) if signal.stop_loss_pct else None,
                "take_profit": price * (1 + signal.take_profit_pct) if signal.take_profit_pct else None,
            }
        )
        self.portfolio.record_trade(0)
        self._log_activity(signal.strategy, signal.action, signal.token, signal.reason, eligible=True)

        await self.bnb_sdk.log_trade_from_dict(
            {
                "token_from": from_token,
                "token_to": to_token,
                "entry_price": price,
                "position_size_usd": trade_amount,
                "strategy": signal.strategy,
                "confidence": signal.confidence,
                "reasoning": signal.reason,
                "eligible": True,
                "tx_hash": result.tx_hash,
            }
        )
        return trade_record

    async def keepalive_trade(self) -> Optional[dict]:
        now = datetime.now(timezone.utc)
        portfolio = self.portfolio.to_dict()
        if portfolio["trades_today"] > 0:
            return None
        if now.hour < self.KEEPALIVE_HOUR_UTC:
            return None

        signal = TradeSignal(
            strategy="KEEPALIVE",
            action="BUY",
            token="USDT",
            token_to="USDC",
            confidence=1.0,
            expected_return=0.0001,
            risk=0.01,
            position_size_pct=0.01,
            reason="Daily minimum trade requirement (keepalive)",
        )
        self._log_activity("KEEPALIVE", "BUY", "USDT", "Executing minimum daily trade")
        return await self.execute_signal(signal)

    async def run_cycle(self) -> dict:
        await self._update_position_prices()
        await self._check_position_exits()
        ratchet_actions = await self._apply_ratchet()

        signals = await self.evaluate_strategies()
        prioritized = self._apply_priority_rules(signals)
        best = select_best_signal(prioritized)

        regime = self.regime_switcher.current_regime
        result = {
            "signals_count": len(signals),
            "trade": None,
            "regime": regime.value,
            "active_strategy": get_regime_strategy_label(regime),
            "ratchet_actions": ratchet_actions,
        }

        if best and best.action != "HOLD":
            result["trade"] = await self.execute_signal(best)
        else:
            result["trade"] = await self.keepalive_trade()

        if self.settings.agent_mode == "paper":
            change = random.uniform(-0.005, 0.008)
            new_value = self.portfolio.state.total_value_usd * (1 + change)
            self.portfolio.update_value(new_value)

        return result

    async def run_loop(self) -> None:
        self._running = True
        logger.info("Tradi agent loop started (interval=%ds)", self.LOOP_INTERVAL_SECONDS)
        while self._running:
            try:
                cycle_result = await self.run_cycle()
                logger.info("Cycle complete: %s", cycle_result)
            except Exception as e:
                logger.exception("Cycle error: %s", e)
            await asyncio.sleep(self.LOOP_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False

    def get_dashboard_state(self) -> dict:
        portfolio = self.portfolio.to_dict()
        regime = self.regime_switcher.current_regime
        active_strategy = get_regime_strategy_label(regime)
        return {
            "agent_name": "Tradi",
            "mode": self.settings.agent_mode,
            "portfolio": portfolio,
            "regime": regime.value,
            "active_strategy": active_strategy,
            "regime_display": f"Market State: {regime.value} — Using {active_strategy}",
            "regime_metrics": self._regime_metrics,
            "risk": self.risk.get_status(),
            "open_positions": self._open_positions,
            "trade_history": self._trade_history[:50],
            "activity_log": self._activity_log[:50],
            "whales": self.whale_shadow.get_whale_stats(),
            "momentum": self.momentum_breakout.get_stats(),
            "eligible_token_count": self.validator.count,
            "x402_stats": self.cmc.get_x402_stats(),
            "wallet_address": None,
            "twak_registered": self.twak.is_registered,
            "agent_id": self.bnb_sdk.agent_id,
        }

    async def get_full_state(self) -> dict:
        state = self.get_dashboard_state()
        state["wallet_address"] = await self.twak.get_wallet_address()
        state["on_chain_logs"] = self.bnb_sdk.get_trade_logs()
        return state
