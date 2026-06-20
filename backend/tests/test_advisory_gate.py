"""Tests for advisory gate (veto-only, fail-open)."""

import asyncio
from unittest.mock import AsyncMock, patch

from agent.advisory_gate import AdvisoryGate


def test_fail_open_when_disabled():
    gate = AdvisoryGate(api_key="test", enabled=False)

    async def run():
        return await gate.should_block("CAKE", {"type": "STANDARD"}, {"regime": "NORMAL"})

    blocked, reason = asyncio.run(run())
    assert blocked is False
    assert reason == ""


def test_fail_open_on_api_error():
    gate = AdvisoryGate(api_key="test-key", enabled=True)

    async def run():
        with patch("agent.advisory_gate.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("network down")
            )
            return await gate.should_block("ETH", {"type": "FVG_MOMENTUM"}, {})

    blocked, _ = asyncio.run(run())
    assert blocked is False


def test_blocks_on_yes_response():
    gate = AdvisoryGate(api_key="test-key", enabled=True)
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {"choices": [{"message": {"content": "YES"}}]}

    async def run():
        with patch("agent.advisory_gate.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
            return await gate.should_block("DOGE", {"type": "STANDARD"}, {"regime": "NORMAL"})

    blocked, reason = asyncio.run(run())
    assert blocked is True
    assert reason == "ADVISORY_BLOCK"


def test_proceeds_on_no_response():
    gate = AdvisoryGate(api_key="test-key", enabled=True)
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: {"choices": [{"message": {"content": "NO"}}]}

    async def run():
        with patch("agent.advisory_gate.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
            return await gate.should_block("BNB", {"type": "LIQUIDITY_SWEEP"}, {})

    blocked, _ = asyncio.run(run())
    assert blocked is False
