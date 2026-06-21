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
  → confluence_engine entry_signal (min ATR 2% → LOW_CONVICTION, then CHOPPY_RANGE chop filter)
  → momentum / sweep / FVG paths
  → pre_trade_checklist (R:R, spread, volume)
  → should_enter (BSC gas > 8 gwei → HIGH_GAS, strategy only)
  → ADX Kelly scaler on position size
  → correlation_guard
  → russian_doll_risk
  → token_validator.is_eligible()
  → risk_manager.validate_trade()
  → MIN_TRADE_USD ($2) check
  → TWAK execute (USDT → token)
  → ... on exit ...
  → TWAK execute (token → USDT)
  → checkpoint save (data/agent_checkpoint.json)
```

## Submission — risk guards (DoraHacks / judges)

| Guard | Purpose |
|-------|---------|
| **Min ATR 2%** | Skips flat/low-vol tokens before signal paths (`LOW_CONVICTION`) — tournament config |
| **Gas defer (8 gwei)** | Defers discretionary entries when BSC gas is high; qualification trades bypass |
| **ADX Kelly scaler** | Smaller positions in weak trends (ADX &lt; 25); avoids over-betting chop |
| **Chop filter** | Skips tight ranges (`ATR/close &lt; 1.5%` + ADX &lt; 25) before other gates |
| **Russian Doll** | Progressive de-risk 8% / 12%; hard halt 20% (tournament) |
| **0.5% min pct / $2 min USD** | Confluence rejects tiny % sizes; `MIN_TRADE_USD=2` blocks on-chain entries below $2 |
| **149-token whitelist** | Competition compliance on every leg |
| **Session checkpoint** | Resumes positions and daily trade count after laptop restart |

Both swap legs run through TWAK with slippage protection. Failed exit swaps defer to the next cycle.

Rejected trades logged in activity feed with reason.

## Pre-Launch Checklist

- [ ] `bash scripts/competition_preflight.sh` passes
- [ ] `twak compete status` shows registered
- [ ] Wallet funded (BNB gas + USDT)
- [ ] `CMC_API_KEY` set for live data
- [ ] Paper run shows `CYCLE` logs every 15 min
- [ ] Competition dry-run: `--mode competition --dry-run --live-cmc --duration 10h` → `logs/dry_run.log`
- [ ] Dry-run logs show guards working (`LOW_CONVICTION`, `HIGH_GAS` when applicable)
- [ ] Checkpoint resume: restart same command → `CHECKPOINT restored` in log
- [ ] Non-eligible tokens blocked (`POST /api/validate-token`)
- [ ] Dashboard at :3000 shows agent state
- [ ] Wallet password backed up securely

## Competition Start

```bash
# Option A: dedicated competition process
export AGENT_MODE=competition
nohup backend/.venv/bin/python -u -m tradi.agent \
  --mode competition \
  --config config/tournament_week.yaml \
  --live-cmc \
  --duration 168h \
  >> logs/competition.log 2>&1 &

# Option B: paper agent with COMPETITION_AUTO_SWITCH=true (flips at COMPETITION_START UTC)
nohup backend/.venv/bin/python -u -m tradi.agent \
  --mode paper \
  --config config/production.yaml \
  --live-cmc \
  --duration 168h \
  >> logs/full_system.log 2>&1 &
```
