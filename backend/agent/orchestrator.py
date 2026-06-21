"""Main orchestration loop for Tradi — Three-Layer Confluence model."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from agent.checkpoint import load_checkpoint, save_checkpoint
from agent.confluence_engine import ConfluenceEngine
from agent.exit_manager import TRAILING_ACTIVATION_PCT, apply_trailing_stop, set_exit_levels
from agent.keepalive_strategy import KeepaliveStrategy
from agent.portfolio import PortfolioTracker
from agent.position_manager import apply_profit_protection_scaling
from agent.risk_manager import RiskManager
from agent.trade_enforcer import SmartTradeEnforcer
from config import get_settings
from data.bnb_sdk import BNBAIAgentSDK
from data.cmchub_client import CMCHubClient
from data.twak_wrapper import TWAKWrapper
from strategies.signal_generation import TradeSignal
from tournament_config import TournamentConfig, load_tournament_config
from validation.token_validator import TokenValidator

logger = logging.getLogger(__name__)

MIN_TRADE_USD = 2.0  # Skip entries below this (BSC gas / pool minimums)


class TradiOrchestrator:
    """Coordinates confluence strategies, risk, and execution."""

    LOOP_INTERVAL_SECONDS = 900
    MAX_HOLD_HOURS = 48

    def __init__(
        self,
        tournament_config_path: Optional[Path] = None,
        live_cmc: bool = False,
        dry_run: bool = False,
    ):
        import os

        if dry_run:
            os.environ["COMPETITION_DRY_RUN"] = "1"
            get_settings.cache_clear()

        self.settings = get_settings()
        self.validator = TokenValidator()
        self.cmc = CMCHubClient(live_cmc=live_cmc)
        self.twak = TWAKWrapper()
        self.bnb_sdk = BNBAIAgentSDK()
        self.portfolio = PortfolioTracker()
        self.risk = RiskManager()
        self.tournament_config_path = tournament_config_path
        self.production_config_path = (
            tournament_config_path
            if tournament_config_path and "production" in tournament_config_path.name
            else None
        )

        self.tournament_config: Optional[TournamentConfig] = None
        if tournament_config_path:
            self.tournament_config = load_tournament_config(tournament_config_path)
            label = "PRODUCTION" if "production" in tournament_config_path.name else "TOURNAMENT"
            logger.info("%s MODE ACTIVE", label)
            logger.info(
                "  strategy=%s exits=%s adx=%s sizing=%s universe=%s",
                self.tournament_config.strategy,
                self.tournament_config.asymmetric_exits,
                self.tournament_config.adx_filter,
                self.tournament_config.sizing,
                self.tournament_config.universe,
            )
        elif self.settings.agent_mode == "competition":
            self.tournament_config = load_tournament_config()
            logger.info("TOURNAMENT MODE ACTIVE")

        if self.settings.competition_dry_run:
            logger.info("COMPETITION DRY RUN — paper swaps, real wallet sync enabled")

        self.confluence = ConfluenceEngine(self.cmc, self.validator, self.tournament_config)
        self.keepalive_strategy = KeepaliveStrategy(self.cmc, self.validator)
        self.trade_enforcer = SmartTradeEnforcer(self.tournament_config)
        self._running = False
        self._open_positions: list[dict] = []
        self._activity_log: list[dict] = []
        self._trade_history: list[dict] = []
        self._last_kelly_size: float = 0.0
        self._checkpoint_cycle_num: int = 0

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

        restored = load_checkpoint(self)
        await self._sync_portfolio_from_wallet(after_checkpoint=restored)
        if restored:
            await self._update_position_prices()

        results["portfolio"] = self.portfolio.to_dict()
        results["checkpoint_restored"] = restored
        logger.info("Tradi initialized: wallet=%s agent=%s", address, agent_id)
        return results

    def _apply_runtime_config(self, mode: str, config_path: Path) -> None:
        """Reload tournament YAML and strategy components after a mode switch."""
        import os

        os.environ["AGENT_MODE"] = mode
        get_settings.cache_clear()
        self.settings = get_settings()
        self.cmc.settings = self.settings
        self.twak.settings = self.settings
        self.cmc.mcp.settings = self.settings

        paper = self.settings.agent_mode == "paper" and not self.settings.competition_dry_run
        if getattr(self.cmc.mcp, "x402", None) is not None:
            self.cmc.mcp.x402.paper_mode = paper

        self.tournament_config_path = config_path
        self.tournament_config = load_tournament_config(config_path)
        portfolio_value = self.portfolio.to_dict().get("total_value_usd") or 10000.0
        self.confluence = ConfluenceEngine(
            self.cmc,
            self.validator,
            self.tournament_config,
            account_size=portfolio_value,
        )
        self.trade_enforcer = SmartTradeEnforcer(self.tournament_config)

        label = "TOURNAMENT" if "tournament" in config_path.name else "PRODUCTION"
        logger.info(
            "MODE_SWITCH %s | agent_mode=%s strategy=%s exits=%s adx=%s sizing=%s",
            label,
            mode,
            self.tournament_config.strategy,
            self.tournament_config.asymmetric_exits,
            self.tournament_config.adx_filter,
            self.tournament_config.sizing,
        )

    async def apply_agent_mode(self, mode: str, config_path: Path) -> None:
        """Switch paper ↔ competition at runtime (UTC competition window)."""
        if mode == self.settings.agent_mode and self.tournament_config_path == config_path:
            return

        prev = self.settings.agent_mode
        self._apply_runtime_config(mode, config_path)
        await self._sync_portfolio_from_wallet()

        if mode == "competition" and prev != "competition":
            ok, msg = await self.twak.register_competition()
            logger.info("COMPETITION_AUTO_START registration ok=%s msg=%s", ok, msg)
        elif mode == "paper" and prev == "competition":
            logger.info("COMPETITION_AUTO_END — back to paper swaps")

    async def _sync_portfolio_from_wallet(self, after_checkpoint: bool = False) -> None:
        """Seed or reconcile portfolio from TWAK wallet (competition/live/dry-run)."""
        mode = self.settings.agent_mode
        if mode == "paper" and not self.settings.competition_dry_run:
            return

        balance = await self.twak.get_wallet_balance_usd(self.cmc.get_price)
        if balance <= 0:
            if after_checkpoint:
                logger.warning(
                    "PORTFOLIO wallet sync unavailable after checkpoint — keeping saved portfolio ($%.2f)",
                    self.portfolio.state.total_value_usd,
                )
            else:
                logger.warning(
                    "PORTFOLIO wallet sync unavailable — using $%.2f paper seed",
                    self.portfolio.state.initial_value_usd,
                )
            return

        if after_checkpoint and self._open_positions:
            if self.settings.competition_dry_run:
                logger.info(
                    "PORTFOLIO wallet sync deferred — dry-run checkpoint has %d paper position(s); on_chain=$%.2f",
                    len(self._open_positions),
                    balance,
                )
                return

            self.portfolio.mark_to_market(self._open_positions)
            pos_val = self.portfolio.state.positions_value_usd
            self.portfolio.state.cash_usd = max(0.0, balance - pos_val)
            self.portfolio.state.wallet_synced = True
            self.portfolio.mark_to_market(self._open_positions)
            logger.info(
                "PORTFOLIO wallet sync (checkpoint reconcile): on_chain=$%.2f cash=$%.2f positions=$%.2f",
                balance,
                self.portfolio.state.cash_usd,
                pos_val,
            )
            return

        self.portfolio.seed_from_wallet(balance)
        suffix = " (post-checkpoint)" if after_checkpoint else ""
        logger.info("PORTFOLIO wallet sync%s: $%.2f", suffix, balance)

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

    async def evaluate_strategies(self) -> list[TradeSignal]:
        self.portfolio.mark_to_market(self._open_positions)
        portfolio = self.portfolio.to_dict()
        drawdown = portfolio["drawdown_pct"] / 100
        daily_pnl = portfolio["daily_pnl_pct"] / 100
        return await self.confluence.scan_all(
            drawdown,
            self._open_positions,
            daily_pnl,
            account_size=portfolio["total_value_usd"],
        )

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
                    pos["market_value_usd"] = self.portfolio.position_market_value(pos)
            except Exception as e:
                logger.warning("Price update failed for %s: %s", token, e)

    async def _apply_profit_protection(self) -> list[dict]:
        return apply_profit_protection_scaling(
            self._open_positions,
            self.portfolio.state.total_value_usd,
            log_fn=self._log_activity,
        )

    def _uses_on_chain_execution(self) -> bool:
        """True when TWAK performs real BSC swaps (competition/live, not paper/dry-run)."""
        return self.settings.agent_mode in ("competition", "live") and not self.settings.competition_dry_run

    async def _execute_sell_swap(
        self,
        token: str,
        amount_usd: float,
        strategy: str,
        reason: str,
    ):
        """Sell token → USDT via TWAK (simulated in paper, on-chain in competition)."""
        if amount_usd <= 0:
            return None

        if not self.validator.is_eligible(token):
            msg = f"{token} not on eligible whitelist"
            self._log_activity(strategy, "SELL_FAILED", token, msg, eligible=False)
            return None

        vol = await self.cmc.get_24h_volatility(token)
        result = await self.twak.execute_with_slippage_protection(
            token, "USDT", amount_usd, vol
        )
        if isinstance(result, str):
            self._log_activity(strategy, "SELL_FAILED", token, result)
            logger.warning("Exit sell rejected token=%s reason=%s detail=%s", token, reason, result)
            return None
        if not result.success:
            err = result.error or "Swap failed"
            self._log_activity(strategy, "SELL_FAILED", token, err)
            logger.warning("Exit sell failed token=%s reason=%s error=%s", token, reason, err)
            return None
        return result

    async def _apply_profit_protection_cash(self, actions: list[dict]) -> None:
        for action in actions:
            token = action.get("token")
            if not token:
                continue
            pos = next(
                (
                    p
                    for p in self._open_positions
                    if (p.get("token_to") or p.get("token")) == token
                ),
                None,
            )
            if not pos:
                continue
            trim_usd = action.get("trim_usd") or 0.0
            entry = pos.get("entry_price") or 0.0
            current = pos.get("current_price") or entry
            strategy = pos.get("strategy", "PROFIT_PROTECTION")

            swap = await self._execute_sell_swap(
                token, trim_usd, strategy, action.get("reason", "PROFIT_PROTECTION_TRIM")
            )
            if swap is None:
                pos["amount_usd"] = action.get("from_size_usd", pos.get("amount_usd"))
                logger.warning("PROFIT_PROTECTION deferred token=%s trim=$%.2f", token, trim_usd)
                continue

            pnl_usd = self.portfolio.trim_position(trim_usd, entry, current, token)
            pos["market_value_usd"] = self.portfolio.position_market_value(pos)
            pos["partial_exit_tx"] = swap.tx_hash
            logger.info(
                "PROFIT_PROTECTION trim token=%s amount=$%.2f pnl=$%+.2f tx=%s on_chain=%s",
                token,
                trim_usd,
                pnl_usd,
                swap.tx_hash,
                self._uses_on_chain_execution(),
            )

    async def _close_position(self, pos: dict, reason: str, now: datetime) -> bool:
        token = pos.get("token_to") or pos.get("token")
        exit_price = pos.get("current_price", pos.get("entry_price"))
        entry = pos.get("entry_price") or 0.0
        amount = pos.get("amount_usd") or 0.0
        strategy = pos.get("strategy", "SYSTEM")
        sell_usd = self.portfolio.position_market_value(pos)

        swap = await self._execute_sell_swap(token, sell_usd, strategy, reason)
        if swap is None:
            pos["exit_pending"] = reason
            logger.warning(
                "EXIT_DEFERRED token=%s reason=%s (will retry next cycle)",
                token,
                reason,
            )
            return False

        exit_price = await self.cmc.get_price(token)
        tx_hash = swap.tx_hash

        pnl_usd, pnl_pct = self.portfolio.close_position(amount, entry, exit_price, token)

        self.risk.record_exit(token)
        pos["status"] = "closed"
        pos["closed_at"] = now.isoformat()
        pos["exit_reason"] = reason
        pos["exit_price"] = exit_price
        pos["pnl_pct"] = pnl_pct
        pos["pnl_usd"] = round(pnl_usd, 2)
        pos["market_value_usd"] = 0.0
        pos["exit_tx_hash"] = tx_hash

        self._open_positions.remove(pos)
        self._trade_history.insert(0, {**pos, "action": "SELL"})
        self._log_activity(strategy, "SELL", token, f"{reason} tx={tx_hash}")
        logger.info(
            "EXIT_EXECUTED token=%s reason=%s pnl=%+.2f%% ($%+.2f) tx=%s cash=$%.2f on_chain=%s",
            token,
            reason,
            pnl_pct * 100,
            pnl_usd,
            tx_hash,
            self.portfolio.state.cash_usd,
            self._uses_on_chain_execution(),
        )

        await self.bnb_sdk.log_trade_from_dict(
            {
                "timestamp": now.isoformat(),
                "token_from": token,
                "token_to": "USDT",
                "entry_price": entry,
                "exit_price": exit_price,
                "position_size_usd": amount,
                "pnl_usd": pnl_usd,
                "strategy": strategy,
                "confidence": pos.get("confidence", 0),
                "reasoning": reason,
                "eligible": self.validator.is_eligible(token),
                "tx_hash": tx_hash,
            }
        )
        return True

    async def _check_position_exits(self) -> None:
        """Asymmetric exits: 1.5% stop, 4.5% target, trailing at +3%."""
        now = datetime.now(timezone.utc)
        to_close = []

        for pos in self._open_positions:
            token = pos.get("token_to") or pos.get("token")
            entry = pos.get("entry_price", 0)
            current = pos.get("current_price", entry)
            opened = pos.get("timestamp")
            stop = pos.get("stop_loss")
            target = pos.get("take_profit")

            if entry and current:
                if stop and current <= stop:
                    to_close.append((pos, "STOP_LOSS"))
                    continue
                if target and current >= target:
                    to_close.append((pos, "TAKE_PROFIT"))
                    continue

                trail_act = pos.get("trailing_activation", entry * (1 + TRAILING_ACTIVATION_PCT))
                trail_dist = pos.get("trailing_distance", 0.01)
                new_stop = apply_trailing_stop(current, entry, stop or 0, trail_act, trail_dist)
                if new_stop > (stop or 0):
                    pos["stop_loss"] = new_stop
                    pos["trailing_active"] = True

            if opened:
                opened_dt = datetime.fromisoformat(opened.replace("Z", "+00:00"))
                if now - opened_dt > timedelta(hours=self.MAX_HOLD_HOURS):
                    to_close.append((pos, "TIME_EXPIRED"))

        for pos, reason in to_close:
            await self._close_position(pos, reason, now)

    async def execute_signal(self, signal: TradeSignal) -> Optional[dict]:
        self.portfolio.mark_to_market(self._open_positions)
        portfolio = self.portfolio.to_dict()
        drawdown = portfolio["drawdown_pct"] / 100
        daily_pnl = portfolio["daily_pnl_pct"] / 100

        can_trade, risk_reason = self.risk.check_portfolio_risk(
            drawdown, daily_pnl, portfolio["consecutive_losses"]
        )
        if not can_trade:
            logger.warning("HALT reason=%s token=%s", risk_reason, signal.token)
            self._log_activity(signal.strategy, "REJECTED", signal.token, risk_reason)
            return None

        if len(self._open_positions) >= self.confluence.russian_doll.state.max_positions:
            self._log_activity(signal.strategy, "REJECTED", signal.token, "Max positions (Russian Doll)")
            return None

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

        self._last_kelly_size = signal.position_size_pct
        trade_amount = portfolio["total_value_usd"] * signal.position_size_pct
        if trade_amount > portfolio["cash_usd"]:
            trade_amount = portfolio["cash_usd"]
        if trade_amount <= 0:
            self._log_activity(signal.strategy, "REJECTED", signal.token, "Insufficient cash")
            return None

        if trade_amount < MIN_TRADE_USD:
            msg = f"Trade ${trade_amount:.2f} below MIN_TRADE_USD ${MIN_TRADE_USD:.0f}"
            logger.warning("%s token=%s", msg, signal.token)
            self._log_activity(signal.strategy, "REJECTED", signal.token, msg)
            return None

        from_token, to_token = "USDT", signal.token

        vol = await self.cmc.get_24h_volatility(signal.token)
        result = await self.twak.execute_with_slippage_protection(
            from_token, to_token, trade_amount, vol
        )
        if isinstance(result, str):
            self._log_activity(signal.strategy, "REJECTED", signal.token, result)
            return None
        if not result.success:
            self._log_activity(signal.strategy, "FAILED", signal.token, result.error or "Swap failed")
            return None

        price = await self.cmc.get_price(signal.token)
        if not self.portfolio.allocate_cash(trade_amount, to_token):
            self._log_activity(signal.strategy, "FAILED", signal.token, "Cash allocation failed")
            return None

        ohlcv = await self.cmc.get_ohlcv(signal.token, interval="1h", limit=30)
        from strategies.technical import atr as calc_atr

        close = ohlcv.get("close", [price])
        atr_vals = calc_atr(ohlcv.get("high", close), ohlcv.get("low", close), close, 14)
        atr_val = atr_vals[-1] if atr_vals else None
        stop_pct = signal.stop_loss_pct or self.confluence.stop_loss_pct
        take_pct = signal.take_profit_pct or self.confluence.take_profit_pct
        exits = set_exit_levels(
            price,
            atr_val,
            stop_loss_pct=stop_pct,
            take_profit_pct=take_pct,
        )
        risk_pct = exits.risk_pct

        trade_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy": signal.strategy,
            "action": signal.action,
            "token_from": from_token,
            "token_to": to_token,
            "amount_usd": trade_amount,
            "entry_price": price,
            "current_price": price,
            "market_value_usd": trade_amount,
            "unrealized_pnl_pct": 0.0,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "eligible": True,
            "tx_hash": result.tx_hash,
            "status": "open",
            "risk_pct": risk_pct,
        }
        self._trade_history.insert(0, trade_record)
        self._open_positions.append({
            **trade_record,
            "stop_loss": exits.stop_loss,
            "take_profit": exits.take_profit,
            "trailing_activation": exits.trailing_activation,
            "trailing_distance": exits.trailing_distance,
        })
        self.portfolio.record_entry()
        self.trade_enforcer.mark_trade_executed()
        self.portfolio.mark_to_market(self._open_positions)
        logger.info(
            "TRADE_EXECUTED token=%s strategy=%s size=%.2f%% amount=$%.2f price=%.6f tx=%s cash=$%.2f",
            signal.token,
            signal.strategy,
            signal.position_size_pct * 100,
            trade_amount,
            price,
            result.tx_hash,
            self.portfolio.state.cash_usd,
        )
        self._log_activity(signal.strategy, signal.action, signal.token, signal.reason)
        return trade_record

    async def keepalive_trade(self) -> Optional[dict]:
        signal = await self.keepalive_strategy.generate_signal(self.portfolio.to_dict())
        if not signal:
            return None
        return await self.execute_signal(signal)

    async def run_cycle(self) -> dict:
        await self._update_position_prices()
        await self._check_position_exits()
        profit_protection = await self._apply_profit_protection()
        await self._apply_profit_protection_cash(profit_protection)

        signals = await self.evaluate_strategies()
        executed = []

        for sig in signals:
            if sig.action == "HOLD":
                continue
            trade = await self.execute_signal(sig)
            if trade:
                executed.append(trade)

        portfolio = self.portfolio.to_dict()
        if not executed:
            forced = await self.trade_enforcer.ensure_daily_trade(
                portfolio,
                scan_fn=self.evaluate_strategies,
                execute_fn=self.execute_signal,
                find_safest_token_fn=self.confluence.find_safest_token,
            )
            if forced:
                executed.append(forced)
                logger.info("DAILY qualification trade executed token=%s", forced.get("token_to"))

        self.portfolio.mark_to_market(self._open_positions)

        self._checkpoint_cycle_num += 1
        save_checkpoint(self, self._checkpoint_cycle_num)

        regime = self.confluence.regime_mode
        p = self.portfolio.to_dict()
        return {
            "signals_count": len(signals),
            "trades_executed": len(executed),
            "trade": executed[0] if executed else None,
            "regime_mode": regime.value,
            "profit_protection_actions": profit_protection,
            "confluence": self.confluence.get_dashboard_data(),
            "portfolio": p,
        }

    async def run_loop(self) -> None:
        self._running = True
        while self._running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.exception("Cycle error: %s", e)
            await asyncio.sleep(self.LOOP_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False

    def get_dashboard_state(self) -> dict:
        self.portfolio.mark_to_market(self._open_positions)
        portfolio = self.portfolio.to_dict()
        conf = self.confluence.get_dashboard_data()
        return {
            "agent_name": "Tradi",
            "mode": self.settings.agent_mode,
            "dry_run": self.settings.competition_dry_run,
            "tournament_mode": self.tournament_config is not None,
            "portfolio": portfolio,
            "regime": conf["regime_mode"],
            "regime_mode": conf["regime_mode"],
            "regime_display": f"Regime: {conf['regime_mode']}",
            "regime_metrics": conf["regime_metrics"],
            "confluence": conf,
            "ghost": conf.get("ghost"),
            "russian_doll": conf["russian_doll"],
            "kelly_gauge": {
                "optimal_pct": round(self._last_kelly_size * 100, 2),
                "regime_multiplier": conf["regime_mode"],
            },
            "risk": self.risk.get_status(),
            "open_positions": self._open_positions,
            "trade_history": self._trade_history[:50],
            "activity_log": self._activity_log[:50],
            "eligible_token_count": self.validator.count,
            "x402_stats": self.cmc.get_x402_stats(),
            "wallet_address": None,
            "twak_registered": self.twak.is_registered,
            "agent_id": self.bnb_sdk.agent_id,
            "strategies": [
                {"name": "Momentum Pullback V3", "weight": "100%"},
            ],
        }

    async def get_full_state(self) -> dict:
        state = self.get_dashboard_state()
        state["wallet_address"] = await self.twak.get_wallet_address()
        state["on_chain_logs"] = self.bnb_sdk.get_trade_logs()
        from agent.confluence_engine import SCAN_TOKENS
        state["microstructure_heatmap"] = await self.cmc.get_microstructure_heatmap(
            [t for t in SCAN_TOKENS if self.validator.is_eligible(t)]
        )
        state["correlation_matrix"] = self._build_correlation_matrix()
        return state

    def _build_correlation_matrix(self) -> list[dict]:
        from agent.correlation_guard import get_correlation_24h
        tokens = list({p.get("token_to") or p.get("token") for p in self._open_positions if p})
        matrix = []
        for i, a in enumerate(tokens):
            for b in tokens[i + 1:]:
                matrix.append({"a": a, "b": b, "corr": round(get_correlation_24h(a, b), 2)})
        return matrix
