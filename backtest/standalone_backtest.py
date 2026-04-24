# -*- coding: utf-8 -*-
"""
ICT Standalone Backtest - XAUUSD (Gold)
========================================
Strategy : Sweep -> FVG -> MSS Entry  (ICT methodology)
Data     : Yahoo Finance GC=F (Gold Futures, ~XAUUSD)
Target   : ~5 signals/week, RR > 2, SL >= $15 (no tiny SLs)
Account  : $1 000, Risk 2.5% per trade
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# --- Strategy parameters -----------------------------------------------------
ACCOUNT      = 1_000.0
RISK_PCT     = 0.025      # 2.5 % per trade
MIN_RR       = 2.0        # minimum RR at TP1
SL_MIN       = 15.0       # minimum $15 SL for gold (no tiny stops)
SL_ATR_MULT  = 1.5        # ATR buffer added beyond sweep wick
TP2_R        = 3.5        # TP2 target in R multiples
ANTISPAM_H   = 2          # minimum hours between signals (reduced for ~5/week target)
ATR_PERIOD   = 14
EMA_PERIOD   = 200
LONDON       = (7, 16)    # UTC
NY           = (13, 21)   # UTC
FVG_LOOKBACK = 30         # bars to scan for FVG (extended)
SWEEP_LB     = 25         # bars to scan for sweep (extended from 15)
ATR_MIN      = 1.5        # minimum ATR(14) in $ (relaxed slightly)
ATR_MAX_MULT = 8.0        # skip if ATR > ATR_MIN x this (news spike)
REQUIRE_MSS  = False      # MSS gate — set False to increase frequency


# --- Indicators --------------------------------------------------------------

def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low = df["High"], df["Low"]
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


# --- Swing detection ---------------------------------------------------------

def swing_highs(series: pd.Series, n: int = 3) -> list[tuple[int, float]]:
    arr = series.values
    result = []
    for i in range(n, len(arr) - n):
        if all(arr[i] >= arr[i - j] for j in range(1, n + 1)) and \
           all(arr[i] >= arr[i + j] for j in range(1, n + 1)):
            result.append((i, float(arr[i])))
    return result


def swing_lows(series: pd.Series, n: int = 3) -> list[tuple[int, float]]:
    arr = series.values
    result = []
    for i in range(n, len(arr) - n):
        if all(arr[i] <= arr[i - j] for j in range(1, n + 1)) and \
           all(arr[i] <= arr[i + j] for j in range(1, n + 1)):
            result.append((i, float(arr[i])))
    return result


# --- Bias --------------------------------------------------------------------

def h4_bias(df_h4: pd.DataFrame) -> str:
    """HH/HL = bullish, LH/LL = bearish, else neutral."""
    if len(df_h4) < 30:
        return "neutral"
    sh = swing_highs(df_h4["High"], n=2)
    sl = swing_lows(df_h4["Low"], n=2)
    if len(sh) < 2 or len(sl) < 2:
        return "neutral"
    hh = sh[-1][1] > sh[-2][1]
    hl = sl[-1][1] > sl[-2][1]
    lh = sh[-1][1] < sh[-2][1]
    ll = sl[-1][1] < sl[-2][1]
    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    return "neutral"


def h1_ema_bias(df_h1: pd.DataFrame) -> str:
    ema = df_h1["ema200"].iloc[-1]
    price = df_h1["Close"].iloc[-1]
    if price > ema:
        return "bullish"
    if price < ema:
        return "bearish"
    return "neutral"


# --- Liquidity levels --------------------------------------------------------

def get_pdh_pdl(df_d1: pd.DataFrame, bar_date) -> tuple[float | None, float | None]:
    prev = df_d1[df_d1.index.date < bar_date]
    if prev.empty:
        return None, None
    return float(prev["High"].iloc[-1]), float(prev["Low"].iloc[-1])


def get_asia_range(df_m5: pd.DataFrame, bar_date) -> tuple[float | None, float | None]:
    asia_start = pd.Timestamp(bar_date, tz="UTC")
    asia_end   = asia_start + pd.Timedelta(hours=7)
    seg = df_m5[(df_m5.index >= asia_start) & (df_m5.index < asia_end)]
    if len(seg) < 5:
        return None, None
    return float(seg["High"].max()), float(seg["Low"].min())


# --- Sweep detection ---------------------------------------------------------

def detect_sweep(df_m5: pd.DataFrame, levels: list[tuple[str, float]], bias: str):
    """
    Returns (level_name, sweep_wick_price) or (None, None).
    Bullish: wick below level, close above  ->  sell-side liquidity taken
    Bearish: wick above level, close below  ->  buy-side liquidity taken
    """
    tail = df_m5.tail(SWEEP_LB)
    best = (None, None, -1)  # name, wick, idx

    for lvl_name, lvl_price in levels:
        if lvl_price is None:
            continue
        for i, (_, row) in enumerate(tail.iterrows()):
            if bias == "bullish":
                if row["Low"] < lvl_price < row["Close"]:
                    if i > best[2]:
                        best = (lvl_name, float(row["Low"]), i)
            else:
                if row["High"] > lvl_price > row["Close"]:
                    if i > best[2]:
                        best = (lvl_name, float(row["High"]), i)

    return best[0], best[1]


# --- FVG detection -----------------------------------------------------------

def detect_fvg(df_m5: pd.DataFrame, bias: str, atr: float):
    """
    3-candle FVG pattern.
    Bullish: c1.high < c3.low   (gap up, price left void)
    Bearish: c1.low  > c3.high  (gap down)
    Returns (top, bottom, midpoint) of the most recent valid FVG or None.
    Min gap = 0.3 x ATR to filter noise.
    """
    tail = df_m5.tail(FVG_LOOKBACK).reset_index(drop=True)
    min_gap = 0.3 * atr
    candidates = []

    for i in range(len(tail) - 2):
        c1, c3 = tail.iloc[i], tail.iloc[i + 2]
        if bias == "bullish" and c1["High"] < c3["Low"]:
            gap = c3["Low"] - c1["High"]
            if gap >= min_gap:
                candidates.append((c1["High"], c3["Low"], (c1["High"] + c3["Low"]) / 2))
        elif bias == "bearish" and c1["Low"] > c3["High"]:
            gap = c1["Low"] - c3["High"]
            if gap >= min_gap:
                candidates.append((c1["Low"], c3["High"], (c1["Low"] + c3["High"]) / 2))

    return candidates[-1] if candidates else None


# --- MSS confirmation --------------------------------------------------------

def detect_mss(df_m5: pd.DataFrame, bias: str, lookback: int = 20) -> bool:
    """
    Bullish MSS: recent close breaks above a prior swing high.
    Bearish MSS: recent close breaks below a prior swing low.
    """
    tail = df_m5.tail(lookback)
    if len(tail) < 10:
        return False
    if bias == "bullish":
        sh = swing_highs(tail["High"], n=2)
        if not sh:
            return False
        prior_high = max(p for _, p in sh)
        return float(tail["Close"].iloc[-1]) > prior_high
    else:
        sl = swing_lows(tail["Low"], n=2)
        if not sl:
            return False
        prior_low = min(p for _, p in sl)
        return float(tail["Close"].iloc[-1]) < prior_low


# --- Outcome simulation -------------------------------------------------------

def simulate_outcome(
    df_m5_full: pd.DataFrame,
    sig_idx: int,
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    spread: float = 0.30,
) -> tuple[str, float, int]:
    """Walk forward from sig_idx+1. Returns (outcome, pnl_R, bars_held)."""
    adj_entry = entry + spread if direction == "BUY" else entry - spread
    risk = abs(adj_entry - sl)
    if risk == 0:
        return "EXPIRED", 0.0, 0

    for j in range(sig_idx + 1, min(sig_idx + 600, len(df_m5_full))):
        c = df_m5_full.iloc[j]
        if direction == "BUY":
            if c["Low"] <= sl:
                return "LOSS", -1.0, j - sig_idx
            if c["High"] >= tp2:
                return "TP2", round(abs(tp2 - adj_entry) / risk, 2), j - sig_idx
            if c["High"] >= tp1:
                return "TP1", round(abs(tp1 - adj_entry) / risk, 2), j - sig_idx
        else:
            if c["High"] >= sl:
                return "LOSS", -1.0, j - sig_idx
            if c["Low"] <= tp2:
                return "TP2", round(abs(tp2 - adj_entry) / risk, 2), j - sig_idx
            if c["Low"] <= tp1:
                return "TP1", round(abs(tp1 - adj_entry) / risk, 2), j - sig_idx

    return "EXPIRED", 0.0, 600


# --- Symbol configuration ----------------------------------------------------
# yf_ticker   : Yahoo Finance symbol
# sessions    : active UTC hour windows [(start, end), ...]
# atr_min     : minimum ATR(14) to avoid dead market
# sl_min      : minimum SL distance (price units) — no tiny stops
# spread      : typical spread cost (price units)
# contract    : price units per lot (XAUUSD=100, forex=100000)
# pip         : 1 pip in price units (for display)

SYMBOL_CONFIG = {
    "XAUUSD": dict(yf_ticker="GC=F",       sessions=[(7,16),(13,21)], atr_min=1.5,    sl_min=15.0,   spread=0.30,    contract=100,    pip=1.0  ),
    "EURUSD": dict(yf_ticker="EURUSD=X",   sessions=[(7,16),(13,21)], atr_min=0.0003, sl_min=0.0015, spread=0.00010, contract=100000, pip=0.0001),
    "GBPUSD": dict(yf_ticker="GBPUSD=X",   sessions=[(7,16)],         atr_min=0.0003, sl_min=0.0015, spread=0.00012, contract=100000, pip=0.0001),
    "USDJPY": dict(yf_ticker="USDJPY=X",   sessions=[(0,9),(13,21)],  atr_min=0.04,   sl_min=0.15,   spread=0.020,   contract=100000, pip=0.01  ),
    "USDCHF": dict(yf_ticker="USDCHF=X",   sessions=[(7,16),(13,21)], atr_min=0.0003, sl_min=0.0015, spread=0.00012, contract=100000, pip=0.0001),
}

ALL_SYMBOLS = list(SYMBOL_CONFIG.keys())


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns and ensure UTC timezone."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def calc_lot(account: float, risk_pct: float, sl_dist: float, contract: float) -> float:
    """
    lot = (account x risk_pct) / (sl_dist x contract)
    XAUUSD: contract=100  (1 lot=100oz, $1 move=$100)
    Forex : contract=100000 (1 lot=100k, 1pip=$10)
    """
    risk_dollar = account * risk_pct
    lots = risk_dollar / (sl_dist * contract)
    return max(round(lots, 2), 0.01)


# --- Main backtest (single symbol) -------------------------------------------

def run_backtest(symbol: str = "XAUUSD", days: int = 55) -> pd.DataFrame | None:
    cfg = SYMBOL_CONFIG.get(symbol)
    if cfg is None:
        print(f"[ERROR] Unknown symbol '{symbol}'. Choose from: {ALL_SYMBOLS}")
        return None

    yf_ticker = cfg["yf_ticker"]
    sessions  = cfg["sessions"]
    atr_min   = cfg["atr_min"]
    sl_min    = cfg["sl_min"]
    spread    = cfg["spread"]
    contract  = cfg["contract"]
    pip       = cfg["pip"]

    print("=" * 65)
    print(f"  ICT Backtest - {symbol}  ({yf_ticker})")
    print(f"  Account: ${ACCOUNT:,.0f}  |  Risk: {RISK_PCT*100:.1f}%/trade")
    print(f"  Strategy: Sweep -> FVG -> MSS  |  Min RR: {MIN_RR}  |  Min SL: {sl_min}")
    print("=" * 65)

    print("\n[1/4] Downloading historical data...")

    # -- 5-minute data (max ~60 days from Yahoo) --
    df5 = _normalize(yf.download(yf_ticker, period=f"{days}d", interval="5m",
                                 progress=False, auto_adjust=True))

    # -- H1 data (730 days) for EMA200 --
    df1h = _normalize(yf.download(yf_ticker, period="730d", interval="1h",
                                  progress=False, auto_adjust=True))
    df1h["ema200"] = calc_ema(df1h["Close"], EMA_PERIOD)

    # -- H4 (resample from H1) --
    df4h = df1h.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()
    df4h["ema200"] = calc_ema(df4h["Close"], EMA_PERIOD)

    # -- D1 (resample from H1) --
    df_d1 = df1h.resample("1D").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()

    # -- ATR on M5 --
    df5["atr"] = calc_atr(df5, ATR_PERIOD)

    if df5.empty or df1h.empty:
        print(f"  [ERROR] No data returned for {symbol} ({yf_ticker})")
        return None

    print(f"  M5  : {len(df5)} bars  ({df5.index[0].date()} -> {df5.index[-1].date()})")
    print(f"  H1  : {len(df1h)} bars")
    print(f"  H4  : {len(df4h)} bars")

    # -- Walk-forward ----------------------------------------------------------
    print("\n[2/4] Walk-forward analysis...")
    signals: list[dict] = []
    last_signal_time: pd.Timestamp | None = None
    start_idx = 250  # warm-up bars

    counters = dict(
        outside_session=0, antispam=0, no_data=0,
        h4_neutral=0, h1_mismatch=0, atr_filter=0,
        no_sweep=0, no_fvg=0, no_mss=0,
        sl_invalid=0, rr_fail=0,
    )

    for idx in range(start_idx, len(df5)):
        bar_time = df5.index[idx]
        hour = bar_time.hour

        # Session filter (per-symbol windows)
        in_session = any(s[0] <= hour < s[1] for s in sessions)
        if not in_session:
            counters["outside_session"] += 1
            continue

        # Anti-spam
        if last_signal_time is not None:
            elapsed_h = (bar_time - last_signal_time).total_seconds() / 3600
            if elapsed_h < ANTISPAM_H:
                counters["antispam"] += 1
                continue

        # Slice data - NO lookahead
        m5   = df5.iloc[: idx + 1].tail(500)
        h1   = df1h[df1h.index <= bar_time].tail(300)
        h4   = df4h[df4h.index <= bar_time].tail(100)
        d1   = df_d1[df_d1.index <= bar_time].tail(30)

        if len(h4) < 20 or len(h1) < EMA_PERIOD + 5:
            counters["no_data"] += 1
            continue

        # -- Gate 1: H4 trend bias --------------------------------------------
        bias = h4_bias(h4)
        if bias == "neutral":
            counters["h4_neutral"] += 1
            continue

        # -- Gate 2: H1 EMA200 alignment -------------------------------------
        h1_b = h1_ema_bias(h1)
        if h1_b != bias:
            counters["h1_mismatch"] += 1
            continue

        # -- Gate 3: ATR volatility (per-symbol threshold) --------------------
        atr = float(m5["atr"].iloc[-1])
        if pd.isna(atr) or atr < atr_min or atr > atr_min * ATR_MAX_MULT:
            counters["atr_filter"] += 1
            continue

        # -- Gate 4: Liquidity levels -----------------------------------------
        pdh, pdl = get_pdh_pdl(d1, bar_time.date())
        asia_h, asia_l = get_asia_range(df5, bar_time.date())

        levels: list[tuple[str, float]] = []
        if bias == "bullish":
            if pdl is not None:   levels.append(("PDL",      pdl))
            if asia_l is not None: levels.append(("AsiaLow",  asia_l))
        else:
            if pdh is not None:   levels.append(("PDH",      pdh))
            if asia_h is not None: levels.append(("AsiaHigh", asia_h))

        if not levels:
            counters["no_data"] += 1
            continue

        # -- Gate 5: Sweep ----------------------------------------------------
        swept_name, sweep_wick = detect_sweep(m5, levels, bias)
        if swept_name is None:
            counters["no_sweep"] += 1
            continue

        # -- Gate 6: FVG entry ------------------------------------------------
        fvg = detect_fvg(m5, bias, atr)
        if fvg is None:
            counters["no_fvg"] += 1
            continue
        fvg_top, fvg_bottom, entry = fvg

        # Entry must be in front of current price (limit order zone)
        curr_price = float(m5["Close"].iloc[-1])
        if bias == "bullish" and entry > curr_price + atr:
            counters["no_fvg"] += 1
            continue
        if bias == "bearish" and entry < curr_price - atr:
            counters["no_fvg"] += 1
            continue

        # -- Gate 7: MSS confirmation (optional when REQUIRE_MSS=False) ----------
        mss_ok = detect_mss(m5, bias)
        if REQUIRE_MSS and not mss_ok:
            counters["no_mss"] += 1
            continue

        # -- Gate 8: SL calculation -------------------------------------------
        buf = atr * SL_ATR_MULT
        if bias == "bullish":
            sl = round(sweep_wick - buf, 2)
            if sl >= entry:
                counters["sl_invalid"] += 1
                continue
        else:
            sl = round(sweep_wick + buf, 2)
            if sl <= entry:
                counters["sl_invalid"] += 1
                continue

        sl_dist = abs(entry - sl)
        if sl_dist < sl_min:
            if bias == "bullish":
                sl = round(entry - sl_min, 5)
            else:
                sl = round(entry + sl_min, 5)
            sl_dist = sl_min

        # -- Gate 9: TP1 / TP2 / RR ------------------------------------------
        # TP1: nearest opposing liquidity level with RR >= MIN_RR
        opp_levels: list[tuple[str, float]] = []
        if bias == "bullish":
            if pdh is not None:   opp_levels.append(("PDH",      pdh))
            if asia_h is not None: opp_levels.append(("AsiaHigh", asia_h))
        else:
            if pdl is not None:   opp_levels.append(("PDL",      pdl))
            if asia_l is not None: opp_levels.append(("AsiaLow",  asia_l))

        tp1 = None
        if opp_levels:
            if bias == "bullish":
                candidates = sorted([p for _, p in opp_levels if p > entry])
            else:
                candidates = sorted([p for _, p in opp_levels if p < entry], reverse=True)
            for p in candidates:
                rr = abs(p - entry) / sl_dist
                if rr >= MIN_RR:
                    tp1 = round(p, 2)
                    break

        # ATR fallback: 3.0 ATR should clear RR 2 on most setups
        if tp1 is None:
            if bias == "bullish":
                tp1 = round(entry + sl_dist * 2.5, 2)
            else:
                tp1 = round(entry - sl_dist * 2.5, 2)

        rr1 = abs(tp1 - entry) / sl_dist
        if rr1 < MIN_RR:
            counters["rr_fail"] += 1
            continue

        # TP2: 3.5R extension
        if bias == "bullish":
            tp2 = round(entry + sl_dist * TP2_R, 2)
        else:
            tp2 = round(entry - sl_dist * TP2_R, 2)

        # -- Simulate outcome -------------------------------------------------
        direction = "BUY" if bias == "bullish" else "SELL"
        outcome, pnl_r, bars = simulate_outcome(df5, idx, direction, entry, sl, tp1, tp2, spread)

        risk_dollar = ACCOUNT * RISK_PCT
        pnl_dollar  = round(pnl_r * risk_dollar, 2)
        lot         = calc_lot(ACCOUNT, RISK_PCT, sl_dist, contract)
        sl_pips     = round(sl_dist / pip)

        # Session name: match the active window
        sess_name = "Unknown"
        for s_start, s_end in sessions:
            if s_start <= hour < s_end:
                sess_name = {(7,16):"London", (13,21):"NY", (0,9):"Asia"}.get((s_start,s_end), f"{s_start}-{s_end}h")
                break

        record = {
            "symbol":      symbol,
            "date":        bar_time.strftime("%Y-%m-%d"),
            "weekday":     bar_time.strftime("%a"),
            "time_utc":    bar_time.strftime("%H:%M"),
            "session":     sess_name,
            "direction":   direction,
            "swept_level": swept_name,
            "mss":         mss_ok,
            "bias_h4":     bias,
            "entry":       round(entry, 5),
            "sl":          round(sl, 5),
            "tp1":         round(tp1, 5),
            "tp2":         round(tp2, 5),
            "sl_dist":     round(sl_dist, 5),
            "sl_pips":     sl_pips,
            "rr1":         round(rr1, 2),
            "rr2":         TP2_R,
            "lot":         lot,
            "risk_dollar": risk_dollar,
            "outcome":     outcome,
            "pnl_r":       round(pnl_r, 2),
            "pnl_dollar":  pnl_dollar,
            "bars_held":   bars,
        }
        signals.append(record)
        last_signal_time = bar_time

        icon = "[OK]" if outcome in ("TP1", "TP2") else ("[X]" if outcome == "LOSS" else "[~]")
        print(
            f"  {icon} [{bar_time:%m/%d %a %H:%M}] {direction:4s} {swept_name:<10} "
            f"E:{entry:.5g}  SL:{sl:.5g}(-{sl_pips}pip)  TP1:{tp1:.5g}(RR{rr1:.1f})  "
            f">> {outcome:7s}  {pnl_r:+.1f}R  ${pnl_dollar:+.0f}"
        )

    if not signals:
        print("\n[!]  No signals found. Check data availability or strategy gates.")
        print(f"   Filter breakdown: {counters}")
        return None

    df = pd.DataFrame(signals)

    # --- Statistics ----------------------------------------------------------
    print("\n[3/4] Computing statistics...")

    closed = df[df["outcome"] != "EXPIRED"]
    wins   = closed[closed["outcome"].isin(["TP1", "TP2"])]
    losses = closed[closed["outcome"] == "LOSS"]

    total_closed  = len(closed)
    win_count     = len(wins)
    loss_count    = len(losses)
    win_rate      = win_count / total_closed * 100 if total_closed > 0 else 0
    total_r       = closed["pnl_r"].sum()
    total_dollar  = closed["pnl_dollar"].sum()
    avg_win_r     = wins["pnl_r"].mean()    if not wins.empty else 0
    avg_sl        = df["sl_dist"].mean()
    avg_rr        = df["rr1"].mean()

    # Week count
    df["week_key"] = pd.to_datetime(df["date"]).dt.to_period("W")
    weeks = df["week_key"].nunique()
    per_week = len(df) / max(weeks, 1)

    # Equity curve (cumulative $)
    df["cum_dollar"] = closed["pnl_dollar"].cumsum()
    df.loc[df["outcome"] == "EXPIRED", "cum_dollar"] = np.nan
    df["cum_dollar"] = df["cum_dollar"].ffill()

    # Max drawdown (on R)
    cum_r = closed["pnl_r"].cumsum()
    peak  = cum_r.cummax()
    dd    = (cum_r - peak)
    max_dd_r = dd.min()

    print("\n" + "=" * 65)
    print(f"  BACKTEST RESULTS - {symbol}  (ICT Sweep + FVG + MSS)")
    print("=" * 65)
    print(f"  Period       : {df['date'].min()} -> {df['date'].max()}")
    print(f"  Total Signals: {len(df)}  ({per_week:.1f}/week over {weeks} weeks)")
    print(f"  Closed       : {total_closed}  |  Win: {win_count}  |  Loss: {loss_count}  |  Expired: {len(df)-total_closed}")
    print(f"  Win Rate     : {win_rate:.1f}%")
    print(f"  Total PnL    : {total_r:+.2f}R  (${total_dollar:+.0f})")
    print(f"  Avg Win      : {avg_win_r:+.2f}R")
    print(f"  Avg SL pips  : {df['sl_pips'].mean():.0f} pips")
    print(f"  Avg RR at TP1: {avg_rr:.2f}R")
    print(f"  Max Drawdown : {max_dd_r:.2f}R")
    print("=" * 65)

    # -- Weekly breakdown ------------------------------------------------------
    print("\n  WEEKLY BREAKDOWN")
    print(f"  {'Week':>12}  {'Signals':>7}  {'W/L':>6}  {'PnL_R':>7}  {'PnL_$':>8}  {'WinRate':>8}")
    for wk, grp in df.groupby("week_key"):
        g_closed = grp[grp["outcome"] != "EXPIRED"]
        w = len(g_closed[g_closed["outcome"].isin(["TP1","TP2"])])
        l = len(g_closed[g_closed["outcome"] == "LOSS"])
        r = g_closed["pnl_r"].sum()
        d = g_closed["pnl_dollar"].sum()
        wr = w / (w + l) * 100 if (w + l) > 0 else 0
        print(f"  {str(wk):>12}  {len(grp):>7}  {w}W/{l}L  {r:>+6.1f}R  ${d:>+7.0f}  {wr:>6.0f}%")

    # -- Direction breakdown ---------------------------------------------------
    print("\n  DIRECTION STATS")
    for direction in ["BUY", "SELL"]:
        g = df[df["direction"] == direction]
        if g.empty:
            continue
        gc = g[g["outcome"] != "EXPIRED"]
        w = len(gc[gc["outcome"].isin(["TP1","TP2"])])
        l = len(gc[gc["outcome"] == "LOSS"])
        r = gc["pnl_r"].sum()
        wr = w/(w+l)*100 if (w+l) > 0 else 0
        print(f"  {direction}: {len(g)} trades | {w}W/{l}L ({wr:.0f}%) | {r:+.1f}R")

    # -- Session breakdown -----------------------------------------------------
    print("\n  SESSION STATS")
    for sess in df["session"].unique():
        g = df[df["session"] == sess]
        if g.empty:
            continue
        gc = g[g["outcome"] != "EXPIRED"]
        w = len(gc[gc["outcome"].isin(["TP1","TP2"])])
        l = len(gc[gc["outcome"] == "LOSS"])
        r = gc["pnl_r"].sum()
        wr = w/(w+l)*100 if (w+l) > 0 else 0
        print(f"  {sess}: {len(g)} trades | {w}W/{l}L ({wr:.0f}%) | {r:+.1f}R")

    # -- Swept level breakdown -------------------------------------------------
    print("\n  SWEPT LEVEL STATS")
    for lvl in df["swept_level"].unique():
        g = df[df["swept_level"] == lvl]
        gc = g[g["outcome"] != "EXPIRED"]
        w = len(gc[gc["outcome"].isin(["TP1","TP2"])])
        l = len(gc[gc["outcome"] == "LOSS"])
        r = gc["pnl_r"].sum()
        wr = w/(w+l)*100 if (w+l) > 0 else 0
        print(f"  {lvl}: {len(g)} trades | {w}W/{l}L ({wr:.0f}%) | {r:+.1f}R")

    # -- Filter breakdown ------------------------------------------------------
    print(f"\n  FILTER BREAKDOWN: {counters}")

    # -- Position sizing summary -----------------------------------------------
    print(f"\n  POSITION SIZING (${ACCOUNT:.0f} account, {RISK_PCT*100:.1f}% risk/trade)")
    print(f"  Risk per trade   : ${ACCOUNT * RISK_PCT:.0f}")
    print(f"  Avg lot size     : {df['lot'].mean():.3f} lots")
    print(f"  Avg SL           : {df['sl_pips'].mean():.0f} pips")
    print(f"  Final account est: ${ACCOUNT + total_dollar:,.0f}  ({total_dollar/ACCOUNT*100:+.1f}%)")
    print("=" * 65)

    return df


# --- Run all symbols ----------------------------------------------------------

def run_all(days: int = 55, save: bool = False) -> None:
    """Backtest all symbols sequentially and print a combined summary."""
    all_results: list[pd.DataFrame] = []

    for sym in ALL_SYMBOLS:
        df = run_backtest(sym, days)
        if df is not None:
            all_results.append(df)
        print()

    if not all_results:
        print("[!] No results for any symbol.")
        return

    combined = pd.concat(all_results, ignore_index=True)

    # --- Combined summary ---
    closed  = combined[combined["outcome"] != "EXPIRED"]
    wins    = closed[closed["outcome"].isin(["TP1","TP2"])]
    losses  = closed[closed["outcome"] == "LOSS"]
    total_r = closed["pnl_r"].sum()
    total_usd = closed["pnl_dollar"].sum()
    wr      = len(wins) / len(closed) * 100 if len(closed) > 0 else 0

    combined["week_key"] = pd.to_datetime(combined["date"]).dt.to_period("W")
    weeks    = combined["week_key"].nunique()
    per_week = len(combined) / max(weeks, 1)

    print("\n" + "#" * 65)
    print("  COMBINED RESULTS — ALL SYMBOLS")
    print("#" * 65)
    print(f"  Period    : {combined['date'].min()} -> {combined['date'].max()}")
    print(f"  Signals   : {len(combined)} total  ({per_week:.1f}/week)")
    print(f"  Closed    : {len(closed)} | Win: {len(wins)} | Loss: {len(losses)} | Expired: {len(combined)-len(closed)}")
    print(f"  Win Rate  : {wr:.1f}%")
    print(f"  Total PnL : {total_r:+.2f}R  (${total_usd:+.0f})")
    print(f"  Account   : ${ACCOUNT + total_usd:,.0f}  ({total_usd/ACCOUNT*100:+.1f}%)")
    print("#" * 65)

    print(f"\n  {'Symbol':<8} {'Trades':>6}  {'W/L':>7}  {'WR%':>5}  {'PnL_R':>7}  {'PnL_$':>8}  {'Per/wk':>7}")
    for sym in ALL_SYMBOLS:
        sg = combined[combined["symbol"] == sym]
        if sg.empty:
            continue
        sc = sg[sg["outcome"] != "EXPIRED"]
        w  = len(sc[sc["outcome"].isin(["TP1","TP2"])])
        l  = len(sc[sc["outcome"] == "LOSS"])
        r  = sc["pnl_r"].sum()
        d  = sc["pnl_dollar"].sum()
        wr_s = w/(w+l)*100 if (w+l) > 0 else 0
        pw   = len(sg) / max(weeks, 1)
        print(f"  {sym:<8} {len(sg):>6}  {w}W/{l}L  {wr_s:>4.0f}%  {r:>+6.1f}R  ${d:>+7.0f}  {pw:>5.1f}/wk")

    if save:
        out = os.path.join(os.path.dirname(__file__), "all_symbols_backtest.csv")
        combined.to_csv(out, index=False)
        print(f"\n  Saved -> {out}")


# --- Entry point --------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ICT Standalone Backtest (no MT5 needed — uses Yahoo Finance)",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--symbol", type=str, default="XAUUSD",
        help=f"Single symbol to backtest. Choices: {ALL_SYMBOLS}",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Backtest ALL symbols (XAUUSD, EURUSD, GBPUSD, USDJPY, USDCHF)",
    )
    parser.add_argument(
        "--days", type=int, default=55,
        help="Days of M5 history (max ~60 from Yahoo Finance)",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save results to CSV in backtest/ folder",
    )
    args = parser.parse_args()

    if args.all:
        run_all(days=args.days, save=args.save)
    else:
        sym = args.symbol.upper()
        df  = run_backtest(sym, days=args.days)
        if df is not None and args.save:
            out = os.path.join(os.path.dirname(__file__), f"{sym.lower()}_backtest.csv")
            df.to_csv(out, index=False)
            print(f"\n  Saved -> {out}")
