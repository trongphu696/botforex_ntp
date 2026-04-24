import pandas as pd
import numpy as np
import config


def calc_atr(df: pd.DataFrame, period: int = None) -> pd.Series:
    """Wilder's smoothed ATR.  Seed with SMA(period), then EWM with alpha=1/period."""
    if period is None:
        period = config.ATR_PERIOD
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    # Wilder smoothing: seed = SMA of first `period` bars, then EWM
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def get_atr_value(df: pd.DataFrame, period: int = None) -> float:
    """Returns the last closed-bar ATR scalar."""
    if period is None:
        period = config.ATR_PERIOD
    atr_series = calc_atr(df, period)
    val = atr_series.iloc[-1]
    return float(val) if not np.isnan(val) else 0.0


def get_ema_value(series: pd.Series, period: int) -> float:
    ema = calc_ema(series, period)
    return float(ema.iloc[-1])
