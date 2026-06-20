# Tradi Strategies

## 1. Regime Switcher (60%)

Detects market regime hourly using ADX, ATR, and Bollinger Band width:

| Regime | Condition | Strategy |
|--------|-----------|----------|
| TRENDING | ADX > 25, ATR > 1.5× avg | Supertrend momentum |
| RANGING | ADX < 20, BB squeeze | RSI mean reversion |
| VOLATILE | ATR > 2× avg | Bollinger breakout + volume |
| ACCUMULATION | Default | DCA near 200 EMA |

## 2. Smart Money Shadow (30%)

Tracks whale wallets with:
- Win rate > 65%
- 100+ transactions
- $50K+ portfolio
- Active within 30 days

Copies eligible token swaps with 30–60s delay, 75%+ confidence threshold.

## 3. Momentum Breakout (15%)

Directional momentum on eligible tokens only:
- Entry: Price breaks above 20-period high with volume > 1.5× average
- Exit: Trailing stop at 2× ATR or 48h max hold
- Position: 15% of portfolio (tournament-sized)
- Stop: 3% hard stop

## Strategy Selection

Every 15 minutes:
1. Run all strategies
2. Reject ineligible tokens (score = 0)
3. Apply priority boosts (regime in TRENDING/VOLATILE, whale confidence > 85%)
4. Execute highest `opportunity_score` if above threshold
5. Keepalive trade at 20:00 UTC if no trades today
