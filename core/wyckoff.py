import pandas as pd
import numpy as np
import config
from core.models import WyckoffContext
from core.indicators import calc_atr, calc_ema


def _detect_spring(df_h4: pd.DataFrame) -> float:
    """
    Spring: failed breakdown below prior support.
    - Find support = lowest low of last WYCKOFF_H4_LOOKBACK bars (excluding last 10)
    - Look in last 10 bars for a candle where:
        low < support AND close > support AND close > open (bullish rejection)
    Returns confidence (0.8) or 0.0.
    """
    lookback = config.WYCKOFF_H4_LOOKBACK
    if len(df_h4) < lookback + 10:
        return 0.0

    base = df_h4.iloc[-lookback:-10]
    support = float(base["low"].min())

    recent = df_h4.iloc[-10:]
    for i in range(len(recent)):
        c = recent.iloc[i]
        if c["low"] < support and c["close"] > support and c["close"] > c["open"]:
            return 0.8
    return 0.0


def _detect_upthrust(df_h4: pd.DataFrame) -> float:
    """
    Upthrust: failed breakout above prior resistance.
    - Find resistance = highest high of last WYCKOFF_H4_LOOKBACK bars (excluding last 10)
    - Look in last 10 bars for a candle where:
        high > resistance AND close < resistance AND close < open (bearish rejection)
    Returns confidence (0.8) or 0.0.
    """
    lookback = config.WYCKOFF_H4_LOOKBACK
    if len(df_h4) < lookback + 10:
        return 0.0

    base = df_h4.iloc[-lookback:-10]
    resistance = float(base["high"].max())

    recent = df_h4.iloc[-10:]
    for i in range(len(recent)):
        c = recent.iloc[i]
        if c["high"] > resistance and c["close"] < resistance and c["close"] < c["open"]:
            return 0.8
    return 0.0


def _detect_accumulation(df_h4: pd.DataFrame) -> float:
    """
    Accumulation: price compression (low ATR) with near-flat EMA slope.
    Returns confidence (0.6) or 0.0.
    """
    n = config.WYCKOFF_ACCUM_BARS
    if len(df_h4) < n + 5:
        return 0.0

    recent = df_h4.tail(n)
    price_range = float(recent["high"].max() - recent["low"].min())
    atr_series = calc_atr(df_h4, config.ATR_PERIOD)
    avg_atr = float(atr_series.tail(n).mean())

    if avg_atr == 0:
        return 0.0

    # Compression: range < 1.5 × average ATR
    compressed = price_range < config.WYCKOFF_ATR_COMPRESS * avg_atr

    # Flat EMA(20) slope
    ema20 = calc_ema(df_h4["close"], 20)
    slope = abs(float(ema20.iloc[-1]) - float(ema20.iloc[-n])) / float(ema20.iloc[-n])

    if compressed and slope < 0.005:
        return 0.6
    return 0.0


def _detect_distribution(df_h4: pd.DataFrame) -> float:
    """Mirror of accumulation — price compression after an uptrend."""
    return _detect_accumulation(df_h4)  # same mechanics; caller applies context


def detect_wyckoff(df_h4: pd.DataFrame, bias: str) -> WyckoffContext:
    """
    Returns the most relevant Wyckoff pattern for the given bias.
    Non-blocking: only adds confidence to a signal.
    """
    if bias == "bullish":
        conf = _detect_spring(df_h4)
        if conf > 0:
            return WyckoffContext(pattern="spring", confidence=conf)
        conf = _detect_accumulation(df_h4)
        if conf > 0:
            return WyckoffContext(pattern="accumulation", confidence=conf)

    elif bias == "bearish":
        conf = _detect_upthrust(df_h4)
        if conf > 0:
            return WyckoffContext(pattern="upthrust", confidence=conf)
        conf = _detect_distribution(df_h4)
        if conf > 0:
            return WyckoffContext(pattern="distribution", confidence=conf)

    return WyckoffContext(pattern="none", confidence=0.0)
