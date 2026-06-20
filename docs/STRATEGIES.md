# Tradi Strategies

## 1. Market State Adapter (60%)

Detects market regime hourly using ADX and ATR:

| Regime | Condition | Strategy |
|--------|-----------|----------|
| TRENDING | ADX > 25, ATR > 1.5× avg | Momentum |
| RANGING | ADX < 20 | Mean reversion |
| VOLATILE | ATR > 2× avg | Breakout |
| ACCUMULATION | Default | DCA |

## 2. Smart Money Shadow (disabled)

**Status:** Disabled in orchestrator until BSC on-chain whale indexer is integrated.

Paper mode previously used simulated random signals (`WhaleShadow.SIMULATED = True`), which produced fake copy-trade signals. Re-enable by setting `WHALE_SHADOW_ENABLED = True` in `orchestrator.py` after wiring real wallet monitoring.

## 3. Momentum Breakout (15%)

Directional momentum on eligible tokens only:
- Entry: Price breaks above 20-period high with volume > 1.5× average
- Exit: Trailing stop at 2× ATR or 48h max hold
- Position: 15% of portfolio (dynamic risk budget)
- Stop: 3% hard stop

## Strategy Selection

Every 15 minutes:
1. Run all strategies
2. Reject ineligible tokens (score = 0)
3. Apply priority boosts (market state in TRENDING/VOLATILE, whale confidence > 85%)
4. Execute highest `opportunity_score` if above threshold
5. Keepalive trade at 20:00 UTC if no trades today

## Risk Features

- **Dynamic Risk Budgeting** — Position sizes scale with drawdown and confidence
- **Profit Protection Scaling** — Trim winners at +10%, +20%, +35% gains
- **Reentry Throttle** — 4-hour cooldown before re-entering a token after exit
