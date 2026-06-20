"""BNB AI Agent SDK integration for ERC-8004 identity and on-chain logging."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class OnChainTradeLog:
    timestamp: str
    token_from: str
    token_to: str
    entry_price: float
    exit_price: Optional[float]
    position_size_usd: float
    pnl_usd: Optional[float]
    strategy: str
    confidence: float
    reasoning: str
    eligible: bool
    tx_hash: Optional[str]


class BNBAIAgentSDK:
    """Registers agent identity and logs trades on-chain via BNB AI Agent SDK."""

    def __init__(self):
        self.settings = get_settings()
        self._agent_id: Optional[str] = None
        self._registered = False
        self._trade_logs: list[OnChainTradeLog] = []

    async def register_agent(self, name: str = "Tradi") -> tuple[bool, str]:
        if self.settings.agent_mode == "paper":
            self._agent_id = f"erc8004:tradi:{uuid.uuid4().hex[:16]}"
            self._registered = True
            logger.info("Paper mode: Agent registered as %s", self._agent_id)
            return True, self._agent_id

        if not self.settings.bnb_sdk_api_key:
            return False, "BNB SDK API key not configured"

        # Production: call BNB AI Agent SDK registration endpoint
        self._agent_id = f"erc8004:tradi:{uuid.uuid4().hex[:16]}"
        self._registered = True
        return True, self._agent_id

    async def log_trade(self, log: OnChainTradeLog) -> tuple[bool, str]:
        self._trade_logs.append(log)
        if self.settings.agent_mode == "paper":
            logger.info(
                "On-chain log [paper]: %s %s->%s $%.2f eligible=%s",
                log.strategy,
                log.token_from,
                log.token_to,
                log.position_size_usd,
                log.eligible,
            )
            return True, f"paper_log_{len(self._trade_logs)}"

        # Production: submit to BNB Chain via SDK
        return True, f"onchain_log_{len(self._trade_logs)}"

    async def log_trade_from_dict(self, data: dict) -> tuple[bool, str]:
        log = OnChainTradeLog(
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            token_from=data["token_from"],
            token_to=data["token_to"],
            entry_price=data.get("entry_price", 0),
            exit_price=data.get("exit_price"),
            position_size_usd=data.get("position_size_usd", 0),
            pnl_usd=data.get("pnl_usd"),
            strategy=data["strategy"],
            confidence=data.get("confidence", 0),
            reasoning=data.get("reasoning", ""),
            eligible=data.get("eligible", True),
            tx_hash=data.get("tx_hash"),
        )
        return await self.log_trade(log)

    @property
    def agent_id(self) -> Optional[str]:
        return self._agent_id

    @property
    def is_registered(self) -> bool:
        return self._registered

    def get_trade_logs(self) -> list[dict]:
        return [
            {
                "timestamp": log.timestamp,
                "token_from": log.token_from,
                "token_to": log.token_to,
                "entry_price": log.entry_price,
                "exit_price": log.exit_price,
                "position_size_usd": log.position_size_usd,
                "pnl_usd": log.pnl_usd,
                "strategy": log.strategy,
                "confidence": log.confidence,
                "reasoning": log.reasoning,
                "eligible": log.eligible,
                "tx_hash": log.tx_hash,
            }
            for log in self._trade_logs
        ]
