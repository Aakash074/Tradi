"""Tradi V3 — momentum pullback + full pre-trade confluence."""

import logging
from typing import Optional

from agent.advisory_gate import AdvisoryGate
from agent.correlation_guard import correlation_filter_fast
from agent.exit_manager import STOP_LOSS_PCT, TAKE_PROFIT_PCT, set_exit_levels
from agent.fvg_detector import FVGDetector
from agent.historical_context import HistoricalContextAnalyzer
from agent.liquidity_sweep import LiquiditySweepDetector
from agent.pre_trade_checklist import PreTradeChecklist
from agent.russian_doll_risk import RussianDollRisk
from agent.token_selector import TokenSelector
from data.bsc_gas import get_bsc_gas_gwei
from data.cmchub_client import CMCHubClient
from strategies.kelly_sizing import ADX_SCALE_REFERENCE, CHOP_ADX_MAX, CHOP_ATR_PCT, adx_scale, dynamic_sizing
from strategies.microstructure import DEFAULT_ADX_THRESHOLD, momentum_pullback_from_ohlcv
from strategies.regime_filter import RegimeMode, regime_filter
from strategies.signal_generation import TradeSignal
from strategies.technical import atr, adx
from tournament_config import TournamentConfig
from validation.token_validator import TokenValidator

logger = logging.getLogger(__name__)

SCAN_TOKENS = [
    "CAKE", "ETH", "DOGE", "SHIB", "LINK", "BNB", "ADA",
    "AVAX", "DOT", "UNI", "AAVE", "ATOM", "FIL", "INJ",
    "LTC", "BCH", "TON", "DAI", "USDT", "USDC",
]

MAX_SIGNALS_PER_CYCLE = 4
MIN_SIGNAL_STRENGTH = 0.6


