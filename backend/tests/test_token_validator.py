"""Unit tests for token eligibility validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation.token_validator import TokenValidator


def test_eligible_tokens_count():
    v = TokenValidator()
    assert v.count == 149


def test_eligible_token():
    v = TokenValidator()
    assert v.is_eligible("CAKE")
    assert v.is_eligible("cake")
    assert v.is_eligible("ETH")


def test_ineligible_token():
    v = TokenValidator()
    assert not v.is_eligible("PEPE")
    assert not v.is_eligible("UNKNOWN")


def test_validate_pair_both_eligible():
    v = TokenValidator()
    valid, reason = v.validate_pair("CAKE", "USDT")
    assert valid
    assert "eligible" in reason.lower()


def test_validate_pair_one_ineligible():
    v = TokenValidator()
    valid, reason = v.validate_pair("PEPE", "USDT")
    assert not valid
    assert "PEPE" in reason
