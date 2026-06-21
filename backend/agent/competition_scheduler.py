"""Auto-switch agent mode on COMPETITION_START / COMPETITION_END (UTC)."""

from datetime import datetime, timezone
from typing import Optional

from config import Settings


def parse_competition_timestamp(value: str) -> datetime:
    """Parse ISO-8601 timestamps; ``Z`` suffix is treated as UTC."""
    normalized = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def competition_bounds(settings: Settings) -> tuple[datetime, datetime]:
    start = parse_competition_timestamp(settings.competition_start)
    end = parse_competition_timestamp(settings.competition_end)
    return start, end


def scheduled_agent_mode(
    settings: Settings,
    cli_mode: str,
    now: Optional[datetime] = None,
) -> str:
    """
    Target mode from the competition window when auto-switch is enabled.

    Before COMPETITION_START: keep the CLI mode (paper pre-warm or early competition dry-run).
    During the window: competition.
    After COMPETITION_END: paper (live mode is left unchanged).
    """
    if not settings.competition_auto_switch:
        return settings.agent_mode

    now = now or datetime.now(timezone.utc)
    start, end = competition_bounds(settings)

    if now > end:
        return "live" if cli_mode == "live" else "paper"

    if start <= now <= end:
        return "competition"

    return cli_mode
