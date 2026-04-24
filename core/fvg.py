from typing import Optional
import pandas as pd
import config
from core.models import FVG


def find_fvg(
    df_m5: pd.DataFrame,
    bias: str,
    atr_value: float,
    lookback: int = config.FVG_LOOKBACK,
) -> Optional[FVG]:
    """
    Detect the most recent valid Fair Value Gap on M15.

    Bullish FVG:  candle[n-2].high < candle[n].low
        gap_size  = candle[n].low - candle[n-2].high
        midpoint  = candle[n-2].high + gap_size / 2

    Bearish FVG:  candle[n-2].low > candle[n].high
        gap_size  = candle[n-2].low - candle[n].high
        midpoint  = candle[n].high + gap_size / 2

    Quality guard: gap_size >= MIN_FVG_ATR_RATIO × ATR
    Returns the most recent qualifying FVG.
    """
    tail = df_m5.tail(lookback).reset_index(drop=True)
    min_gap = config.MIN_FVG_ATR_RATIO * atr_value

    # Scan from most recent backwards (n = last 3-bar window)
    for n in range(len(tail) - 1, 1, -1):
        c1 = tail.iloc[n - 2]   # oldest of the 3 candles
        # c2 = tail.iloc[n - 1]  # middle (not used directly)
        c3 = tail.iloc[n]        # newest

        if bias == "bullish":
            if c1["high"] < c3["low"]:
                gap_size = float(c3["low"]) - float(c1["high"])
                if gap_size >= min_gap:
                    midpoint = float(c1["high"]) + gap_size / 2.0
                    offset = max(0, len(df_m5) - lookback)
                    return FVG(
                        top=float(c3["low"]),
                        bottom=float(c1["high"]),
                        midpoint=round(midpoint, 5),
                        kind="bullish",
                        candle_index=offset + n,
                    )

        elif bias == "bearish":
            if c1["low"] > c3["high"]:
                gap_size = float(c1["low"]) - float(c3["high"])
                if gap_size >= min_gap:
                    midpoint = float(c3["high"]) + gap_size / 2.0
                    offset = max(0, len(df_m5) - lookback)
                    return FVG(
                        top=float(c1["low"]),
                        bottom=float(c3["high"]),
                        midpoint=round(midpoint, 5),
                        kind="bearish",
                        candle_index=offset + n,
                    )

    return None
