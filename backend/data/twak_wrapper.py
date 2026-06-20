"""Trust Wallet Agent Kit (TWAK) integration wrapper."""

import asyncio
import logging
import subprocess
import uuid
from dataclasses import dataclass
from typing import Optional

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SwapQuote:
    quote_id: str
    from_token: str
    to_token: str
    from_amount: float
    to_amount: float
    price_impact: float
    gas_estimate: float


@dataclass
class SwapResult:
    success: bool
    tx_hash: Optional[str]
    from_token: str
    to_token: str
    from_amount: float
    to_amount: float
    error: Optional[str] = None


class TWAKWrapper:
    """Wraps TWAK CLI for wallet management and swap execution."""

    def __init__(self):
        self.settings = get_settings()
        self._wallet_address: Optional[str] = None
        self._registered = False
        self._paper_quotes: dict[str, SwapQuote] = {}

    def _run_twak(self, args: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["twak", *args],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip() or result.stdout.strip()
        except FileNotFoundError:
            logger.warning("TWAK CLI not found, using paper mode")
            return False, "TWAK CLI not installed"
        except subprocess.TimeoutExpired:
            return False, "TWAK command timed out"

    async def create_wallet(self) -> tuple[bool, str]:
        if self.settings.agent_mode == "paper":
            self._wallet_address = "0x" + uuid.uuid4().hex[:40]
            return True, self._wallet_address

        ok, output = self._run_twak(
            ["wallet", "create", "--password", self.settings.twak_agent_password]
        )
        if ok:
            self._wallet_address = output.split()[-1] if output else None
        return ok, output

    async def get_wallet_address(self) -> Optional[str]:
        if self._wallet_address:
            return self._wallet_address

        if self.settings.agent_mode == "paper":
            self._wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
            return self._wallet_address

        ok, output = self._run_twak(["wallet", "address", "--chain", "smartchain"])
        if ok:
            self._wallet_address = output.strip()
        return self._wallet_address

    async def register_competition(self) -> tuple[bool, str]:
        if self.settings.agent_mode == "paper":
            self._registered = True
            return True, "Paper mode: competition registration simulated"

        ok, output = self._run_twak(
            ["compete", "register", "--password", self.settings.twak_agent_password]
        )
        if ok:
            self._registered = True
        return ok, output

    async def get_swap_quote(
        self, from_token: str, to_token: str, amount: float
    ) -> Optional[SwapQuote]:
        if self.settings.agent_mode == "paper":
            quote_id = str(uuid.uuid4())
            quote = SwapQuote(
                quote_id=quote_id,
                from_token=from_token,
                to_token=to_token,
                from_amount=amount,
                to_amount=amount * 0.998,
                price_impact=0.002,
                gas_estimate=0.0003,
            )
            self._paper_quotes[quote_id] = quote
            return quote

        ok, output = self._run_twak(
            ["swap", "quote", "--from", from_token, "--to", to_token, "--amount", str(amount)]
        )
        if not ok:
            logger.error("Swap quote failed: %s", output)
            return None
        quote_id = str(uuid.uuid4())
        return SwapQuote(
            quote_id=quote_id,
            from_token=from_token,
            to_token=to_token,
            from_amount=amount,
            to_amount=amount,
            price_impact=0.003,
            gas_estimate=0.0005,
        )

    async def execute_swap(self, quote_id: str, slippage: float = 0.5) -> SwapResult:
        if self.settings.agent_mode == "paper":
            quote = self._paper_quotes.get(quote_id)
            if not quote:
                return SwapResult(
                    success=False,
                    tx_hash=None,
                    from_token="",
                    to_token="",
                    from_amount=0,
                    to_amount=0,
                    error="Quote not found",
                )
            tx_hash = "0x" + uuid.uuid4().hex
            await asyncio.sleep(0.5)
            return SwapResult(
                success=True,
                tx_hash=tx_hash,
                from_token=quote.from_token,
                to_token=quote.to_token,
                from_amount=quote.from_amount,
                to_amount=quote.to_amount,
            )

        ok, output = self._run_twak(
            ["swap", "execute", "--quote-id", quote_id, "--slippage", str(slippage)]
        )
        if ok:
            return SwapResult(
                success=True,
                tx_hash=output.strip(),
                from_token="",
                to_token="",
                from_amount=0,
                to_amount=0,
            )
        return SwapResult(
            success=False,
            tx_hash=None,
            from_token="",
            to_token="",
            from_amount=0,
            to_amount=0,
            error=output,
        )

    async def x402_request(self, endpoint: str, max_payment: float = 0.01) -> tuple[bool, str]:
        if self.settings.agent_mode == "paper":
            return True, f"Paper x402 request to {endpoint}"

        ok, output = self._run_twak(
            ["x402", "request", endpoint, "--max-payment", str(max_payment), "--auto-approve"]
        )
        return ok, output

    @property
    def is_registered(self) -> bool:
        return self._registered
