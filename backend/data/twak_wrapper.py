"""Trust Wallet Agent Kit (TWAK) integration wrapper."""

import asyncio
import logging
import re
import subprocess
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from config import get_settings

logger = logging.getLogger(__name__)

STABLECOINS = frozenset({"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD"})
BALANCE_LINE = re.compile(
    r"(?:(?P<sym>[A-Za-z0-9]{2,12})\s*[:=]\s*(?P<amt1>\d+(?:\.\d+)?))"
    r"|(?:(?P<amt2>\d+(?:\.\d+)?)\s+(?P<sym2>[A-Za-z0-9]{2,12}))"
)


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

    def _uses_paper_swaps(self) -> bool:
        return self.settings.agent_mode == "paper" or self.settings.competition_dry_run

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
        if self._uses_paper_swaps() and self.settings.agent_mode == "paper":
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

        if self.settings.agent_mode == "paper" and not self.settings.competition_dry_run:
            self._wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
            return self._wallet_address

        ok, output = self._run_twak(["wallet", "address", "--chain", "smartchain"])
        if ok:
            self._wallet_address = output.strip()
        return self._wallet_address

    async def register_competition(self) -> tuple[bool, str]:
        if self._uses_paper_swaps() and self.settings.agent_mode == "paper":
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
        if self._uses_paper_swaps():
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
        if self._uses_paper_swaps():
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

    async def execute_with_slippage_protection(
        self, from_token: str, to_token: str, amount: float, vol_24h: float = 0.02
    ) -> Union[SwapResult, str]:
        """MEV-aware execution with dynamic slippage and price impact check."""
        slippage = 1.0 if vol_24h > 0.05 else 0.5  # percent

        quote = await self.get_swap_quote(from_token, to_token, amount)
        if not quote:
            return "REJECTED_NO_QUOTE"

        if quote.price_impact > 0.02:
            logger.warning("Rejected: price impact %.2f%% > 2%%", quote.price_impact * 100)
            return "REJECTED_HIGH_IMPACT"

        return await self.execute_swap(quote.quote_id, slippage=slippage)

    async def get_wallet_balance_usd(
        self,
        price_fn: Callable[[str], Awaitable[float]],
    ) -> float:
        """Sum TWAK wallet token balances converted to USD."""
        if self.settings.agent_mode == "paper" and not self.settings.competition_dry_run:
            return 0.0

        ok, output = self._run_twak(["wallet", "balance", "--chain", "smartchain"])
        if not ok:
            logger.warning("Wallet balance query failed: %s", output)
            return 0.0

        return await self._parse_balance_to_usd(output, price_fn)

    async def _parse_balance_to_usd(
        self,
        output: str,
        price_fn: Callable[[str], Awaitable[float]],
    ) -> float:
        holdings: dict[str, float] = {}
        for line in output.splitlines():
            for match in BALANCE_LINE.finditer(line):
                sym = (match.group("sym") or match.group("sym2") or "").upper()
                amt_str = match.group("amt1") or match.group("amt2")
                if not sym or not amt_str:
                    continue
                try:
                    amt = float(amt_str)
                except ValueError:
                    continue
                if amt <= 0:
                    continue
                holdings[sym] = holdings.get(sym, 0.0) + amt

        if not holdings:
            logger.warning("Could not parse wallet balance output: %s", output[:200])
            return 0.0

        total = 0.0
        for sym, amt in holdings.items():
            if sym in STABLECOINS:
                total += amt
                continue
            try:
                price = await price_fn(sym)
                total += amt * price
            except Exception as e:
                logger.warning("Skipping %s balance in wallet USD total: %s", sym, e)

        logger.info(
            "Wallet balance parsed: %s → $%.2f",
            ", ".join(f"{s}={a:.6g}" for s, a in sorted(holdings.items())),
            total,
        )
        return total

    async def x402_request(self, endpoint: str, max_payment: float = 0.01) -> tuple[bool, str]:
        if self._uses_paper_swaps() and self.settings.agent_mode == "paper":
            return False, "Paper mode: x402 payment skipped"

        ok, output = self._run_twak(
            ["x402", "request", endpoint, "--max-payment", str(max_payment), "--auto-approve"]
        )
        return ok, output

    async def x402_fetch_url(self, url: str, max_payment: float = 0.01) -> tuple[bool, str]:
        """Pay for a full CMC x402 URL via TWAK wallet (Base USDC)."""
        return await asyncio.to_thread(self._x402_fetch_url_sync, url, max_payment)

    def _x402_fetch_url_sync(self, url: str, max_payment: float) -> tuple[bool, str]:
        if self.settings.competition_dry_run:
            return False, "Dry run: x402 payment skipped"
        if self._uses_paper_swaps() and self.settings.agent_mode == "paper":
            return False, "Paper mode: x402 payment skipped"

        args = ["x402", "request", url, "--max-payment", str(max_payment), "--auto-approve"]
        if self.settings.twak_agent_password:
            args.extend(["--password", self.settings.twak_agent_password])
        return self._run_twak(args)

    @property
    def is_registered(self) -> bool:
        return self._registered
