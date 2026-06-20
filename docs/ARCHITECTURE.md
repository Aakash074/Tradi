# Tradi Architecture

## System Overview

Tradi operates as a continuous async loop on FastAPI:

```
Data Ingestion → Signal Generation → Risk Validation → TWAK Execution → Monitoring → Dashboard
```

## Components

### Backend (`backend/`)

| Module | Role |
|--------|------|
| `agent/orchestrator.py` | Main loop, strategy selection, keepalive trades |
| `agent/regime_switcher.py` | Strategy 1 — ADX/ATR/Bollinger regime detection |
| `agent/whale_shadow.py` | Strategy 2 — Smart money copy trading |
| `agent/yield_optimizer.py` | Strategy 3 — PancakeSwap LP yield |
| `agent/risk_manager.py` | Circuit breakers and position limits |
| `data/twak_wrapper.py` | TWAK CLI integration |
| `data/cmchub_client.py` | CMC data + x402 payments |
| `data/bnb_sdk.py` | ERC-8004 identity and on-chain logs |
| `validation/token_validator.py` | 149 eligible token whitelist |

### Frontend (`frontend/`)

Next.js 14 App Router with real-time polling of `/api/dashboard`.

## Data Flow

1. Every 15 minutes, orchestrator runs all three strategies in parallel
2. Signals filtered by token eligibility (both FROM and TO)
3. Best opportunity selected by `(expected_return × confidence) / risk`
4. Risk manager validates drawdown, daily limits, position size
5. TWAK executes swap on PancakeSwap (spot only)
6. BNB SDK logs trade on-chain
7. Dashboard updates via REST API

## Deployment

- Backend: `uvicorn main:app --host 0.0.0.0 --port 8000`
- Frontend: `npm run build && npm start`
- Database: SQLite (default) or PostgreSQL via `DATABASE_URL`
