from typing import List, Optional
import pandas as pd
import config
from core.models import LiquidityLevel, SweepEvent

# Priority order for sweep detection (higher priority = picked first at same index)
_BUY_KINDS  = ("PDL", "AsiaLow", "H1SwingLow", "EqualLow")
_SELL_KINDS = ("PDH", "AsiaHigh", "H1SwingHigh", "EqualHigh")


def _kind_priority(kind: str, direction: str) -> int:
    order = _BUY_KINDS if direction == "bullish" else _SELL_KINDS
    return order.index(kind) if kind in order else 99


def detect_sweep(
    df_m5: pd.DataFrame,
    liquidity_levels: List[LiquidityLevel],
    bias: str,
) -> Optional[SweepEvent]:
    """
    Scan last SWEEP_LOOKBACK candles for a completed liquidity sweep.

    Bullish sweep (sell-side swept):
        candle.low < level.price AND candle.close > level.price
        → wick below level, close back above

    Bearish sweep (buy-side swept):
        candle.high > level.price AND candle.close < level.price
        → wick above level, close back below

    Priority: PDH/PDL > AsiaHigh/AsiaLow > EqualHigh/EqualLow
    Returns the most recent (highest index) sweep found.
    """
    if bias not in ("bullish", "bearish"):
        return None

    target_kinds = _BUY_KINDS if bias == "bullish" else _SELL_KINDS
    target_levels = [l for l in liquidity_levels if l.kind in target_kinds]
    if not target_levels:
        return None

    tail = df_m5.tail(config.SWEEP_LOOKBACK).reset_index(drop=True)
    best_sweep: Optional[SweepEvent] = None
    best_idx = -1

    for i in range(len(tail)):
        candle = tail.iloc[i]
        for level in target_levels:
            swept = False
            if bias == "bullish":
                swept = (candle["low"] < level.price and candle["close"] > level.price)
            else:
                swept = (candle["high"] > level.price and candle["close"] < level.price)

            if swept and i > best_idx:
                # Prefer higher-priority level kind if same index
                if (
                    best_sweep is None
                    or i > best_idx
                    or _kind_priority(level.kind, bias)
                       < _kind_priority(best_sweep.swept_level.kind, bias)
                ):
                    best_idx = i
                    best_sweep = SweepEvent(
                        swept_level=level,
                        sweep_candle_index=i,
                        sweep_low=float(candle["low"]),
                        sweep_high=float(candle["high"]),
                        kind=bias,
                    )

    return best_sweep
