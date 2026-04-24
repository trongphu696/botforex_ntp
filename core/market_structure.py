from typing import Literal
import pandas as pd
import config
from core.swing import get_recent_swings, get_swing_highs, get_swing_lows
from core.indicators import calc_ema


def get_h4_bias(df_h4: pd.DataFrame) -> Literal["bullish", "bearish", "neutral"]:
    """
    Detect HH/HL (bullish) or LH/LL (bearish) on H4.
    Requires at least 2 recent swing highs AND 2 recent swing lows.
    """
    swings = get_recent_swings(df_h4, n=config.H4_SWING_N, lookback_bars=80)
    highs = get_swing_highs(swings)
    lows  = get_swing_lows(swings)

    if len(highs) < 2 or len(lows) < 2:
        return "neutral"

    sh1, sh2 = highs[-2], highs[-1]
    sl1, sl2 = lows[-2],  lows[-1]

    hh = sh2.price > sh1.price
    hl = sl2.price > sl1.price
    lh = sh2.price < sh1.price
    ll = sl2.price < sl1.price

    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    return "neutral"


def get_h1_ema_bias(df_h1: pd.DataFrame) -> Literal["above", "below"]:
    """Returns 'above' if last close > EMA(200) on H1."""
    ema200 = calc_ema(df_h1["close"], config.EMA200_PERIOD)
    last_close = float(df_h1["close"].iloc[-1])
    last_ema   = float(ema200.iloc[-1])
    return "above" if last_close > last_ema else "below"


def get_combined_bias(
    df_h4: pd.DataFrame,
    df_h1: pd.DataFrame,
) -> Literal["bullish", "bearish", "neutral"]:
    """
    Both layers must agree:
        bullish ONLY IF h4 == "bullish" AND h1_ema == "above"
        bearish ONLY IF h4 == "bearish" AND h1_ema == "below"
    """
    h4  = get_h4_bias(df_h4)
    h1e = get_h1_ema_bias(df_h1)

    if h4 == "bullish" and h1e == "above":
        return "bullish"
    if h4 == "bearish" and h1e == "below":
        return "bearish"
    return "neutral"
