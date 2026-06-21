"""Tests for CMC hub client quote parsing."""

from data.cmchub_client import CMCHubClient


def test_parse_quote_price_ton_cmc_casing():
    """CMC returns key 'Ton' when querying symbol=TON."""
    payload = {
        "data": {
            "Ton": {
                "symbol": "Ton",
                "quote": {"USD": {"price": 22.414513419487704}},
            }
        }
    }
    assert CMCHubClient._parse_quote_price(payload, "TON") == 22.414513419487704


def test_parse_quote_price_exact_symbol_key():
    payload = {
        "data": {
            "CAKE": {
                "symbol": "CAKE",
                "quote": {"USD": {"price": 2.45}},
            }
        }
    }
    assert CMCHubClient._parse_quote_price(payload, "CAKE") == 2.45


def test_parse_quote_price_missing_returns_none():
    assert CMCHubClient._parse_quote_price({"data": {}}, "TON") is None
