"""Unit tests for regime detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from strategies.regime_detection import MarketRegime, detect_regime, get_regime_strategy_label


def _make_trending_data(n=50):
    close = [100 + i * 0.5 for i in range(n)]
    high = [c + 1 for c in close]
    low = [c - 1 for c in close]
    return high, low, close


def test_regime_strategy_labels():
    assert get_regime_strategy_label(MarketRegime.TRENDING) == "Momentum Strategy"
    assert get_regime_strategy_label(MarketRegime.RANGING) == "Mean Reversion Strategy"
    assert get_regime_strategy_label(MarketRegime.VOLATILE) == "Breakout Strategy"
    assert get_regime_strategy_label(MarketRegime.ACCUMULATION) == "DCA Strategy"


def test_detect_regime_returns_metrics():
    high, low, close = _make_trending_data()
    regime, metrics = detect_regime(high, low, close)
    assert regime in MarketRegime
    assert "adx" in metrics
    assert "active_strategy" in metrics
