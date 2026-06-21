# Tradi — Autonomous V3 Trading Agent

**Tradi** is an autonomous trading agent for **BNB Hackathon Track 1** (June 22–28, 2026). It trades spot on BNB Chain via TWAK, using only the **149 eligible BEP-20 tokens** on PancakeSwap V2/V3.

**Strategy:** V3 Momentum Pullback Confluence — ADX-filtered pullbacks with liquidity sweep / FVG overlays, asymmetric exits, and Russian Doll risk.

**Backtest (2y, synthetic sim):** +26.44% return, Sharpe 1.83, 6.75% max drawdown on **tournament-style params** (`1.5:6.0` exits, aggressive sizing, ADX 20) — see `results/tradi_backtest_v3.png`. **Live competition performance varies;** the backtest engine uses **synthetic OHLCV**, not historical Binance/CMC replay. Production paper config (`production.yaml`) backtests lower (~+18%) on the same simulator.

## Features

- **V3 confluence engine** — Regime filter + momentum pullback + sweep/FVG/checklist gates
- **Entry guards** — Min ATR 2% (tournament), ADX Kelly scaler, choppy-range filter, BSC gas defer (strategy only)
- **Asymmetric exits** — 1.5% stop / 4.5% target (production), 1.5% / 6% (tournament)
- **Competition compliance** — 149-token whitelist, 25% max position, daily enforcer at 20:00 UTC
- **Hard risk gates** — Russian Doll drawdown tiers, daily loss limit, correlation guard
- **TWAK integration** — Self-custody wallet, swap execution, competition registration
- **Live CMC data** — Real OHLCV/prices with `CMC_API_KEY` + `--live-cmc`
- **Real-time dashboard** — Next.js 14 UI (regime, Kelly, heatmap, correlation)
- **Backtest + chart** — `scripts/backtest.py`, `scripts/plot_backtest.py`

## Quick Start

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh

cp .env.example .env   # set CMC_API_KEY, TWAK_AGENT_PASSWORD

# Run agent + API (recommended)
python -m tradi.agent \
  --mode paper \
  --config config/production.yaml \
  --live-cmc \
  --duration 48h

