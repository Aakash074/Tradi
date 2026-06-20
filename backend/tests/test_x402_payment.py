"""Tests for x402 payment parsing."""

import base64
import json

import httpx

from data.x402_payment import X402Payment


def test_parse_payment_required_base64():
    payload = {
        "x402Version": 2,
        "accepts": [{"amount": "10000", "network": "eip155:8453"}],
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    headers = httpx.Headers({"Payment-Required": encoded})
    parsed = X402Payment.parse_payment_required(headers)
    assert parsed is not None
    assert parsed["accepts"][0]["amount"] == "10000"


def test_payment_amount_usd_from_quote():
    req = {"accepts": [{"amount": "10000"}]}
    assert X402Payment._payment_amount_usd(req, 0.01) == 0.01


def test_x402_disabled_returns_none():
    import asyncio

    payer = X402Payment(enabled=False)

    async def run():
        return await payer.pay_for_data("https://example.com/x402/v1/test")

    assert asyncio.run(run()) is None
