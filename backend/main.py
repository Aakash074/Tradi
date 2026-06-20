"""Tradi FastAPI application."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.orchestrator import TradiOrchestrator
from config import get_settings
from validation.token_validator import TokenValidator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

orchestrator: Optional[TradiOrchestrator] = None
agent_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    orchestrator = TradiOrchestrator()
    await orchestrator.initialize()
    logger.info("Tradi backend started")
    yield
    if orchestrator:
        orchestrator.stop()
    if agent_task and not agent_task.done():
        agent_task.cancel()
    logger.info("Tradi backend stopped")


app = FastAPI(
    title="Tradi Trading Agent",
    description="Autonomous multi-strategy trading agent for BNB Hackathon",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ManualTradeRequest(BaseModel):
    token_from: str
    token_to: str
    amount_usd: float


@app.get("/")
async def root():
    return {"name": "Tradi", "status": "running", "version": "1.0.0"}


@app.get("/api/health")
async def health():
    return {"status": "healthy", "agent": orchestrator is not None}


@app.get("/api/dashboard")
async def dashboard():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    return await orchestrator.get_full_state()


@app.get("/api/portfolio")
async def portfolio():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    return orchestrator.portfolio.to_dict()


@app.get("/api/risk")
async def risk_status():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    portfolio = orchestrator.portfolio.to_dict()
    status = orchestrator.risk.get_status()
    return {
        **status,
        "drawdown_pct": portfolio["drawdown_pct"],
        "daily_pnl_pct": portfolio["daily_pnl_pct"],
        "max_drawdown_dq": get_settings().max_drawdown_dq * 100,
    }


@app.get("/api/eligible-tokens")
async def eligible_tokens():
    validator = TokenValidator()
    return {"count": validator.count, "tokens": validator.eligible_tokens}


@app.post("/api/validate-token")
async def validate_token(symbol: str):
    validator = TokenValidator()
    valid, reason = validator.validate_signal(symbol)
    return {"symbol": symbol, "eligible": valid, "reason": reason}


@app.post("/api/agent/start")
async def start_agent(background_tasks: BackgroundTasks):
    global agent_task
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    if agent_task and not agent_task.done():
        return {"status": "already_running"}
    agent_task = asyncio.create_task(orchestrator.run_loop())
    return {"status": "started"}


@app.post("/api/agent/stop")
async def stop_agent():
    global agent_task
    if orchestrator:
        orchestrator.stop()
    if agent_task and not agent_task.done():
        agent_task.cancel()
        agent_task = None
    return {"status": "stopped"}


@app.post("/api/agent/cycle")
async def run_cycle():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    return await orchestrator.run_cycle()


@app.post("/api/agent/initialize")
async def initialize_agent():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    return await orchestrator.initialize()


@app.get("/api/strategies/regime")
async def regime_status():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    from strategies.regime_detection import get_regime_strategy_label

    regime = orchestrator.regime_switcher.current_regime
    return {
        "current_regime": regime.value,
        "active_strategy": get_regime_strategy_label(regime),
        "regime_display": f"Market State: {regime.value} — Using {get_regime_strategy_label(regime)}",
        "pending_regime": orchestrator.regime_switcher.pending_regime.value
        if orchestrator.regime_switcher.pending_regime
        else None,
        "metrics": orchestrator._regime_metrics,
    }


@app.get("/api/strategies/whales")
async def whale_status():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    return orchestrator.whale_shadow.get_whale_stats()


@app.get("/api/strategies/momentum")
async def momentum_status():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    return orchestrator.momentum_breakout.get_stats()


@app.post("/api/risk/reset")
async def reset_hard_halt():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    reset = orchestrator.risk.manual_reset()
    return {"reset": reset, "status": orchestrator.risk.get_status()}


@app.get("/api/activity")
async def activity_log():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    return orchestrator._activity_log


@app.get("/api/trades")
async def trade_history():
    if not orchestrator:
        raise HTTPException(503, "Agent not initialized")
    return orchestrator._trade_history
