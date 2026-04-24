"""
ForexFactory economic calendar fetcher.
Caches the weekly calendar in memory for NEWS_CACHE_TTL seconds.
On fetch failure, returns the stale cache or an empty list (non-blocking).
"""

import time
import requests
import config

_cache: dict = {"data": [], "fetched_at": 0.0}


def get_events() -> list:
    """
    Returns a list of economic event dicts from ForexFactory.
    Refreshes if cache is older than NEWS_CACHE_TTL.
    """
    now = time.time()
    if now - _cache["fetched_at"] < config.NEWS_CACHE_TTL and _cache["data"]:
        return _cache["data"]

    try:
        resp = requests.get(config.NEWS_CALENDAR_URL, timeout=5)
        resp.raise_for_status()
        events = resp.json()
        _cache["data"] = events if isinstance(events, list) else []
        _cache["fetched_at"] = now
        return _cache["data"]
    except Exception as exc:
        # Non-blocking: return stale data or empty list
        print(f"[news_feed] Warning: failed to fetch calendar — {exc}")
        return _cache.get("data", [])


def force_refresh() -> list:
    """Force a fresh fetch regardless of cache TTL."""
    _cache["fetched_at"] = 0.0
    return get_events()
