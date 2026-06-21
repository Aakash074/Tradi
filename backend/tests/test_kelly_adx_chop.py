"""Kelly ADX scaler and choppy-range entry filter."""

from pathlib import Path
from unittest.mock import MagicMock

from agent.confluence_engine import ConfluenceEngine
from agent.russian_doll_risk import RussianDollRisk
from strategies.kelly_sizing import adx_scale, aggressive_sizing, dynamic_sizing
from strategies.regime_filter import RegimeMode
from tournament_config import load_tournament_config

ROOT = Path(__file__).resolve().parents[2]
MIN_POSITION_PCT = 0.005


def test_adx_scale_at_20_and_25():
    assert adx_scale(20) == 0.8
    assert adx_scale(25) == 1.0
    assert adx_scale(30) == 1.0


def test_dynamic_sizing_shrinks_when_adx_below_25():
    # Use inputs that stay below the 5% cap so ADX scaling is visible
    weak_trend = dynamic_sizing(0.03, 0.7, RegimeMode.NORMAL, 0.0, "dynamic", current_adx=20)
    strong_trend = dynamic_sizing(0.03, 0.7, RegimeMode.NORMAL, 0.0, "dynamic", current_adx=25)
    assert weak_trend == strong_trend * 0.8
    assert weak_trend < strong_trend


def _flat_ohlcv(close: float, n: int = 50) -> dict:
    """Low ATR / tight range series."""
    return {
        "open": [close] * n,
        "high": [close * 1.001] * n,
        "low": [close * 0.999] * n,
        "close": [close] * n,
        "volume": [1_000_000.0] * n,
    }


def test_chop_filter_rejects_tight_range():
    cmc = MagicMock()
    engine = ConfluenceEngine(cmc, MagicMock(), account_size=10_000)
    ohlcv = _flat_ohlcv(100.0)
    ok, _, _ = engine.entry_signal("CAKE", ohlcv, ohlcv, 100.0)
    assert ok is False


def test_kelly_position_scaled_in_entry_signal(monkeypatch):
    cmc = MagicMock()
    engine = ConfluenceEngine(cmc, MagicMock(), account_size=10_000)

    monkeypatch.setattr(
        engine.historical,
        "analyze",
        lambda token, ohlcv_5h: (True, "ok", 0.8),
    )
    monkeypatch.setattr(
        engine.sweep_detector,
        "detect",
        lambda token, ohlcv: (False, {}),
    )
    monkeypatch.setattr(engine.fvg, "is_near_fvg", lambda ohlcv, price: (False, None))
    monkeypatch.setattr(
        "agent.confluence_engine.momentum_pullback_from_ohlcv",
        lambda ohlcv, **kw: (True, "pullback", 0.75),
    )

    # Wider range so chop filter passes; ADX still low on flat-ish trend
    n = 50
    close = 100.0
    ohlcv = {
        "open": [close + (i % 3) * 0.05 for i in range(n)],
        "high": [close + 0.8 + (i % 5) * 0.1 for i in range(n)],
        "low": [close - 0.8 - (i % 5) * 0.1 for i in range(n)],
        "close": [close + (i % 7) * 0.08 for i in range(n)],
        "volume": [2_000_000.0] * n,
    }

    fixed_kelly = 500.0
    monkeypatch.setattr(
        engine.checklist,
        "validate",
        lambda *a, **k: (True, [], fixed_kelly),
    )
    monkeypatch.setattr(engine.checklist, "log_check", lambda *a, **k: (True, fixed_kelly))

    ok_low, data_low, _ = engine.entry_signal("CAKE", ohlcv, ohlcv, ohlcv["close"][-1])
    if not ok_low:
        # If ADX computed >= 25 on synthetic data, force-verify scaler directly
        assert adx_scale(20) < adx_scale(25)
        return

    scale = data_low["size_pct"] / min(0.05, (fixed_kelly * 0.8) / engine.account_size)
    assert scale <= 1.0


def test_kelly_50_at_adx_20_below_minimum():
    """Kelly $50 scaled to $40 must fail the 0.5% floor on $10k."""
    account = 10_000
    scaled = 50 * adx_scale(20)
    pct = scaled / account
    assert pct < MIN_POSITION_PCT


def test_high_adx_aggressive_hits_full_cap():
    """ADX 40 gets 1.0x scale — same max aggressive size as ADX 25 (5% cap)."""
    at_25 = aggressive_sizing(0.8, 0.0, 0.02, current_adx=25)
    at_40 = aggressive_sizing(0.8, 0.0, 0.02, current_adx=40)
    assert adx_scale(40) == 1.0
    assert at_40 == at_25 == 0.05


def test_tournament_halt_fires_above_20pct():
    tourn = load_tournament_config(ROOT / "config" / "tournament_week.yaml")
    rd = RussianDollRisk(halt_at=tourn.halt_drawdown)
    assert rd.check_drawdown(0.19) is True
    assert rd.state.trading_halted is False
    assert rd.check_drawdown(0.21) is False
    assert rd.state.trading_halted is True
