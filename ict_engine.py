# ict_engine.py — ICT Top-Down Analysis Engine (v2.5 — MT5 compatible)
# Pipeline: H4 bias → M15 Liquidity Sweep + FVG/OB → M5 confirm

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from config import KILL_ZONES, MAX_TRADES_PER_SESSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round_price(value: float, symbol: str) -> float:
    decimals = 2 if symbol == "XAU_USD" else 5
    return round(value, decimals)


def _to_utc_dt(t) -> datetime:
    """Chuyển pd.Timestamp hoặc ISO-string về datetime UTC-aware."""
    if hasattr(t, "to_pydatetime"):
        dt = t.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return datetime.fromisoformat(str(t).replace("Z", "+00:00"))


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def calc_lot_size(symbol: str, entry: float, sl: float,
                  equity: float, risk_pct: float = 0.01) -> float:
    CONTRACT_SIZE = 100_000
    GOLD_CONTRACT = 100
    MIN_LOT       = 0.01
    risk_usd      = equity * risk_pct
    sl_distance   = abs(entry - sl)
    if sl_distance == 0:
        return MIN_LOT
    if symbol == "XAU_USD":
        dollar_per_lot = sl_distance * GOLD_CONTRACT
    elif symbol == "USD_JPY":
        dollar_per_lot = sl_distance * CONTRACT_SIZE / entry
    else:
        dollar_per_lot = sl_distance * CONTRACT_SIZE
    lot = risk_usd / dollar_per_lot
    lot = max(MIN_LOT, int(lot / MIN_LOT) * MIN_LOT)
    return round(lot, 2)


# ---------------------------------------------------------------------------
# 1. Kill Zone
# ---------------------------------------------------------------------------

def is_kill_zone(dt_utc: datetime) -> tuple[bool, str]:
    hour = dt_utc.hour
    for zone_name, (start, end) in KILL_ZONES.items():
        if start <= hour < end:
            return True, zone_name
    return False, ""


# ---------------------------------------------------------------------------
# 2. H4 Market Structure
# ---------------------------------------------------------------------------