class ConfluenceEngine:
    """V3: historical context + sweep + FVG + pre-trade checklist."""

    def __init__(
        self,
        cmc: CMCHubClient,
        validator: TokenValidator,
        tournament: Optional[TournamentConfig] = None,
        account_size: float = 10000,
    ):
        self.cmc = cmc
        self.validator = validator
        self.tournament = tournament
        self.tournament_mode = tournament is not None
        self.account_size = account_size

        self.historical = HistoricalContextAnalyzer()
        self.checklist = PreTradeChecklist(account_size=account_size)
        self.sweep_detector = LiquiditySweepDetector()
        self.fvg = FVGDetector()

        halt_at = tournament.halt_drawdown if tournament else 0.25
        self.russian_doll = RussianDollRisk(halt_at=halt_at)

        self.adx_threshold = tournament.adx_filter if tournament else DEFAULT_ADX_THRESHOLD
        self.sizing_mode = tournament.sizing if tournament else "dynamic"
        self.stop_loss_pct = tournament.stop_loss_pct if tournament else STOP_LOSS_PCT
        self.take_profit_pct = tournament.take_profit_pct if tournament else TAKE_PROFIT_PCT
        self.daily_loss_limit = tournament.daily_loss_limit if tournament else 0.10
        self.min_atr_pct = tournament.min_atr_pct if tournament else 0.0
        self.max_gas_gwei = tournament.max_gas_gwei if tournament else 0.0

        self.token_selector = TokenSelector(
            cmc,
            validator,
            top_n=tournament.top_n_tokens if tournament else 20,
            mode=tournament.universe if tournament else "all",
        ) if tournament and tournament.universe == "top_20_momentum" else None

        self.regime_mode: RegimeMode = RegimeMode.NORMAL
        self.regime_metrics: dict = {}
        self._last_scan: list[dict] = []
        self._top_momentum: set[str] = set()
        self._mcp_ta_cache: dict[str, dict] = {}
        self.advisory_gate = AdvisoryGate()
        self._advisory_blocks: list[dict] = []

    def _market_context(self) -> dict:
        return {
            "regime": self.regime_mode.value,
            "regime_metrics": self.regime_metrics,
            "russian_doll": self.russian_doll.get_status(),
            "adx_threshold": self.adx_threshold,
            "sizing_mode": self.sizing_mode,
        }

    async def refresh_universe(self) -> list[str]:
        if self.token_selector:
            tokens = await self.token_selector.refresh()
            self._top_momentum = set(tokens)
            return tokens
        return SCAN_TOKENS

    async def refresh_regime(self) -> RegimeMode:
        self.regime_mode, self.regime_metrics = await regime_filter(self.cmc)
        return self.regime_mode

    def evaluate_signal(self, strength: float) -> bool:
        return strength > MIN_SIGNAL_STRENGTH

    def get_scan_tokens(self) -> list[str]:
        if self.token_selector and self.token_selector.universe:
            return self.token_selector.universe
        return [t for t in SCAN_TOKENS if self.validator.is_eligible(t)]

    async def find_safest_token(self) -> Optional[str]:
        best_token = None
        best_atr_pct = float("inf")
        for token in self.get_scan_tokens():
            if not self.validator.is_eligible(token):
                continue
            try:
                ohlcv = await self.cmc.get_ohlcv(token, interval="1h", limit=30)
                close = ohlcv.get("close", [])
                if len(close) < 15:
                    continue
                atr_vals = atr(ohlcv["high"], ohlcv["low"], close, 14)
                if not atr_vals:
                    continue
                atr_pct = atr_vals[-1] / close[-1] if close[-1] else 1.0
                if atr_pct < best_atr_pct:
                    best_atr_pct = atr_pct
                    best_token = token
            except Exception as e:
                logger.debug("ATR check failed for %s: %s", token, e)
        return best_token

    def entry_signal(
        self,
        token: str,
        ohlcv: dict,
        ohlcv_5h: dict,
        current_price: float,
    ) -> tuple[bool, Optional[dict], float]:
        """Complete entry analysis with all filters."""
        close = ohlcv.get("close", [])
        high = ohlcv.get("high", close)
        low = ohlcv.get("low", close)
        adx_vals = adx(high, low, close, 14) if len(close) >= 15 else []
        current_adx = adx_vals[-1] if adx_vals else 0.0
        atr_vals = atr(high, low, close, 14) if len(close) >= 15 else []
        current_atr = atr_vals[-1] if atr_vals else 0.0
        ref_close = close[-1] if close else current_price

        if ref_close > 0 and current_atr > 0:
            atr_pct = current_atr / ref_close
            if self.min_atr_pct > 0 and atr_pct < self.min_atr_pct:
                logger.info(
                    "%s: Rejected — LOW_CONVICTION (atr/close=%.4f min=%.2f)",
                    token,
                    atr_pct,
                    self.min_atr_pct,
                )
                return False, None, 0.0
            if atr_pct < CHOP_ATR_PCT and current_adx < CHOP_ADX_MAX:
                logger.info(
                    "%s: Rejected — CHOPPY_RANGE (atr/close=%.4f adx=%.1f)",
                    token,
                    atr_pct,
                    current_adx,
                )
                return False, None, 0.0

        hist_valid, hist_reason, hist_conf = self.historical.analyze(token, ohlcv_5h)
        if not hist_valid and hist_conf < 0.3:
            logger.info("%s: Rejected - %s", token, hist_reason)
            return False, None, 0.0

        is_sweep, sweep_data = self.sweep_detector.detect(token, ohlcv)
        sweep_quality = self.sweep_detector.get_sweep_quality(sweep_data) if is_sweep else 0.0

        near_fvg, fvg_data = self.fvg.is_near_fvg(ohlcv, current_price)

        top_set = self._top_momentum if self._top_momentum else None
        momentum_ok, _, mom_strength = momentum_pullback_from_ohlcv(
            ohlcv,
            adx_threshold=self.adx_threshold,
            token=token,
            top_momentum_tokens=top_set,
        )

        entry_type: Optional[str] = None
        confidence = 0.0
        stop = 0.0
        target = 0.0

        if is_sweep and sweep_quality > 0.7:
            entry_type = "LIQUIDITY_SWEEP"
            confidence = sweep_quality
            stop = sweep_data["sweep_price"] * 0.99
            target = current_price * (1 + self.take_profit_pct)
        elif near_fvg and momentum_ok:
            entry_type = "FVG_MOMENTUM"
            confidence = 0.75
            if fvg_data and fvg_data["type"] == "BULLISH":
                stop = fvg_data["bottom"] * 0.995
            else:
                stop = current_price * (1 - self.stop_loss_pct)
            target = current_price * (1 + self.take_profit_pct)
        elif momentum_ok and hist_conf >= 0.6:
            entry_type = "STANDARD"
            confidence = hist_conf * 0.8
            if current_adx < 20:
                logger.info(
                    "%s: Rejected — STANDARD path ADX %.1f < 20 (hist_conf=%.2f)",
                    token,
                    current_adx,
                    hist_conf,
                )
                return False, None, 0.0
            stop = current_price * (1 - self.stop_loss_pct)
            target = current_price * (1 + self.take_profit_pct)
        else:
            if is_sweep and sweep_quality <= 0.7:
                logger.info(
                    "%s: Rejected — liquidity sweep quality %.2f <= 0.7",
                    token,
                    sweep_quality,
                )
            elif near_fvg and not momentum_ok:
                logger.info(
                    "%s: Rejected — near FVG but momentum_pullback failed (strength=%.2f)",
                    token,
                    mom_strength,
                )
            elif not momentum_ok:
                logger.info(
                    "%s: Rejected — no momentum pullback (strength=%.2f hist_conf=%.2f)",
                    token,
                    mom_strength,
                    hist_conf,
                )
            elif hist_conf < 0.6:
                logger.info(
                    "%s: Rejected — hist_conf %.2f < 0.6 for STANDARD path",
                    token,
                    hist_conf,
                )
            else:
                logger.info(
                    "%s: Rejected — no entry path (sweep=%s fvg=%s momentum=%s hist=%.2f)",
                    token,
                    is_sweep,
                    near_fvg,
                    momentum_ok,
                    hist_conf,
                )
            return False, None, 0.0

        passed, failed_checks, position_size = self.checklist.validate(
            token, current_price, stop, target, ohlcv=ohlcv
        )
        self.checklist.log_check(token, current_price, stop, target, ohlcv=ohlcv)

        if not passed:
            logger.info("%s: Checklist failed - %s", token, failed_checks)
            return False, None, 0.0

        scale = adx_scale(current_adx)
        scaled_position = position_size * scale
        if scale < 1.0:
            logger.info(
                "%s: ADX scale %.2fx (adx=%.1f ref=%.0f) kelly=$%.2f → $%.2f",
                token,
                scale,
                current_adx,
                ADX_SCALE_REFERENCE,
                position_size,
                scaled_position,
            )
        final_size_pct = min(0.05, (scaled_position * confidence) / self.account_size)
        if final_size_pct < 0.005:
            logger.info("%s: Rejected — position size %.3f%% below 0.5%% minimum", token, final_size_pct * 100)
            return False, None, 0.0

        return True, {
            "type": entry_type,
            "entry": current_price,
            "stop": stop,
            "target": target,
            "size_pct": final_size_pct,
            "confidence": confidence,
            "reason": f"{entry_type}|{hist_reason}",
            "mom_strength": mom_strength,
        }, confidence

    async def should_enter(
        self,
        token: str,
        strength: float,
        drawdown: float,
        atr_pct: float,
        open_positions: list[dict],
        daily_pnl: float = 0.0,
        size_pct: Optional[float] = None,
        signal_data: Optional[dict] = None,
        current_adx: Optional[float] = None,
    ) -> tuple[bool, float, str]:
        fng = self.regime_metrics.get("fear_greed", 50)
        if fng < 20:
            logger.info("%s: Rejected — extreme fear (F&G=%s)", token, fng)
            return False, 0.0, "EXTREME_FEAR"

        if self.regime_mode == RegimeMode.DEFENSIVE:
            logger.info("%s: Rejected — DEFENSIVE regime", token)
            return False, 0.0, "DEFENSIVE regime — hold cash"

        if daily_pnl <= -self.daily_loss_limit:
            logger.info("%s: Rejected — daily loss limit", token)
            return False, 0.0, f"Daily loss limit {self.daily_loss_limit * 100:.0f}% hit"

        if not self.russian_doll.check_drawdown(drawdown):
            logger.info("%s: Rejected — %s", token, self.russian_doll.state.halt_reason)
            return False, 0.0, self.russian_doll.state.halt_reason

        corr_ok, corr_reason = correlation_filter_fast(token, open_positions)
        if not corr_ok:
            logger.info("%s: Rejected — correlation (%s)", token, corr_reason)
            return False, 0.0, corr_reason

        if not self.evaluate_signal(strength):
            logger.info(
                "%s: Rejected — strength %.2f <= %.2f",
                token,
                strength,
                MIN_SIGNAL_STRENGTH,
            )
            return False, 0.0, f"Strength {strength:.2f} <= {MIN_SIGNAL_STRENGTH}"

        if self.max_gas_gwei > 0:
            gas_gwei = await get_bsc_gas_gwei()
            if gas_gwei is not None and gas_gwei > self.max_gas_gwei:
                logger.info(
                    "%s: Rejected — HIGH_GAS (%.1f gwei > %.0f gwei, strategy only)",
                    token,
                    gas_gwei,
                    self.max_gas_gwei,
                )
                return False, 0.0, "HIGH_GAS"

        if size_pct is not None:
            size = size_pct * self.russian_doll.state.position_size_multiplier
        else:
            size = dynamic_sizing(
                atr_pct,
                strength,
                self.regime_mode,
                drawdown,
                sizing_mode=self.sizing_mode,
                current_adx=current_adx,
            )
            size *= self.russian_doll.state.position_size_multiplier

        if size < 0.005:
            logger.info("%s: Rejected — sized below 0.5%% minimum", token)
            return False, 0.0, "Size below 0.5% minimum"

        # After signal generated, before execution:
        if signal_data is not None:
            blocked, block_reason = await self.advisory_gate.should_block(
                token, signal_data, self._market_context()
            )
            if blocked:
                logger.info("%s: Advisory gate — skipping", token)
                return False, 0.0, block_reason

        return True, min(size, 0.05), "Full confluence approved"

    async def scan_token(
        self,
        token: str,
        drawdown: float,
        open_positions: list[dict],
        daily_pnl: float = 0.0,
        account_size: Optional[float] = None,
    ) -> Optional[TradeSignal]:
        if account_size:
            self.account_size = account_size
            self.checklist.account_size = account_size

        ohlcv = await self.cmc.get_ohlcv(token, interval="1h", limit=50)
        ohlcv_5h = await self.cmc.get_ohlcv(token, interval="15m", limit=20)
        close = ohlcv.get("close", [])
        if not close:
            return None
        current_price = close[-1]

        ok, entry_data, confidence = self.entry_signal(token, ohlcv, ohlcv_5h, current_price)
        if not ok or not entry_data:
            return None

        ta = await self.cmc.get_technical_analysis(token, interval="1h")
        self._mcp_ta_cache[token] = ta
        signal = ta.get("signal", "NEUTRAL")
        if ta.get("bias") == "BEARISH" and any(k in signal for k in ("STRONG", "SELL")):
            logger.info("%s: Rejected — MCP TA bearish (%s)", token, signal)
            return None
        if ta.get("bias") == "BULLISH":
            confidence = min(1.0, confidence * 1.05)

        strength = max(confidence, entry_data.get("mom_strength", 0.0), MIN_SIGNAL_STRENGTH)
        atr_vals = atr(ohlcv.get("high", []), ohlcv.get("low", []), close, 14)
        atr_pct = (atr_vals[-1] / close[-1]) if atr_vals and close else 0.02
        adx_vals = adx(ohlcv.get("high", []), ohlcv.get("low", []), close, 14)
        current_adx = adx_vals[-1] if adx_vals else 0.0

        can_enter, size, msg = await self.should_enter(
            token,
            strength,
            drawdown,
            atr_pct,
            open_positions,
            daily_pnl,
            size_pct=entry_data.get("size_pct"),
            signal_data=entry_data,
            current_adx=current_adx,
        )
        if not can_enter:
            if msg != "ADVISORY_BLOCK":
                logger.info("%s: Rejected — should_enter (%s)", token, msg)
            if msg == "ADVISORY_BLOCK":
                self._advisory_blocks.insert(
                    0,
                    {"token": token, "reason": msg, "signal": entry_data.get("type")},
                )
                self._advisory_blocks = self._advisory_blocks[:20]
            return None

        stop_pct = (entry_data["entry"] - entry_data["stop"]) / entry_data["entry"]
        take_pct = (entry_data["target"] - entry_data["entry"]) / entry_data["entry"]

        return TradeSignal(
            strategy=entry_data["type"],
            action="BUY",
            token=token,
            token_to="USDT",
            confidence=strength,
            expected_return=take_pct,
            risk=stop_pct,
            position_size_pct=size,
            reason=f"{entry_data['reason']} | {msg}",
            stop_loss_pct=stop_pct,
            take_profit_pct=take_pct,
        )

    async def scan_all(
        self,
        drawdown: float,
        open_positions: list[dict],
        daily_pnl: float = 0.0,
        account_size: float = 10000,
    ) -> list[TradeSignal]:
        await self.refresh_regime()
        await self.refresh_universe()
        if self.regime_mode == RegimeMode.DEFENSIVE:
            return []

        held = {p.get("token_to") or p.get("token") for p in open_positions}
        signals: list[TradeSignal] = []
        self._last_scan = []

        for token in self.get_scan_tokens():
            if not self.validator.is_eligible(token) or token in held:
                continue
            sig = await self.scan_token(
                token, drawdown, open_positions, daily_pnl, account_size=account_size
            )
            if sig:
                signals.append(sig)
                self._last_scan.append({"token": token, "strength": sig.confidence, "strategy": sig.strategy})

        signals.sort(key=lambda s: s.confidence, reverse=True)
        max_new = max(0, self.russian_doll.state.max_positions - len(open_positions))
        return signals[: min(MAX_SIGNALS_PER_CYCLE, max_new)]

    def get_dashboard_data(self) -> dict:
        data = {
            "regime_mode": self.regime_mode.value,
            "regime_metrics": self.regime_metrics,
            "ghost": {"ghost_validation": "disabled", "min_strength": MIN_SIGNAL_STRENGTH},
            "russian_doll": self.russian_doll.get_status(),
            "strategies": [
                "MOMENTUM_PULLBACK_V3",
                "LIQUIDITY_SWEEP",
                "FVG_MOMENTUM",
                "STANDARD",
            ],
            "exit_ratio": f"1:{self.take_profit_pct / self.stop_loss_pct:.0f}",
            "adx_threshold": self.adx_threshold,
            "sizing_mode": self.sizing_mode,
            "last_scan": self._last_scan[:10],
            "mcp": {
                "fear_greed": self.regime_metrics.get("fear_greed"),
                "fear_greed_classification": self.regime_metrics.get("fear_greed_classification"),
                "fear_greed_source": self.regime_metrics.get("fear_greed_source"),
                "technical_analysis": dict(list(self._mcp_ta_cache.items())[:5]),
            },
            "advisory_gate": {
                **self.advisory_gate.status(),
                "recent_blocks": self._advisory_blocks[:5],
            },
        }
        if self.tournament_mode:
            data["tournament_mode"] = True
            data["tournament_config"] = {
                "asymmetric_exits": self.tournament.asymmetric_exits,
                "adx_filter": self.adx_threshold,
                "sizing": self.sizing_mode,
                "halt_drawdown": self.tournament.halt_drawdown,
                "daily_loss_limit": self.daily_loss_limit,
            }
        if self.token_selector:
            data["token_universe"] = self.token_selector.get_status()
        return data
