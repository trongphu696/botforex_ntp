from typing import Optional
import pandas as pd
import config
from core.models import SweepEvent, ConfirmationEvent
from core.swing import get_recent_swings, get_swing_highs, get_swing_lows


def detect_mss(
    df_m5: pd.DataFrame,
    sweep_event: SweepEvent,
    swing_n: int = config.M5_SWING_N,
    lookback: int = 20,
) -> Optional[ConfirmationEvent]:
    """
    Market Structure Shift — reversal confirmation after sweep.

    Bullish sweep:
        Find the last swing HIGH before the sweep within `lookback` bars.
        That swing high was part of the prior bearish LH structure.
        Scan bars AFTER the sweep (up to CHOCH_MAX_BARS_AFTER):
        if any bar closes ABOVE that swing high → MSS confirmed.

    Bearish sweep:
        Find the last swing LOW before the sweep.
        Scan bars after sweep for a close BELOW that swing low.
    """
    sweep_idx = sweep_event.sweep_candle_index
    # Work on the tail slice used during sweep detection
    tail = df_m5.tail(config.SWEEP_LOOKBACK).reset_index(drop=True)

    pre_sweep = tail.iloc[max(0, sweep_idx - lookback): sweep_idx + 1]
    if pre_sweep.empty:
        return None

    pre_df = df_m5.iloc[-config.SWEEP_LOOKBACK:].iloc[
        max(0, sweep_idx - lookback): sweep_idx + 1
    ].reset_index(drop=True)

    swings = get_recent_swings(pre_df, n=swing_n, lookback_bars=len(pre_df))
    post_start = sweep_idx + 1
    post_end   = min(len(tail), sweep_idx + 1 + config.CHOCH_MAX_BARS_AFTER)
    post_bars  = tail.iloc[post_start:post_end]

    if sweep_event.kind == "bullish":
        sh_list = get_swing_highs(swings)
        if not sh_list:
            return None
        opposing_level = sh_list[-1].price
        for j, row in post_bars.iterrows():
            if row["close"] > opposing_level:
                return ConfirmationEvent(kind="MSS", candle_index=j, broke_level=opposing_level)

    else:  # bearish
        sl_list = get_swing_lows(swings)
        if not sl_list:
            return None
        opposing_level = sl_list[-1].price
        for j, row in post_bars.iterrows():
            if row["close"] < opposing_level:
                return ConfirmationEvent(kind="MSS", candle_index=j, broke_level=opposing_level)

    return None


def detect_bos(
    df_m5: pd.DataFrame,
    bias: str,
    swing_n: int = config.M5_SWING_N,
) -> Optional[ConfirmationEvent]:
    """
    Break of Structure — continuation break in bias direction.

    Bullish: last close > most recent swing HIGH on M15.
    Bearish: last close < most recent swing LOW on M15.
    """
    swings = get_recent_swings(df_m5, n=swing_n, lookback_bars=50)
    last_close = float(df_m5["close"].iloc[-1])
    last_idx   = len(df_m5) - 1

    if bias == "bullish":
        sh_list = get_swing_highs(swings)
        if not sh_list:
            return None
        recent_sh = sh_list[-1]
        if last_close > recent_sh.price:
            return ConfirmationEvent(kind="BOS", candle_index=last_idx, broke_level=recent_sh.price)

    else:
        sl_list = get_swing_lows(swings)
        if not sl_list:
            return None
        recent_sl = sl_list[-1]
        if last_close < recent_sl.price:
            return ConfirmationEvent(kind="BOS", candle_index=last_idx, broke_level=recent_sl.price)

    return None


def detect_displacement(
    df_m5: pd.DataFrame,
    bias: str,
    atr_value: float,
) -> Optional[ConfirmationEvent]:
    """
    Displacement candle: large-bodied candle with strong directional close.

    Bullish:
        body = close - open >= DISPLACEMENT_ATR_MULT × ATR
        close in top 25% of candle range: (high - close) / (high - low) <= 0.25

    Bearish: mirror with bearish candle, close in bottom 25%.
    """
    tail = df_m5.tail(config.DISPLACEMENT_LOOKBACK)
    mult = config.DISPLACEMENT_ATR_MULT

    for i in range(len(tail) - 1, -1, -1):  # most recent first
        c = tail.iloc[i]
        candle_range = float(c["high"]) - float(c["low"])
        if candle_range == 0:
            continue

        if bias == "bullish":
            body = float(c["close"]) - float(c["open"])
            if body >= mult * atr_value:
                # strong close: not much upper wick
                upper_wick_ratio = (float(c["high"]) - float(c["close"])) / candle_range
                if upper_wick_ratio <= 0.25:
                    idx = len(df_m5) - config.DISPLACEMENT_LOOKBACK + i
                    return ConfirmationEvent(kind="displacement", candle_index=idx, broke_level=float(c["close"]))
        else:
            body = float(c["open"]) - float(c["close"])
            if body >= mult * atr_value:
                lower_wick_ratio = (float(c["close"]) - float(c["low"])) / candle_range
                if lower_wick_ratio <= 0.25:
                    idx = len(df_m5) - config.DISPLACEMENT_LOOKBACK + i
                    return ConfirmationEvent(kind="displacement", candle_index=idx, broke_level=float(c["close"]))

    return None
