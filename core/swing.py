from typing import List
import pandas as pd
import numpy as np
import config
from core.models import SwingPoint


def detect_swings(df: pd.DataFrame, n: int = 3) -> List[SwingPoint]:
    """
    Vectorized n-bar pivot detection.
    A swing HIGH at index i: df.high[i] is strictly greater than all bars in [i-n, i+n].
    A swing LOW  at index i: df.low[i]  is strictly less    than all bars in [i-n, i+n].
    Last n bars are excluded (unconfirmed — need future bars).
    """
    if len(df) < 2 * n + 1:
        return []

    highs = df["high"].values
    lows  = df["low"].values
    times = df["time"] if "time" in df.columns else df.index

    window = 2 * n + 1
    roll_max = pd.Series(highs).rolling(window, center=True).max().values
    roll_min = pd.Series(lows).rolling(window, center=True).min().values

    swings: List[SwingPoint] = []
    end = len(df) - n  # exclude last n (unconfirmed)

    for i in range(n, end):
        ts = str(times.iloc[i]) if hasattr(times, "iloc") else str(times[i])

        # Swing HIGH: bar high equals the rolling max AND strictly > all neighbors
        if highs[i] == roll_max[i]:
            left_max  = highs[max(0, i-n):i].max() if i > 0 else -np.inf
            right_max = highs[i+1:i+n+1].max() if i+1 < len(df) else -np.inf
            if highs[i] > left_max and highs[i] > right_max:
                swings.append(SwingPoint(index=i, price=highs[i], kind="high", timestamp=ts))

        # Swing LOW: bar low equals the rolling min AND strictly < all neighbors
        if lows[i] == roll_min[i]:
            left_min  = lows[max(0, i-n):i].min() if i > 0 else np.inf
            right_min = lows[i+1:i+n+1].min() if i+1 < len(df) else np.inf
            if lows[i] < left_min and lows[i] < right_min:
                swings.append(SwingPoint(index=i, price=lows[i], kind="low", timestamp=ts))

    return swings


def get_recent_swings(df: pd.DataFrame, n: int, lookback_bars: int = 50) -> List[SwingPoint]:
    """Detect swings in the last `lookback_bars` rows only."""
    sliced = df.tail(lookback_bars).reset_index(drop=True)
    offset = max(0, len(df) - lookback_bars)
    swings = detect_swings(sliced, n)
    for s in swings:
        s.index += offset
    return swings


def get_swing_highs(swings: List[SwingPoint]) -> List[SwingPoint]:
    return [s for s in swings if s.kind == "high"]


def get_swing_lows(swings: List[SwingPoint]) -> List[SwingPoint]:
    return [s for s in swings if s.kind == "low"]
