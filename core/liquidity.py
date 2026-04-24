from typing import List, Dict
from datetime import datetime, date
import pandas as pd
import numpy as np
import config
from core.models import LiquidityLevel
from core.swing import get_recent_swings, get_swing_highs, get_swing_lows


def get_previous_day_levels(df_d1: pd.DataFrame) -> Dict[str, float]:
    """Returns PDH and PDL from the fully closed previous daily candle."""
    if len(df_d1) < 2:
        return {}
    prev = df_d1.iloc[-2]
    return {"PDH": float(prev["high"]), "PDL": float(prev["low"])}


def get_asia_session_range(df_h1: pd.DataFrame, now_utc: datetime) -> Dict:
    """
    Filters H1 bars belonging to the current day's Asia session (00:00-09:00 UTC).
    Only uses bars already closed (bar time < now_utc).
    """
    today = now_utc.date()
    mask = (
        df_h1["time"].dt.date == today
    ) & (
        df_h1["time"].dt.hour < config.ASIA_SESSION_UTC[1]
    ) & (
        df_h1["time"] < pd.Timestamp(now_utc)
    )
    asia_bars = df_h1[mask]

    if asia_bars.empty:
        return {"AsiaHigh": None, "AsiaLow": None, "valid": False}

    return {
        "AsiaHigh": float(asia_bars["high"].max()),
        "AsiaLow":  float(asia_bars["low"].min()),
        "valid": True,
    }


def _cluster_prices(
    prices: np.ndarray,
    tolerance_pct: float,
    min_touches: int,
    max_cluster_pct: float,
) -> List[float]:
    """Cluster prices within tolerance. Returns level prices for clusters meeting min_touches."""
    n = len(prices)
    if n == 0:
        return []

    used = [False] * n
    levels = []

    for i in range(n):
        if used[i]:
            continue
        cluster = [prices[i]]
        for j in range(i + 1, n):
            if not used[j]:
                ref = prices[i]
                if ref != 0 and abs(prices[i] - prices[j]) / abs(ref) <= tolerance_pct:
                    cluster.append(prices[j])
                    used[j] = True
        used[i] = True

        if len(cluster) < min_touches:
            continue
        if len(cluster) / n > max_cluster_pct:
            continue  # noise — entire range is a "level"
        levels.append(float(np.mean(cluster)))

    return levels


def find_equal_highs(
    df: pd.DataFrame,
    tolerance_pct: float = config.EQUAL_HL_TOLERANCE_PCT,
    min_touches: int = config.EQUAL_HL_MIN_TOUCHES,
    lookback: int = config.EQUAL_HL_LOOKBACK,
) -> List[LiquidityLevel]:
    tail = df.tail(lookback)
    prices = tail["high"].values
    levels = _cluster_prices(
        prices, tolerance_pct, min_touches, config.EQUAL_HL_MAX_CLUSTER_PCT
    )
    ts = str(tail["time"].iloc[-1]) if "time" in tail.columns else ""
    return [
        LiquidityLevel(price=p, kind="EqualHigh", timestamp=ts, touch_count=min_touches)
        for p in levels
    ]


def find_equal_lows(
    df: pd.DataFrame,
    tolerance_pct: float = config.EQUAL_HL_TOLERANCE_PCT,
    min_touches: int = config.EQUAL_HL_MIN_TOUCHES,
    lookback: int = config.EQUAL_HL_LOOKBACK,
) -> List[LiquidityLevel]:
    tail = df.tail(lookback)
    prices = tail["low"].values
    levels = _cluster_prices(
        prices, tolerance_pct, min_touches, config.EQUAL_HL_MAX_CLUSTER_PCT
    )
    ts = str(tail["time"].iloc[-1]) if "time" in tail.columns else ""
    return [
        LiquidityLevel(price=p, kind="EqualLow", timestamp=ts, touch_count=min_touches)
        for p in levels
    ]


def get_h1_swing_levels(df_h1: pd.DataFrame, max_levels: int = 4) -> List[LiquidityLevel]:
    """
    Returns recent H1 swing highs and lows as liquidity levels.
    These are the primary ICT targets swept before a reversal move.
    Takes the most recent max_levels swing highs and max_levels swing lows.
    """
    swings = get_recent_swings(df_h1, n=config.H1_SWING_N, lookback_bars=60)
    highs = get_swing_highs(swings)
    lows  = get_swing_lows(swings)
    levels: List[LiquidityLevel] = []
    ts = str(df_h1["time"].iloc[-1]) if "time" in df_h1.columns else ""
    for sh in highs[-max_levels:]:
        levels.append(LiquidityLevel(price=sh.price, kind="H1SwingHigh", timestamp=ts))
    for sl in lows[-max_levels:]:
        levels.append(LiquidityLevel(price=sl.price, kind="H1SwingLow", timestamp=ts))
    return levels


def get_all_liquidity_levels(
    df_d1: pd.DataFrame,
    df_h1: pd.DataFrame,
    df_m5: pd.DataFrame,
    now_utc: datetime,
) -> List[LiquidityLevel]:
    """Aggregates all liquidity levels: PDH/PDL, Asia range, H1 swings, Equal Highs/Lows."""
    levels: List[LiquidityLevel] = []
    ts = now_utc.isoformat()

    # Previous Day
    pd_lvls = get_previous_day_levels(df_d1)
    if "PDH" in pd_lvls:
        levels.append(LiquidityLevel(price=pd_lvls["PDH"], kind="PDH", timestamp=ts))
        levels.append(LiquidityLevel(price=pd_lvls["PDL"], kind="PDL", timestamp=ts))

    # Asia session range
    asia = get_asia_session_range(df_h1, now_utc)
    if asia["valid"]:
        levels.append(LiquidityLevel(price=asia["AsiaHigh"], kind="AsiaHigh", timestamp=ts))
        levels.append(LiquidityLevel(price=asia["AsiaLow"],  kind="AsiaLow",  timestamp=ts))

    # H1 swing highs/lows (primary ICT liquidity targets)
    levels.extend(get_h1_swing_levels(df_h1))

    # Equal Highs/Lows on M5
    levels.extend(find_equal_highs(df_m5))
    levels.extend(find_equal_lows(df_m5))

    return levels
