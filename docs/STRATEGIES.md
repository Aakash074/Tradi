# Tradi Strategies — V3 Momentum Pullback Confluence

Single-strategy agent with layered entry filters. Legacy three-strategy blend (Market State / Whale Shadow / Momentum Breakout) is **not** used in the main path.

## Backtest (2024-01-01 → 2026-01-01)

> **Disclaimer:** Backtests use **synthetic OHLCV** (seeded simulation), not historical market replay. **Live competition PnL varies** with slippage, gas, and regime. The +26.44% headline aligns with **tournament** params below; production config simulates ~+18% on the same engine.

### Tournament week (`tournament_week.yaml`) — competition config

| Metric | Result (synthetic sim) | Target |
|--------|------------------------|--------|
| Total return | +26.94% | — |
| Sharpe | 1.89 | > 1.8 ✓ |
| Max drawdown | 2.99% | < 15% ✓ |
| Win rate | 40.3% | > 48% |
| Profit factor | 1.17 | > 1.6 |
| Expectancy / trade | 0.231% | > 0.15% ✓ |

Config: `1.5:6.0` exits, ADX 20, **aggressive** sizing, **min ATR 2%**, **max gas 8 gwei** (strategy defer), 20% halt.

```bash
python scripts/backtest.py --strategy momentum_pullback_v3 \
  --asymmetric_exits 1.5:6.0 --adx_filter 20 --sizing aggressive \
  --start 2024-01-01 --end 2026-01-01 \
  --output results/tradi_backtest_tournament.yaml.json
```

### Production paper (`production.yaml`)

| Metric | Result (synthetic sim) |
|--------|------------------------|
| Total return | +18.28% |
| Sharpe | 1.29 |

Config: `1.5:4.5` exits, ADX 20, dynamic sizing, 25% halt.

```bash
python scripts/backtest.py --strategy momentum_pullback_v3 \
  --asymmetric_exits 1.5:4.5 --adx_filter 20 --sizing dynamic \
  --start 2024-01-01 --end 2026-01-01 \
  --output results/tradi_backtest_production.yaml.json
python scripts/plot_backtest.py --also-backend
```

Chart (legacy baseline run): `results/tradi_backtest_v3.png` (+26.44%, Sharpe 1.83 — archived `results/tradi_backtest.json`, ADX 25 / 1.5:4.5 dynamic).

---

## Layer 1: Regime Filter (`strategies/regime_filter.py`)

| Mode | Condition | Action |
|------|-----------|--------|
| DEFENSIVE | Vol ratio > 1.5 or Fear & Greed < 20 | Hold cash — no new entries |
| NORMAL | Default | Trade normally |
| AGGRESSIVE | Low vol + greed | Trade normally (larger dynamic sizes) |

Fear & Greed source chain: CMC MCP → Pro API → **alternative.me** → mock fallback.

---

## Layer 2: Core Signal (`strategies/microstructure.py`)

**Momentum pullback V3** — buy pullbacks in uptrends:

1. **Trend** — Price > EMA20 and ADX > threshold (20 in both YAML configs)
2. **Pullback** — RSI between 30 and 50
3. **Volume** — Current bar > 1.2× 20-bar average
4. **Min ATR** (`entry_signal`, tournament) — Reject `LOW_CONVICTION` when `ATR/close < 2%` (blocks flat coins)
5. **Chop filter** (`entry_signal`) — Reject `CHOPPY_RANGE` when `ATR/close < 1.5%` and `ADX < 25`
6. **Standard path** — Reject if ADX < 20 on momentum-only entries

Signal strength ≥ 0.6 required. Up to **4 signals per cycle**.

---

## Layer 3: Confluence Entry Paths (`agent/confluence_engine.py`)

Evaluated in order; first match wins, then pre-trade checklist:

| Path | Condition | Strategy tag |
|------|-----------|----------------|
| **Liquidity sweep** | EMA20 stop-hunt + volume spike + recovery (quality > 0.7) | `LIQUIDITY_SWEEP` |
| **FVG + momentum** | Near unmitigated Fair Value Gap + momentum_ok | `FVG_MOMENTUM` |
| **Standard** | momentum_ok + historical context confidence ≥ 0.6 | `STANDARD` |

Supporting modules:

- `agent/historical_context.py` — 5h trend/volume/volatility (can be disabled for testing)
- `agent/liquidity_sweep.py` — Stop-hunt detection below EMA20
- `agent/fvg_detector.py` — Bullish/bearish FVG zones
- `agent/pre_trade_checklist.py` — Spread, R:R ≥ 2:1, volume, technical stop
- `agent/correlation_guard.py` — Blocks correlated new positions

---

## Token Universe (`agent/token_selector.py`)

When `universe: top_20_momentum` in config:

