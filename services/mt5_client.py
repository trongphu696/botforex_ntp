"""
MetaTrader5 client — connection management and candle data fetching.
All returned DataFrames use UTC-aware timestamps and have the forming (current)
candle stripped so callers only work with fully closed bars.
"""

import time
from typing import Dict
import pandas as pd
import config

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

TIMEFRAME_MAP = {}

def _build_timeframe_map():
    global TIMEFRAME_MAP
    if not MT5_AVAILABLE:
        return
    TIMEFRAME_MAP = {
        "D1":  mt5.TIMEFRAME_D1,
        "H4":  mt5.TIMEFRAME_H4,
        "H1":  mt5.TIMEFRAME_H1,
        "M15": mt5.TIMEFRAME_M15,
        "M5":  mt5.TIMEFRAME_M5,
        "M1":  mt5.TIMEFRAME_M1,
    }


def initialize() -> None:
    """
    Connect to MT5. Reads login credentials from environment via config.
    Retries up to 3 times with 2-second delays.
    Raises RuntimeError on persistent failure.
    """
    if not MT5_AVAILABLE:
        raise RuntimeError("MetaTrader5 package not installed. Run: pip install MetaTrader5")

    _build_timeframe_map()

    kwargs = {}
    if config.MT5_LOGIN:
        kwargs["login"] = int(config.MT5_LOGIN)
    if config.MT5_PASSWORD:
        kwargs["password"] = config.MT5_PASSWORD
    if config.MT5_SERVER:
        kwargs["server"] = config.MT5_SERVER

    for attempt in range(1, 4):
        if mt5.initialize(**kwargs):
            return
        err = mt5.last_error()
        if attempt < 3:
            time.sleep(2)
        else:
            raise RuntimeError(f"MT5 initialize failed after 3 attempts. Last error: {err}")


def shutdown() -> None:
    if MT5_AVAILABLE and mt5:
        mt5.shutdown()


def get_candles(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    """
    Fetch `count` closed candles for `symbol` at `timeframe`.
    Returns DataFrame with columns: [time, open, high, low, close, volume].
    The forming (current) candle is stripped.
    Retries up to 3 times on None result.
    """
    if not MT5_AVAILABLE:
        raise RuntimeError("MetaTrader5 not available")

    mt5_symbol = config.MT5_SYMBOL_MAP.get(symbol, symbol)
    tf = TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    # Ensure symbol is in Market Watch
    if not mt5.symbol_select(mt5_symbol, True):
        raise RuntimeError(f"Cannot select symbol {mt5_symbol}: {mt5.last_error()}")

    rates = None
    for attempt in range(3):
        rates = mt5.copy_rates_from_pos(mt5_symbol, tf, 0, count + 1)
        if rates is not None:
            break
        time.sleep(0.5)

    if rates is None:
        raise RuntimeError(
            f"Failed to fetch {symbol}/{timeframe} candles: {mt5.last_error()}"
        )

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df[["time", "open", "high", "low", "close", "tick_volume"]].rename(
        columns={"tick_volume": "volume"}
    )
    # Strip the forming candle (last bar is still open)
    df = df.iloc[:-1].reset_index(drop=True)
    return df


def get_all_timeframes(symbol: str) -> Dict[str, pd.DataFrame]:
    """Fetch D1, H4, H1, M5 for a symbol in one call."""
    return {
        "D1": get_candles(symbol, "D1", config.D1_COUNT),
        "H4": get_candles(symbol, "H4", config.H4_COUNT),
        "H1": get_candles(symbol, "H1", config.H1_COUNT),
        "M5": get_candles(symbol, "M5", config.M5_COUNT),
    }


def get_current_price(symbol: str) -> float:
    """Returns the current mid-price (bid+ask)/2 for the symbol."""
    if not MT5_AVAILABLE:
        return 0.0
    mt5_symbol = config.MT5_SYMBOL_MAP.get(symbol, symbol)
    tick = mt5.symbol_info_tick(mt5_symbol)
    if tick is None:
        return 0.0
    return round((tick.bid + tick.ask) / 2, 5)
