"""Eligible token validation for competition compliance."""

import json
from pathlib import Path
from typing import Optional

from config import ELIGIBLE_TOKENS_PATH


class TokenValidator:
    """Validates trades against the 149 eligible BEP-20 token whitelist."""

    def __init__(self, tokens_path: Optional[Path] = None):
        path = tokens_path or ELIGIBLE_TOKENS_PATH
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw_tokens: list[str] = data["tokens"]
        self._raw_tokens = raw_tokens
        self._tokens: set[str] = {t.upper() for t in raw_tokens}
        self._original: dict[str, str] = {t.upper(): t for t in raw_tokens}

    @property
    def eligible_tokens(self) -> list[str]:
        return list(self._original.values())

    @property
    def count(self) -> int:
        """Total entries in official list (149 per competition rules)."""
        return len(self._raw_tokens)

    @property
    def unique_count(self) -> int:
        return len(self._tokens)

    def is_eligible(self, symbol: str) -> bool:
        return symbol.upper() in self._tokens

    def normalize(self, symbol: str) -> Optional[str]:
        return self._original.get(symbol.upper())

    def validate_pair(self, from_token: str, to_token: str) -> tuple[bool, str]:
        """Validate both sides of a trade. Returns (valid, reason)."""
        from_ok = self.is_eligible(from_token)
        to_ok = self.is_eligible(to_token)

        if not from_ok and not to_ok:
            return False, f"Both tokens ineligible: {from_token}, {to_token}"
        if not from_ok:
            return False, f"FROM token not eligible: {from_token}"
        if not to_ok:
            return False, f"TO token not eligible: {to_token}"
        return True, "Both tokens eligible"

    def validate_signal(self, token: str) -> tuple[bool, str]:
        if self.is_eligible(token):
            return True, f"{token} is eligible"
        return False, f"Token not in eligible list: {token}"
