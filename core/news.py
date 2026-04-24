from datetime import datetime, timedelta, timezone
from typing import List, Tuple
import config


def _event_affects_symbol(event: dict, symbol: str) -> bool:
    """Check if an economic event involves any of the symbol's currencies."""
    currencies = config.SYMBOL_CURRENCIES.get(symbol, [])
    event_currency = event.get("country", "").upper()
    # ForexFactory uses country field like "USD", "EUR", "GBP", "JPY", "CHF"
    return event_currency in currencies


def _is_high_impact(event: dict) -> bool:
    """Filter to High impact events containing known keywords."""
    impact = event.get("impact", "").lower()
    if impact != "high":
        return False
    title = event.get("title", "").upper()
    for kw in config.HIGH_IMPACT_KEYWORDS:
        if kw.upper() in title:
            return True
    return False


def _parse_event_time(event: dict) -> Optional[datetime]:
    """Parse event date string to UTC datetime."""
    try:
        from dateutil import parser as dtparser
        dt = dtparser.parse(event["date"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def is_news_blackout(
    symbol: str,
    dt_utc: datetime,
    events: List[dict],
) -> Tuple[bool, str]:
    """
    Returns (True, event_title) if dt_utc falls within the blackout window
    of any high-impact event that affects the symbol's currencies.
    Otherwise returns (False, "").
    """
    before = timedelta(minutes=config.NEWS_BLACKOUT_BEFORE_MINS)
    after  = timedelta(minutes=config.NEWS_BLACKOUT_AFTER_MINS)

    for event in events:
        if not _is_high_impact(event):
            continue
        if not _event_affects_symbol(event, symbol):
            continue

        event_time = _parse_event_time(event)
        if event_time is None:
            continue

        if dt_utc.tzinfo is None:
            dt_check = dt_utc.replace(tzinfo=timezone.utc)
        else:
            dt_check = dt_utc

        blackout_start = event_time - before
        blackout_end   = event_time + after

        if blackout_start <= dt_check <= blackout_end:
            return True, event.get("title", "High Impact News")

    return False, ""


# Avoid circular import — dateutil is not always available; provide fallback
try:
    from dateutil import parser as _dtparser
except ImportError:
    _dtparser = None


def _parse_event_time(event: dict):  # noqa: F811
    """Parse ISO datetime string, with fallback if dateutil not installed."""
    raw = event.get("date", "")
    if not raw:
        return None
    try:
        if _dtparser is not None:
            dt = _dtparser.parse(raw)
        else:
            # Fallback: assume format "YYYY-MM-DDTHH:MM:SS+00:00" or similar
            raw_clean = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