def get_market_structure(df_h4: pd.DataFrame) -> str:
    df = df_h4.tail(50).reset_index(drop=True)
    if len(df) < 3:
        return "neutral"

    bullish_count = 0
    bearish_count = 0
    lookback = min(10, len(df) - 1)

    for i in range(len(df) - lookback, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        if curr["high"] > prev["high"] and curr["low"] > prev["low"]:
            bullish_count += 1
        if curr["high"] < prev["high"] and curr["low"] < prev["low"]:
            bearish_count += 1

    if bullish_count > bearish_count * 1.5:
        return "bullish"
    elif bearish_count > bullish_count * 1.5:
        return "bearish"
    return "neutral"


# ---------------------------------------------------------------------------
# 3. Liquidity Sweep (M15)
# ---------------------------------------------------------------------------

def find_liquidity_sweep(df_m15: pd.DataFrame) -> Optional[dict]:
    """
    Bullish sweep : wick dưới đáy 20-bar reference, đóng lại trên đáy.
    Bearish sweep : wick trên đỉnh 20-bar reference, đóng lại dưới đỉnh.
    Chỉ xét candle nằm trong Kill Zone.
    """
    if len(df_m15) < 22:
        return None

    for i in range(20, len(df_m15)):
        candle = df_m15.iloc[i]

        try:
            candle_time = _to_utc_dt(candle["time"])
        except Exception:
            continue

        in_zone, zone_name = is_kill_zone(candle_time)
        if not in_zone:
            continue

        ref         = df_m15.iloc[i - 20: i]
        recent_low  = float(ref["low"].min())
        recent_high = float(ref["high"].max())

        if candle["low"] < recent_low and candle["close"] > recent_low:
            return {
                "type":       "bullish",
                "sweep_low":  float(candle["low"]),
                "sweep_high": None,
                "zone":       zone_name,
            }

        if candle["high"] > recent_high and candle["close"] < recent_high:
            return {
                "type":       "bearish",
                "sweep_low":  None,
                "sweep_high": float(candle["high"]),
                "zone":       zone_name,
            }

    return None


# ---------------------------------------------------------------------------
# 4. Fair Value Gap (M15)
# ---------------------------------------------------------------------------

def find_fvg(df_m15: pd.DataFrame, bias: str) -> Optional[dict]:
    if len(df_m15) < 3:
        return None

    current_close = float(df_m15["close"].iloc[-1])
    search_start  = max(1, len(df_m15) - 11)
    search_end    = len(df_m15) - 1

    for i in range(search_end - 1, search_start - 1, -1):
        prev_c = df_m15.iloc[i - 1]
        next_c = df_m15.iloc[i + 1]

        if bias == "bullish":
            fvg_bottom = float(prev_c["high"])
            fvg_top    = float(next_c["low"])
            if fvg_bottom < fvg_top and current_close > fvg_top:
                return {"type": "bullish", "top": fvg_top, "bottom": fvg_bottom}

        elif bias == "bearish":
            fvg_top    = float(prev_c["low"])
            fvg_bottom = float(next_c["high"])
            if fvg_top > fvg_bottom and current_close < fvg_bottom:
                return {"type": "bearish", "top": fvg_top, "bottom": fvg_bottom}

    return None


# ---------------------------------------------------------------------------
# 5. Order Block (M15)
# ---------------------------------------------------------------------------

def find_order_block(df_m15: pd.DataFrame, bias: str) -> Optional[dict]:
    if len(df_m15) < 5:
        return None

    current_close = float(df_m15["close"].iloc[-1])
    search_start  = max(0, len(df_m15) - 20)

    for i in range(len(df_m15) - 4, search_start - 1, -1):
        candle     = df_m15.iloc[i]
        next_three = df_m15.iloc[i + 1: i + 4]
        if len(next_three) < 3:
            continue

        if bias == "bullish":
            if candle["close"] >= candle["open"]:
                continue
            if not all(next_three.iloc[j]["close"] > next_three.iloc[j]["open"] for j in range(3)):
                continue
            if float(candle["low"]) <= current_close <= float(candle["high"]):
                return {
                    "type":    "bullish",
                    "ob_high": float(candle["high"]),
                    "ob_low":  float(candle["low"]),
                }

        elif bias == "bearish":
            if candle["close"] <= candle["open"]:
                continue
            if not all(next_three.iloc[j]["close"] < next_three.iloc[j]["open"] for j in range(3)):
                continue
            if float(candle["low"]) <= current_close <= float(candle["high"]):
                return {
                    "type":    "bearish",
                    "ob_high": float(candle["high"]),
                    "ob_low":  float(candle["low"]),
                }

    return None


# ---------------------------------------------------------------------------
# 6. M5 Entry Confirmation
# ---------------------------------------------------------------------------

def confirm_entry_m5(df_m5: pd.DataFrame, bias: str) -> bool:
    if len(df_m5) < 15:
        return False

    atr_value = calc_atr(df_m5, period=14).iloc[-1]
    if pd.isna(atr_value) or atr_value == 0:
        return False

    last    = df_m5.iloc[-1]
    body    = abs(float(last["close"]) - float(last["open"]))
    is_bull = float(last["close"]) > float(last["open"])
    is_bear = float(last["close"]) < float(last["open"])

    if bias == "bullish":
        return is_bull and body > 0.5 * atr_value
    elif bias == "bearish":
        return is_bear and body > 0.5 * atr_value
    return False


# ---------------------------------------------------------------------------
# 7. SL / TP
# ---------------------------------------------------------------------------

def calc_sl_tp(
    sweep:  dict,
    fvg:    Optional[dict],
    ob:     Optional[dict],
    df_m15: pd.DataFrame,
    bias:   str,
    symbol: str,
    entry:  float,
) -> dict:
    atr = float(calc_atr(df_m15, period=14).iloc[-1])

    if bias == "bullish":
        base = sweep["sweep_low"] if sweep["sweep_low"] is not None else (entry - atr)
        sl   = base - atr * 0.5

        highs = df_m15["high"].tail(10)
        highs = highs[highs > entry]
        tp1   = float(highs.max()) if not highs.empty else entry + atr * 2

        if fvg is not None:
            tp2 = fvg["top"]
        elif ob is not None:
            tp2 = ob["ob_high"]
        else:
            tp2 = entry + atr * 3

        if tp2 <= tp1:
            tp2 = tp1 + atr

    else:  # bearish
        base = sweep["sweep_high"] if sweep["sweep_high"] is not None else (entry + atr)
        sl   = base + atr * 0.5

        lows = df_m15["low"].tail(10)
        lows = lows[lows < entry]
        tp1  = float(lows.min()) if not lows.empty else entry - atr * 2

        if fvg is not None:
            tp2 = fvg["bottom"]
        elif ob is not None:
            tp2 = ob["ob_low"]
        else:
            tp2 = entry - atr * 3

        if tp2 >= tp1:
            tp2 = tp1 - atr

    return {
        "sl":  _round_price(sl,  symbol),
        "tp1": _round_price(tp1, symbol),
        "tp2": _round_price(tp2, symbol),
    }


# ---------------------------------------------------------------------------
# 8. Orchestrator (live bot)
# ---------------------------------------------------------------------------

def analyze(
    symbol:              str,
    df_h4:               pd.DataFrame,
    df_m15:              pd.DataFrame,
    df_m5:               pd.DataFrame,
    session_trade_count: int = 0,
) -> tuple[Optional[dict], str]:
    """Trả về (signal_dict, "") khi có setup, hoặc (None, reject_reason)."""
    now_utc = datetime.now(tz=timezone.utc)

    in_zone, zone_name = is_kill_zone(now_utc)
    if not in_zone:
        return None, "outside kill zone"

    if session_trade_count >= MAX_TRADES_PER_SESSION:
        return None, "max trades per session"

    bias = get_market_structure(df_h4)
    if bias == "neutral":
        return None, "H4 neutral"

    sweep = find_liquidity_sweep(df_m15)
    if sweep is None:
        return None, "no sweep"
    if sweep["type"] != bias:
        return None, f"sweep {sweep['type']} != bias {bias}"

    fvg = find_fvg(df_m15, bias)
    ob  = find_order_block(df_m15, bias)
    if fvg is None and ob is None:
        return None, "no FVG or OB"

    if not confirm_entry_m5(df_m5, bias):
        return None, "M5 no confirm"

    entry = _round_price(float(df_m5["close"].iloc[-1]), symbol)
    sltp  = calc_sl_tp(sweep, fvg, ob, df_m15, bias, symbol, entry)

    risk = abs(entry - sltp["sl"])
    rr   = round(abs(sltp["tp1"] - entry) / risk, 2) if risk > 0 else 0.0

    setup_parts = ["Sweep"]
    if fvg: setup_parts.append("FVG")
    if ob:  setup_parts.append("OB")

    return {
        "symbol":    symbol,
        "signal":    "BUY" if bias == "bullish" else "SELL",
        "entry":     entry,
        "sl":        sltp["sl"],
        "tp1":       sltp["tp1"],
        "tp2":       sltp["tp2"],
        "rr":        rr,
        "setup":     " + ".join(setup_parts),
        "zone":      zone_name,
        "bias":      bias.capitalize(),
        "timestamp": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lot_half":  0.01,
        "risk_usd":  10.0,
    }, ""
