"""External advisory gate — veto-only review, fail-open if unreachable."""

import json
import logging
from typing import Any, Optional

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class AdvisoryGate:
    """
    Optional external reviewer that may only BLOCK trades, never initiate them.
    If the API is unavailable or misconfigured, trades proceed (fail-open).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.advisory_gate_api_key or settings.openai_api_key
        self.model = model or settings.advisory_gate_model
        self.enabled = enabled if enabled is not None else settings.advisory_gate_enabled
        if self.enabled and not self.api_key:
            logger.info("Advisory gate enabled but no API key — running fail-open")
            self.enabled = False

    async def should_block(
        self,
        token: str,
        signal_data: dict[str, Any],
        market_context: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Ask whether to skip this trade.
        Returns (True, reason) to block, (False, "") to proceed.
        """
        if not self.enabled:
            return False, ""

        prompt = f"""You are a risk manager reviewing a crypto trade.

Trade: {token}
Signal: {json.dumps(signal_data, default=str)}
Market: {json.dumps(market_context, default=str)}

Question: Should we SKIP this trade? Reply with ONLY "YES" or "NO".
YES = skip trade
NO = proceed with trade"""

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    OPENAI_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 10,
                        "temperature": 0,
                    },
                )
                resp.raise_for_status()
                body = resp.json()

            answer = (
                body.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
                .upper()
            )
            if "YES" in answer and "NO" not in answer:
                logger.info("Advisory gate blocked %s (response=%s)", token, answer)
                return True, "ADVISORY_BLOCK"
            return False, ""

        except Exception as e:
            logger.warning("Advisory gate unreachable for %s — fail-open: %s", token, e)
            return False, ""

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "model": self.model if self.enabled else None,
        }
