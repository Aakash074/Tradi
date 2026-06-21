"""Tests for UTC competition auto-switch scheduling."""

from datetime import datetime, timezone

from agent.competition_scheduler import (
    competition_bounds,
    parse_competition_timestamp,
    scheduled_agent_mode,
)
from config import Settings


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


def test_parse_competition_timestamp_z_suffix():
    dt = parse_competition_timestamp("2026-06-22T00:00:00Z")
    assert dt == datetime(2026, 6, 22, 0, 0, 0, tzinfo=timezone.utc)


def test_scheduled_mode_before_start_keeps_cli_mode():
    settings = _settings(competition_auto_switch=True, agent_mode="paper")
    before = datetime(2026, 6, 21, 23, 59, 59, tzinfo=timezone.utc)
    assert scheduled_agent_mode(settings, cli_mode="paper", now=before) == "paper"


def test_scheduled_mode_at_start_flips_to_competition():
    settings = _settings(competition_auto_switch=True, agent_mode="paper")
    start = datetime(2026, 6, 22, 0, 0, 0, tzinfo=timezone.utc)
    assert scheduled_agent_mode(settings, cli_mode="paper", now=start) == "competition"


def test_scheduled_mode_during_window_is_competition():
    settings = _settings(competition_auto_switch=True, agent_mode="paper")
    mid = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
    assert scheduled_agent_mode(settings, cli_mode="paper", now=mid) == "competition"


def test_scheduled_mode_after_end_returns_paper():
    settings = _settings(competition_auto_switch=True, agent_mode="competition")
    after = datetime(2026, 6, 29, 0, 0, 0, tzinfo=timezone.utc)
    assert scheduled_agent_mode(settings, cli_mode="paper", now=after) == "paper"


def test_scheduled_mode_respects_auto_switch_disabled():
    settings = _settings(competition_auto_switch=False, agent_mode="paper")
    mid = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
    assert scheduled_agent_mode(settings, cli_mode="paper", now=mid) == "paper"


def test_competition_bounds():
    settings = _settings()
    start, end = competition_bounds(settings)
    assert start == datetime(2026, 6, 22, 0, 0, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 6, 28, 23, 59, 59, tzinfo=timezone.utc)