# Dashboard (separate terminal)
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — API at [http://localhost:8000](http://localhost:8000).

## Agent CLI

```bash
python -m tradi.agent --help

# Paper (production config) — auto-flips to competition at COMPETITION_START (UTC)
python -m tradi.agent --mode paper --config config/production.yaml --live-cmc --duration 168h

# Competition week (manual; or rely on COMPETITION_AUTO_SWITCH=true)
python -m tradi.agent --mode competition --config config/tournament_week.yaml --live-cmc --duration 168h

# Competition dry-run (paper swaps + real wallet sync, no gas)
python -m tradi.agent --mode competition --config config/tournament_week.yaml --live-cmc --dry-run --duration 10h

# Dry-run — survives terminal close (recommended before Jun 22)
nohup backend/.venv/bin/python -u -m tradi.agent \
  --mode competition --config config/tournament_week.yaml --live-cmc --dry-run --duration 168h \
  >> logs/dry_run.log 2>&1 &

# Production paper — survives terminal close
nohup backend/.venv/bin/python -u -m tradi.agent \
  --mode paper --config config/production.yaml --live-cmc --duration 168h \
  >> logs/full_system.log 2>&1 &
```

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `paper` | `paper` \| `competition` \| `live` |
| `--config` | `config/production.yaml` | YAML strategy/risk config |
| `--live-cmc` | off | Use live CoinMarketCap API |
| `--dry-run` | off | Paper swaps + real TWAK wallet sync (no gas) |
| `--duration` | `48h` | Session length (`6h`, `1d`, etc.) |
| `--serve-api` | on | FastAPI dashboard on :8000 |

## Configuration

Copy `.env.example` to `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `TWAK_AGENT_PASSWORD` | Competition | Password from `twak wallet create` |
| `CMC_API_KEY` | Recommended | Live prices (`--live-cmc`); OHLCV uses Binance klines fallback on Basic plan |
| `TWAK_ACCESS_ID` / `TWAK_HMAC_SECRET` | Optional | TWAK hosted API credentials |
| `AGENT_MODE` | — | `paper` (default) or `competition` |
| `COMPETITION_START` / `COMPETITION_END` | — | UTC window for auto-switch (ISO-8601, `Z` suffix) |
| `COMPETITION_AUTO_SWITCH` | `true` | Flip paper → competition at start, back at end (no restart) |
| `COMPETITION_DRY_RUN` | — | Paper swaps + real wallet sync (`--dry-run`) |
| `X402_ENABLED` | — | USDC micropayments for CMC premium MCP (`--x402`) |
| `ADVISORY_GATE_*` | — | Optional veto-only trade review (fail-open) |
| `DATABASE_URL` | — | `sqlite+aiosqlite:///./tradi.db` (default) |

BNB Agent SDK is open-source (`bnbagent`) — uses TWAK wallet password, not an API key.

## Competition Readiness

```bash
# Install TWAK
curl -fsSL https://agent-kit.trustwallet.com/install.sh | bash

# Wallet + register (before June 22 UTC)
twak wallet create --password <secure>
twak compete register --password <secure>
twak compete status

# Preflight check
bash scripts/competition_preflight.sh
```

## Backtest

Simulated 2-year runs (`scripts/backtest.py`) use **synthetic candles** — useful for config comparison, not live PnL guarantees.

```bash
# Tournament week params (closest to +26.44% headline)
python scripts/backtest.py \
  --strategy momentum_pullback_v3 \
  --asymmetric_exits 1.5:6.0 --adx_filter 20 --sizing aggressive \
  --start 2024-01-01 --end 2026-01-01 \
  --output results/tradi_backtest_tournament.yaml.json

# Production paper params
python scripts/backtest.py \
  --strategy momentum_pullback_v3 \
  --asymmetric_exits 1.5:4.5 --adx_filter 20 --sizing dynamic \
  --start 2024-01-01 --end 2026-01-01 \
  --output results/tradi_backtest_production.yaml.json

python scripts/plot_backtest.py --also-backend
# → results/tradi_backtest_v3.png
```

## Submission notes (risk awareness)

| Guard | Location | Behavior |
|-------|----------|----------|
| **Min ATR** | `entry_signal()`, `tournament_week.yaml` | Rejects flat coins when `ATR/close < 2%` (`LOW_CONVICTION`) — tournament only |
| **Gas defer** | `should_enter()`, `data/bsc_gas.py` | Defers strategy entries when BSC gas > 8 gwei (`HIGH_GAS`); qualification bypasses |
| **ADX Kelly scaler** | `strategies/kelly_sizing.py`, `entry_signal()` | `adx_scale = min(ADX/25, 1.0)` — 0.8× size at ADX 20, full size at 25+; 0.5% minimum blocks uneconomic trades |
| **Chop filter** | `entry_signal()` | Rejects when `ATR/close < 1.5%` and `ADX < 25` (`CHOPPY_RANGE`) |
| **Min trade USD** | `orchestrator.py` | Skips on-chain entries below `$2` (`MIN_TRADE_USD`) — micro-wallet protection |
| **Russian Doll** | `russian_doll_risk.py` | Size tiers at 8% / 12% DD; halt at 20% (tournament) or 25% (production) |
| **Daily enforcer** | `trade_enforcer.py` | Qualification trade after 20:00 UTC if no trades that day (5% size, bypasses gas gate) |
| **Checkpoint** | `agent/checkpoint.py` | Resumes open positions and `trades_today` after restart (`data/agent_checkpoint.json`) |

## Monitoring

Agent state is checkpointed after each cycle to `data/agent_checkpoint.json` (open positions, `trades_today`, portfolio). On restart with the same `--mode` and `--config`, the session resumes automatically.

```bash
tail -f logs/dry_run.log | grep -E "CYCLE|TRADE|EXIT|HALT|HIGH_GAS|LOW_CONVICTION|CHECKPOINT"
tail -f logs/full_system.log | grep -E "CYCLE|TRADE|EXIT|HALT|DRAWDOWN|DAILY"
python scripts/monitor.py --watch
```

Structured log tags: `TRADE_EXECUTED`, `EXIT_EXECUTED`, `EXIT_DEFERRED`, `SELL_FAILED`, `HALT`, `DRAWDOWN`, `DAILY`, `HIGH_GAS`, `LOW_CONVICTION`, `ERROR`.

## On-chain execution (Track 1)

Tradi uses **TWAK for both entry and exit** so competition PnL reflects real wallet balances:

```
Entry:  USDT ──TWAK swap──► token     (TRADE_EXECUTED)
Exit:   token ──TWAK swap──► USDT    (EXIT_EXECUTED)
```

| Mode | Buys | Sells |
|------|------|-------|
| **Paper** | Simulated TWAK swap | Simulated TWAK swap |
| **Competition / live** | Real BSC tx via `twak swap` | Real BSC tx via `twak swap` |
| **Dry-run** (`--dry-run`) | Simulated | Simulated (wallet balance sync only) |

Exit triggers: stop-loss, take-profit, trailing stop, 48h max hold, profit-protection trim.  
Failed sells retry next cycle (`EXIT_DEFERRED`) — position stays open until the swap succeeds.

See `docs/STRATEGIES.md` for exit rules and R:R config.

## Project Structure

```
Tradi/
├── config/
│   ├── production.yaml       # Paper / production V3
│   └── tournament_week.yaml  # Competition week
├── backend/agent/
│   ├── confluence_engine.py  # V3 brain
│   ├── orchestrator.py       # Main loop
│   ├── checkpoint.py         # Session resume on restart
│   ├── exit_manager.py       # 1.5% / 4.5% exits
│   └── ...
├── backend/data/bsc_gas.py   # BSC gas price (strategy deferral)
├── frontend/                 # Next.js dashboard
├── scripts/
│   ├── backtest.py
│   ├── plot_backtest.py
│   └── competition_preflight.sh
├── results/tradi_backtest.json
├── ELIGIBLE_TOKENS.json      # 149 tokens
└── docs/
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/dashboard` | Full agent state |
| `GET /api/health` | Health check |
| `GET /api/risk` | Risk and circuit breakers |
| `GET /api/eligible-tokens` | 149 token whitelist |
| `POST /api/agent/cycle` | Run one trading cycle |
| `POST /api/validate-token?symbol=CAKE` | Check token eligibility |

## Testing

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/ -v
```

## Modes

| Mode | Swaps | Data | Config |
|------|-------|------|--------|
| **Paper** | Simulated TWAK (entry + exit) | Live CMC if `--live-cmc`, else mock OHLCV | `production.yaml` |
| **Competition** | Real TWAK on BSC (entry + exit) | Live CMC | `tournament_week.yaml` (auto if `AGENT_MODE=competition`) |
| **Live** | Same as competition | Live | User-defined |

## License

Built for BNB Hackathon Track 1 — June 2026.