- Ranks eligible tokens by 24h momentum
- Refreshes every 15 minutes (900s cache)
- Production config uses top-50 scan for broader coverage during testing

---

## Position Sizing (`strategies/kelly_sizing.py`)

**Dynamic** (production) or **aggressive** (tournament):

| Mode | Behavior |
|------|----------|
| `dynamic` | Vol-adjusted, ~4% base, max 5%, scaled by regime and drawdown |
| `aggressive` | 4% base, max 5%, tournament week |

**ADX Kelly scaler:** `adx_scale = min(ADX / 25, 1.0)` applied to checklist Kelly size and `dynamic_sizing()` — 0.8× at ADX 20, full size at ADX 25+. Positions below **0.5%** of account are rejected (uneconomic vs fees).

Russian Doll multiplier reduces size at 8% / 12% drawdown tiers.

**Min trade size:** Positions below **0.5%** of account are rejected in confluence; `orchestrator.py` also blocks entries below **$2 USD** (`MIN_TRADE_USD`) for BSC gas economics.

---

## Gas defer (`data/bsc_gas.py` + `should_enter()`)

Tournament config sets `execution.max_gas_gwei: 8` (~$0.50–$0.80/swap on BSC).

| Path | Gas check |
|------|-----------|
| **Strategy entries** | `should_enter()` fetches BSC `eth_gasPrice` (90s cache); rejects with `HIGH_GAS` if > 8 gwei |
| **Qualification trades** | Bypass `should_enter()` — enforcer calls `execute_signal()` directly |
| **RPC failure** | Fail-open (no defer) so transient RPC issues do not block entries |

---

## Exits (`agent/exit_manager.py` + `agent/orchestrator.py`)

| Config | Stop | Target | R:R |
|--------|------|--------|-----|
| **Production** (`production.yaml`) | 1.5% | 4.5% | 1:3 |
| **Tournament** (`tournament_week.yaml`) | 1.5% | 6.0% | 1:4 |

- Trailing stop activates at **+3%**, trails **1%** below high
- ATR can tighten stop (never widen beyond configured %)
- 48-hour max hold in orchestrator

### On-chain execution (competition / live)

Every exit is a **real TWAK swap** so wallet PnL matches hackathon scoring:

| Event | TWAK swap | Log tag |
|-------|-----------|---------|
| **Entry** | `USDT → token` | `TRADE_EXECUTED` |
| **Full exit** (stop / target / time) | `token → USDT` | `EXIT_EXECUTED` |
| **Profit-protection trim** | partial `token → USDT` | `PROFIT_PROTECTION` |

Flow each cycle:

1. Update prices → check stop / target / trailing / 48h max hold
2. On trigger, sell full position via `execute_with_slippage_protection(token, USDT, market_value_usd)`
3. Record `exit_tx_hash`, update portfolio cash, log to BNB SDK
4. If swap fails → position stays open with `exit_pending`; **retries next cycle**

**Paper mode** uses the same code path with simulated TWAK swaps (fake tx hashes).  
**Competition mode** submits real BSC transactions — both legs count toward live PnL.

Slippage protection matches entries: dynamic slippage from 24h vol, reject if price impact > 2%.

---

## Risk (`agent/russian_doll_risk.py`)

| Drawdown | Action |
|----------|--------|
| 8% | 50% size, max 3 positions |
| 12% | 25% size, max 2 positions |
| 20% (tournament) / 25% (production) | Trading halted |

Daily loss limit: **5%** (config). Competition DQ at **30%** drawdown.

---

## Daily Trade Enforcer (`agent/trade_enforcer.py`)

After **20:00 UTC**, if `trades_today == 0`:

1. Force strongest signal from scan, or
2. Qualification trade on lowest-ATR eligible token at **5%** (`forced_size: 0.05` in tournament config — ~$2.50 on a $50 wallet)

Qualification trades **bypass** the gas defer gate (required for daily compliance).

---

## Session checkpoint (`agent/checkpoint.py`)

After each cycle, agent state is saved to `data/agent_checkpoint.json` (open positions, portfolio, `trades_today`, enforcer flags). Restart with the same `--mode` and `--config` to resume without losing session context.

---

## Config Files

| File | Use |
|------|-----|
| `config/production.yaml` | Paper / production: 1.5:4.5, ADX 20, dynamic sizing, 25% halt |
| `config/tournament_week.yaml` | Competition: 1.5:6.0, ADX 20, aggressive sizing, min ATR 2%, max gas 8 gwei, 20% halt, 5% enforcer |

Loaded via `backend/tournament_config.py` → `TournamentConfig`.

**Competition auto-switch:** With `COMPETITION_AUTO_SWITCH=true`, a paper agent flips to `tournament_week.yaml` at `COMPETITION_START` (UTC) and back at `COMPETITION_END` without restart.
