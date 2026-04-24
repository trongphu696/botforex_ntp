from datetime import datetime
from typing import Optional, Tuple
import config


def is_valid_session(symbol: str, dt_utc: datetime) -> Tuple[bool, str]:
    """
    Returns (True, session_name) if dt_utc falls within any valid trading
    session window for the given symbol, else (False, "").
    """
    hour = dt_utc.hour
    windows = config.SESSION_WINDOWS.get(symbol, [])

    matched = []
    for (start, end) in windows:
        if start <= hour < end:
            name = config.SESSION_NAMES.get((start, end), f"{start:02d}-{end:02d} UTC")
            matched.append(name)

    if not matched:
        return False, ""

    # Combine overlapping session names (e.g. London + NY overlap)
    return True, " / ".join(dict.fromkeys(matched))


def get_active_sessions(dt_utc: datetime) -> list:
    """Returns list of all session names active at dt_utc (regardless of symbol)."""
    hour = dt_utc.hour
    active = []
    for (start, end), name in config.SESSION_NAMES.items():
        if start <= hour < end:
            active.append(name)
    return active
