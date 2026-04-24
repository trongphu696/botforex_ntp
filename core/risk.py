from typing import List, Optional, Tuple
import pandas as pd
import config
from core.models import LiquidityLevel, SweepEvent
from core.swing import get_recent_swings, get_swing_highs, get_swing_lows
from core.indicators import get_atr_value


def calculate_sl(
    sweep_event: SweepEvent,
    atr_value: float,
    bias: str,
    df_m5: Optional[pd.DataFrame] = None,
    entry: Optional[float] = None,
) -> float:
    """
    ICT structural SL placement:

    BUY : SL below the most recent swing Low (HL) that is itself BELOW entry.
    SELL: SL above the most recent swing High (LH) that is itself ABOVE entry.

    Filters by entry so we never pick a structural point on the wrong side.
    Falls back to sweep wick + ATR buffer when no valid structural point exists.
    """
    buf = atr_value * config.SL_ATR_BUFFER

    if df_m5 is not None and len(df_m5) >= 10:
        swings = get_recent_swings(df_m5, n=config.M5_SWING_N, lookback_bars=50)

        if bias == "bullish":
            # Only consider swing lows that are strictly below entry
            candidates = [
                l for l in get_swing_lows(swings)
                if entry is None or l.price < entry
            ]
            if candidates:
                structural_low = candidates[-1].price  # most recent valid HL
                return round(structural_low - buf, 5)

        else:
            # Only consider swing highs that are strictly above entry
            candidates = [
                h for h in get_swing_highs(swings)
                if entry is None or h.price > entry
            ]
            if candidates:
                structural_high = candidates[-1].price  # most recent valid LH
                return round(structural_high + buf, 5)

    # Fallback: sweep wick + buffer
    if bias == "bullish":
        return round(sweep_event.sweep_low - buf, 5)
    else:
        return round(sweep_event.sweep_high + buf, 5)


def _find_nearest_level_beyond(
    levels: List[LiquidityLevel],
    entry: float,
    bias: str,
    exclude_below: float = None,
) -> float:
    """
    Find the nearest liquidity level beyond entry in the bias direction.
    For BUY: nearest level ABOVE entry (and optionally above exclude_below).
    For SELL: nearest level BELOW entry.
    """
    candidates = []
    for lvl in levels:
        if bias == "bullish" and lvl.price > entry:
            if exclude_below is None or lvl.price > exclude_below:
                candidates.append(lvl.price)
        elif bias == "bearish" and lvl.price < entry:
            if exclude_below is None or lvl.price < exclude_below:
                candidates.append(lvl.price)

    if not candidates:
        return None

    if bias == "bullish":
        return min(candidates)  # nearest above
    else:
        return max(candidates)  # nearest below


def calculate_tp1(
    df_m5: pd.DataFrame,
    bias: str,
    entry: float,
    atr_value: float,
    levels: List[LiquidityLevel] = None,
) -> float:
    """
    TP1 = nearest major liquidity level beyond entry.
    Only uses PDH/PDL and Asia range — Equal H/L are too noisy as targets.
    Fallback: entry ± TP_FALLBACK_ATR × ATR.
    """
    _MAJOR_KINDS = {"PDH", "PDL", "AsiaHigh", "AsiaLow"}
    if levels:
        major = [l for l in levels if l.kind in _MAJOR_KINDS]
        tp = _find_nearest_level_beyond(major, entry, bias)
        if tp is not None:
            return round(tp, 5)

    # ATR fallback
    buf = atr_value * config.TP_FALLBACK_ATR
    if bias == "bullish":
        return round(entry + buf, 5)
    else:
        return round(entry - buf, 5)


def calculate_tp2(
    levels: List[LiquidityLevel],
    bias: str,
    entry: float,
    tp1: float,
) -> float:
    """
    TP2 = next major liquidity level beyond TP1.
    Fallback: tp1 + (tp1 - entry) × TP2_EXTEND_MULT.
    """
    if levels:
        tp = _find_nearest_level_beyond(levels, entry, bias, exclude_below=tp1)
        if tp is not None:
            return round(tp, 5)

    extend = abs(tp1 - entry) * config.TP2_EXTEND_MULT
    if bias == "bullish":
        return round(tp1 + extend, 5)
    else:
        return round(tp1 - extend, 5)


def check_min_rr(entry: float, sl: float, tp1: float) -> Tuple[bool, float]:
    """
    rr = |tp1 - entry| / |entry - sl|
    Returns (rr >= MIN_RR, rr_value).
    """
    risk   = abs(entry - sl)
    reward = abs(tp1 - entry)
    if risk == 0:
        return False, 0.0
    rr = reward / risk
    return rr >= config.MIN_RR, round(rr, 2)


def calc_rr_tp2(entry: float, sl: float, tp2: float) -> float:
    risk = abs(entry - sl)
    if risk == 0:
        return 0.0
    return round(abs(tp2 - entry) / risk, 2)


def calculate_lot_size(symbol: str, entry: float, sl: float) -> float:
    """
    Risk-based lot sizing: risk exactly RISK_PCT% of ACCOUNT_BALANCE.

    USD-quoted (XAUUSD, GBPUSD, AUDUSD, NZDUSD):
        lot = risk_usd / (sl_distance × contract_size)

    JPY-quoted (USDJPY, GBPJPY):
        P&L per lot = sl_distance × contract_size / entry  (in USD)
        lot = risk_usd × entry / (sl_distance × contract_size)
    """
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return config.LOT_MIN

    risk_usd      = config.ACCOUNT_BALANCE * config.RISK_PCT / 100.0
    contract_size = config.LOT_CONTRACT_SIZE.get(symbol, 100_000)

    if symbol in config.JPY_QUOTED:
        raw = risk_usd * entry / (sl_distance * contract_size)
    else:
        raw = risk_usd / (sl_distance * contract_size)

    # Floor to nearest LOT_STEP, enforce minimum
    # Use round() to neutralise IEEE-754 drift before floor division
    step = config.LOT_STEP
    lot  = max(config.LOT_MIN, round(int(round(raw / step, 8)) * step, 2))
    return lot
