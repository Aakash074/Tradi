# Tradi Architecture — V3

## System Overview

Tradi runs as a continuous async loop (15-minute cycles) on FastAPI:

```
CMC Data → Regime Filter → Confluence Scan → Pre-Trade Checklist → Risk → TWAK Execute → Dashboard
```

Entry point: `python -m tradi.agent` (`tradi/agent/__main__.py`) or `uvicorn main:app` with external orchestrator.

## Components

### Backend (`backend/`)

| Module | Role |
|--------|------|
| `agent/orchestrator.py` | Main loop, position exits, TWAK execution, daily enforcer, `MIN_TRADE_USD` |
| `agent/confluence_engine.py` | **V3 brain** — regime, momentum, sweep, FVG, checklist, gas defer |
| `agent/checkpoint.py` | Session save/load (`data/agent_checkpoint.json`) |
| `agent/exit_manager.py` | Asymmetric 1.5:4.5 (prod) / 1.5:6 (tournament) exits + trailing |
| `agent/competition_scheduler.py` | Auto-switch paper ↔ competition at UTC window |
| `agent/russian_doll_risk.py` | Drawdown tiers and halt |
| `agent/token_selector.py` | Top-N momentum universe |
| `agent/trade_enforcer.py` | Daily qualification trades after 20:00 UTC |
| `agent/correlation_guard.py` | Correlation filter for new positions |
| `strategies/regime_filter.py` | DEFENSIVE / NORMAL / AGGRESSIVE |
| `strategies/microstructure.py` | Momentum pullback V3 (ADX, EMA, RSI, volume) |
| `strategies/kelly_sizing.py` | Dynamic / aggressive position sizing |
| `data/twak_wrapper.py` | TWAK CLI — wallet, swaps, competition register |
| `data/cmchub_client.py` | CMC prices/OHLCV (+ mock fallback in paper) |
| `data/bsc_gas.py` | BSC `eth_gasPrice` for strategy-entry deferral (90s cache) |
| `data/bnb_sdk.py` | ERC-8004 identity stub + on-chain log buffer |
| `validation/token_validator.py` | 149 eligible token whitelist |
| `tournament_config.py` | Loads `production.yaml` / `tournament_week.yaml` |

Legacy (not in main path): `market_state_adapter.py`, `whale_shadow.py`, `momentum_breakout.py`, `ghost_tracker.py`.

### Frontend (`frontend/`)

Next.js 14 App Router — polls `GET /api/dashboard` for regime, positions, confluence data, heatmap, correlation matrix.

## Data Flow (each cycle)

1. **Refresh** regime + top momentum universe (`token_selector`)
2. **Scan** eligible tokens through `confluence_engine.scan_all()`
   - Min ATR filter (tournament) → historical context → sweep / FVG / momentum paths
   - Pre-trade checklist (R:R, spread, volume)
3. **Filter** by `should_enter()` (gas defer, Russian Doll, correlation, min strength 0.6)
4. **Execute** up to 4 new positions via TWAK (paper sim or live); skip if trade &lt; $2 USD
5. **Manage** open positions — stop, take-profit, trailing, 48h max hold
6. **Enforce** daily trade if after 20:00 UTC and zero trades today (qualification bypasses gas)
7. **Checkpoint** portfolio + positions to `data/agent_checkpoint.json`
8. **Expose** state via `/api/dashboard`

## Config

| File | Mode | Exits | Halt | Extra |
|------|------|-------|------|-------|
| `config/production.yaml` | Paper / dev | 1.5:4.5 | 25% | Dynamic sizing |
| `config/tournament_week.yaml` | Competition | 1.5:6.0 | 20% | Aggressive sizing, min ATR 2%, max gas 8 gwei |

`AGENT_MODE=competition` or `COMPETITION_AUTO_SWITCH=true` loads tournament config for the competition window (UTC).

## Deployment

```bash
# Recommended: agent + API together
python -m tradi.agent --mode paper --config config/production.yaml --live-cmc --duration 168h

# Or split (not recommended — dashboard won't sync agent state)
uvicorn main:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev

# Competition preflight
bash scripts/competition_preflight.sh
```

- Logs: `logs/full_system.log` (paper), `logs/dry_run.log` (competition dry-run), `logs/competition.log` (live)
- Checkpoint: `data/agent_checkpoint.json` (gitignored; survives restarts)

## Backtest Pipeline

```
scripts/backtest.py → backend/backtest/momentum_backtest.py → results/tradi_backtest.json
scripts/plot_backtest.py → results/tradi_backtest_v3.png
```

Separate legacy runner: `python -m backtest` (90d, old engine) — **not** V3 results.
