from typing import List, Tuple
from datetime import datetime, timedelta, timezone
import config
from core.models import Signal


def _is_active(signal: Signal, now_utc: datetime, hours: int = config.ANTISPAM_HOURS) -> bool:
    """Returns True if the signal was sent within the last `hours` hours."""
    try:
        from dateutil import parser as dtparser
        ts = dtparser.parse(signal.timestamp)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return False

    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    return (now_utc - ts) < timedelta(hours=hours)


def get_active_signals(signals: List[Signal], now_utc: datetime) -> List[Signal]:
    return [s for s in signals if s.status == "open" and _is_active(s, now_utc)]


def is_correlated_blocked(
    new_symbol: str,
    active_signals: List[Signal],
    new_direction: str = "",
) -> Tuple[bool, str]:
    """
    Hard blocks:
      - EURUSD ↔ USDCHF: any active signal on either blocks the other.
      - GBPUSD ↔ EURUSD: if same direction, block (positive correlation).

    Soft block (returns False but reason is non-empty for logging):
      - XAUUSD with any active USD-pair signal.
    """
    active_symbols = {s.symbol: s for s in active_signals}

    # Hard block: EURUSD / USDCHF
    for pair in config.CORRELATED_PAIRS:
        if new_symbol in pair:
            other = pair[0] if pair[1] == new_symbol else pair[1]
            if other in active_symbols:
                return True, f"Correlation block: {new_symbol} conflicts with active {other}"

    # Soft block: XAUUSD vs USD pairs
    if config.XAUUSD_USD_SOFT_BLOCK and new_symbol == "XAUUSD":
        usd_pairs = [s for sym, s in active_symbols.items() if sym != "XAUUSD" and "USD" in sym]
        if usd_pairs:
            names = ", ".join(s.symbol for s in usd_pairs)
            # Not a hard block — return False but populate reason for Telegram note
            return False, f"Soft correlation note: XAUUSD with active {names}"

    return False, ""
