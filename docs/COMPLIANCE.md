# Tradi Competition Compliance

## Eligible Tokens

Only the 149 BEP-20 tokens in `ELIGIBLE_TOKENS.json` may be traded. Every trade validates **both** FROM and TO tokens before execution.

Verify count:

```bash
cat ELIGIBLE_TOKENS.json | jq '.tokens | length'   # → 149
bash scripts/competition_preflight.sh
```

## Trading Constraints

| Rule | Tradi Implementation |
|------|---------------------|
| Venue | PancakeSwap V2/V3 spot only via TWAK |
| No leverage/perps | Spot swaps only |
| Max position 34% | Hard cap at 25% in `risk_manager.py` |
| Min 1 trade/day | `SmartTradeEnforcer` at 20:00 UTC |
| Registration | `twak compete register` before deadline |

## Risk Gates (Hard Coded)

| Threshold | Action |
|-----------|--------|
| 8% drawdown | 50% size (Russian Doll) |
| 12% drawdown | 25% size, max 2 positions |
| 20% drawdown | Halt (tournament config) |
| 25% drawdown | Halt (production config) |
| 30% drawdown | DISQUALIFIED |
| 5% daily loss | Halt until next UTC day (config) |
| 3 consecutive losses | Halt 4 hours |

## Validation Flow (V3)

```
Token scan → regime_filter (DEFENSIVE = skip)
  → confluence_engine (momentum / sweep / FVG)
  → pre_trade_checklist (R:R, spread, volume)
  → correlation_guard
  → russian_doll_risk
  → token_validator.is_eligible()
  → risk_manager.validate_trade()
  → TWAK execute (USDT → token)
  → ... on exit ...
  → TWAK execute (token → USDT)
```

Both swap legs run through TWAK with slippage protection. Failed exit swaps defer to the next cycle.

Rejected trades logged in activity feed with reason.

## Pre-Launch Checklist

- [ ] `bash scripts/competition_preflight.sh` passes
- [ ] `twak compete status` shows registered
- [ ] Wallet funded (BNB gas + USDT)
- [ ] `CMC_API_KEY` set for live data
- [ ] Paper run shows `CYCLE` logs every 15 min
- [ ] Non-eligible tokens blocked (`POST /api/validate-token`)
- [ ] Dashboard at :3000 shows agent state
- [ ] Wallet password backed up securely

## Competition Start

```bash
export AGENT_MODE=competition
python -m tradi.agent \
  --mode competition \
  --config config/tournament_week.yaml \
  --live-cmc \
  --duration 168h \
  >> logs/competition.log 2>&1 &
```
