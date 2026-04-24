"""
Backtester — replays the IDENTICAL signal_engine pipeline on historical MT5 data.
Walk-forward: slices each timeframe per current M5 bar to prevent lookahead bias.
Simulates outcomes by scanning future M5 bars for TP1/TP2/SL hits.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import pandas as pd
import config
from engine.signal_engine import analyze
from services import mt5_client
from storage import json_store


def _simulate_outcome(
    df_m5_full: pd.DataFrame,
    signal_idx: int,
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: float,
    spread: float = 0.0,
) -> dict:
    """
    Walk forward from signal_idx + 1 to find first TP1/TP2/SL hit.
    Uses candle high/low to check if level was touched intra-bar.
    """
    adj_entry = entry + spread if direction == "BUY" else entry - spread
    risk = abs(adj_entry - sl)

    for j in range(signal_idx + 1, len(df_m5_full)):
        c = df_m5_full.iloc[j]
        if direction == "BUY":
            if c["low"] <= sl:
                return {"outcome": "loss", "price": sl, "pnl_r": -1.0, "bars_held": j - signal_idx}
            if c["high"] >= tp2:
                pnl = abs(tp2 - adj_entry) / risk if risk > 0 else 0
                return {"outcome": "tp2", "price": tp2, "pnl_r": round(pnl, 2), "bars_held": j - signal_idx}
            if c["high"] >= tp1:
                pnl = abs(tp1 - adj_entry) / risk if risk > 0 else 0
                return {"outcome": "tp1", "price": tp1, "pnl_r": round(pnl, 2), "bars_held": j - signal_idx}
        else:  # SELL
            if c["high"] >= sl:
                return {"outcome": "loss", "price": sl, "pnl_r": -1.0, "bars_held": j - signal_idx}
            if c["low"] <= tp2:
                pnl = abs(tp2 - adj_entry) / risk if risk > 0 else 0
                return {"outcome": "tp2", "price": tp2, "pnl_r": round(pnl, 2), "bars_held": j - signal_idx}
            if c["low"] <= tp1:
                pnl = abs(tp1 - adj_entry) / risk if risk > 0 else 0
                return {"outcome": "tp1", "price": tp1, "pnl_r": round(pnl, 2), "bars_held": j - signal_idx}

    return {"outcome": "expired", "price": None, "pnl_r": 0.0, "bars_held": len(df_m5_full) - signal_idx}


def run_backtest(symbol: str, days: int = 180) -> List[dict]:
    """
    Fetch historical data and walk forward through M5 bars.
    Returns list of signal result dicts.
    """
    print(f"\n[backtest] {symbol} — {days} days")
    spread = config.SPREAD.get(symbol, config.SPREAD["_default"])

    # Fetch maximum available history
    d1_count  = min(config.D1_COUNT  + days, 500)
    h4_count  = min(config.H4_COUNT  + days * 6, 3000)
    h1_count = min(config.H1_COUNT + days * 24, 10000)
    m5_count = min(config.M5_COUNT + days * 288, 100000)  # 288 M5 bars per day

    print(f"  Fetching D1×{d1_count}, H4×{h4_count}, H1×{h1_count}, M5×{m5_count}...")
    try:
        df_d1_full = mt5_client.get_candles(symbol, "D1", d1_count)
        df_h4_full = mt5_client.get_candles(symbol, "H4", h4_count)
        df_h1_full = mt5_client.get_candles(symbol, "H1", h1_count)
        df_m5_full = mt5_client.get_candles(symbol, "M5", m5_count)
    except Exception as e:
        print(f"  [ERROR] Could not fetch data: {e}")
        return []

    cutoff_time = df_m5_full["time"].max() - timedelta(days=days)
    start_idx = df_m5_full[df_m5_full["time"] >= cutoff_time].index[0]

    signals: List[dict] = []
    last_signal_time: datetime = None

    # Filter breakdown counters
    f: Dict[str, int] = {
        "outside_session": 0, "news_blackout": 0, "h4_h1_bias_neutral": 0,
        "corr_block": 0, "atr_out_of_range": 0, "insufficient_data": 0,
        "no_sweep": 0, "no_confirmation": 0, "no_fvg": 0,
        "sl_invalid": 0, "sl_too_close": 0, "rr_fail": 0, "antispam": 0,
        "low_confidence": 0, "equal_hl_no_mss": 0, "other": 0,
    }

    total_bars = len(df_m5_full) - start_idx
    print(f"  Walking {total_bars} M5 bars from {cutoff_time.date()} ...")

    for idx in range(start_idx, len(df_m5_full)):
        if (idx - start_idx) % 2000 == 0 and idx > start_idx:
            pct = (idx - start_idx) / total_bars * 100
            print(f"  ... {pct:.0f}%  signals so far: {len(signals)}", flush=True)
        bar_time = df_m5_full.iloc[idx]["time"]
        if hasattr(bar_time, "to_pydatetime"):
            bar_time = bar_time.to_pydatetime()
        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        # Anti-spam
        if last_signal_time and (bar_time - last_signal_time) < timedelta(hours=config.ANTISPAM_HOURS):
            f["antispam"] += 1
            continue

        # Slice each TF to bars available at this M15 bar time
        df_d1  = df_d1_full[df_d1_full["time"] <= bar_time].tail(config.D1_COUNT)
        df_h4  = df_h4_full[df_h4_full["time"] <= bar_time].tail(config.H4_COUNT)
        df_h1  = df_h1_full[df_h1_full["time"] <= bar_time].tail(config.H1_COUNT)
        df_m5 = df_m5_full.iloc[:idx + 1].tail(config.M5_COUNT)

        if len(df_m5) < 50:
            f["insufficient_data"] += 1
            continue

        sig, rejection = analyze(
            symbol=symbol,
            df_d1=df_d1.reset_index(drop=True),
            df_h4=df_h4.reset_index(drop=True),
            df_h1=df_h1.reset_index(drop=True),
            df_m5=df_m5.reset_index(drop=True),
            news_events=[],        # no live news in backtest
            active_signals=[],
            now_utc=bar_time,
        )

        if sig is None:
            # Categorize rejection
            cat = rejection.split(":")[0] if ":" in rejection else rejection
            f[cat] = f.get(cat, 0) + 1
            continue

        # Simulate outcome
        outcome_info = _simulate_outcome(
            df_m5_full, idx,
            sig.direction, sig.entry, sig.sl, sig.tp1, sig.tp2,
            spread=spread,
        )

        record = {
            **sig.to_dict(),
            "outcome": outcome_info["outcome"],
            "outcome_price": outcome_info["price"],
            "pnl_r": outcome_info["pnl_r"],
            "bars_held": outcome_info["bars_held"],
            "backtest_bar_time": bar_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        signals.append(record)
        last_signal_time = bar_time

        print(
            f"  [{bar_time:%m-%d %H:%M}]  {sig.direction} {symbol}  "
            f"SL:{sig.sl}  Entry:{sig.entry}  TP1:{sig.tp1}  TP2:{sig.tp2}  "
            f"RR:{sig.rr}R  Conf:{sig.confidence_score}%  "
            f">> {outcome_info['outcome'].upper()}  pnl:{outcome_info['pnl_r']:+.1f}R"
        )

    # Print summary
    wins   = sum(1 for s in signals if s["outcome"] in ("tp1", "tp2"))
    losses = sum(1 for s in signals if s["outcome"] == "loss")
    total  = wins + losses
    total_r = sum(s["pnl_r"] for s in signals if s["outcome"] != "expired")
    win_rate = round(wins / total * 100, 1) if total > 0 else 0

    print(f"\n  -- {symbol} Results ({days}d) --")
    print(f"  Signals  : {len(signals)}  |  Closed: {total}  |  Win: {wins}  Loss: {losses}")
    print(f"  Win Rate : {win_rate}%  |  Total PnL: {total_r:+.1f}R")
    print(f"  Filter breakdown: {json.dumps(f, indent=2)}")

    return signals


def run_all(days: int = 180) -> None:
    """Run backtest for all symbols and save aggregated results."""
    json_store.ensure_data_dir()
    all_results = []

    for symbol in config.SYMBOLS:
        results = run_backtest(symbol, days)
        all_results.extend(results)

    json_store.save(config.BACKTEST_FILE, all_results)
    print(f"\n[backtest] Saved {len(all_results)} records -> {config.BACKTEST_FILE}")

    # Overall summary
    wins   = sum(1 for s in all_results if s["outcome"] in ("tp1", "tp2"))
    losses = sum(1 for s in all_results if s["outcome"] == "loss")
    total  = wins + losses
    total_r = sum(s["pnl_r"] for s in all_results if isinstance(s.get("pnl_r"), (int, float)))
    print(f"\n  OVERALL — {wins}W/{losses}L  ({round(wins/total*100,1) if total else 0}%)  {total_r:+.1f}R")


def probe() -> None:
    """
    Quick diagnostic: fetch 5 D1 bars per symbol and print what arrives.
    Run before a full backtest to confirm MT5 data is reachable.
    """
    print("\n[probe] MT5 data connectivity check")
    for symbol in config.SYMBOLS:
        mt5_symbol = config.MT5_SYMBOL_MAP.get(symbol, symbol)
        try:
            df = mt5_client.get_candles(symbol, "D1", 5)
            if df.empty:
                print(f"  {symbol} ({mt5_symbol}): EMPTY — broker may not have this symbol")
            else:
                latest = df["time"].iloc[-1].strftime("%Y-%m-%d")
                print(f"  {symbol} ({mt5_symbol}): OK  {len(df)} bars, latest={latest}")
        except Exception as e:
            print(f"  {symbol} ({mt5_symbol}): ERROR — {e}")


def run_verbose(symbol: str = "XAUUSD", days: int = 1) -> None:
    """
    Print rejection reason for every in-session bar over `days`.
    Use this to find which gate is blocking signals.
    """
    from engine.signal_engine import analyze
    from core import session as sess_mod

    print(f"\n[verbose] {symbol} — {days}d bar-by-bar rejection trace")
    spread = config.SPREAD.get(symbol, config.SPREAD["_default"])

    d1_count = min(config.D1_COUNT + days, 500)
    h4_count = min(config.H4_COUNT + days * 6, 3000)
    h1_count = min(config.H1_COUNT + days * 24, 10000)
    m5_count = min(config.M5_COUNT + days * 288, 100000)

    try:
        df_d1_full = mt5_client.get_candles(symbol, "D1", d1_count)
        df_h4_full = mt5_client.get_candles(symbol, "H4", h4_count)
        df_h1_full = mt5_client.get_candles(symbol, "H1", h1_count)
        df_m5_full = mt5_client.get_candles(symbol, "M5", m5_count)
    except Exception as e:
        print(f"  [ERROR] {e}")
        return

    cutoff_time = df_m5_full["time"].max() - timedelta(days=days)
    start_idx   = df_m5_full[df_m5_full["time"] >= cutoff_time].index[0]

    printed = 0
    for idx in range(start_idx, len(df_m5_full)):
        bar_time = df_m5_full.iloc[idx]["time"]
        if hasattr(bar_time, "to_pydatetime"):
            bar_time = bar_time.to_pydatetime()
        if bar_time.tzinfo is None:
            bar_time = bar_time.replace(tzinfo=timezone.utc)

        # Only trace session bars
        valid, _ = sess_mod.is_valid_session(symbol, bar_time)
        if not valid:
            continue

        df_d1 = df_d1_full[df_d1_full["time"] <= bar_time].tail(config.D1_COUNT)
        df_h4 = df_h4_full[df_h4_full["time"] <= bar_time].tail(config.H4_COUNT)
        df_h1 = df_h1_full[df_h1_full["time"] <= bar_time].tail(config.H1_COUNT)
        df_m5 = df_m5_full.iloc[:idx + 1].tail(config.M5_COUNT)

        _, rejection = analyze(
            symbol=symbol,
            df_d1=df_d1.reset_index(drop=True),
            df_h4=df_h4.reset_index(drop=True),
            df_h1=df_h1.reset_index(drop=True),
            df_m5=df_m5.reset_index(drop=True),
            news_events=[], active_signals=[], now_utc=bar_time,
        )

        reason = rejection if rejection else "SIGNAL OK"
        print(f"  {bar_time:%m-%d %H:%M}  {reason}")
        printed += 1
        if printed >= 200:
            print("  ... (capped at 200 bars)")
            break


def run_short(days: int = 5) -> None:
    """
    Run a 5-day backtest per symbol and print the full filter breakdown.
    Fast way to see which gate is blocking signals.
    """
    print(f"\n[backtest] Short diagnostic run ({days}d per symbol)")
    for symbol in config.SYMBOLS:
        results = run_backtest(symbol, days=days)
        if results:
            print(f"  {symbol}: {len(results)} signal(s) found")
        else:
            print(f"  {symbol}: 0 signals — see filter breakdown above")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe",   action="store_true", help="quick MT5 data check")
    parser.add_argument("--short",   action="store_true", help="5-day diagnostic run")
    parser.add_argument("--verbose", action="store_true", help="bar-by-bar rejection trace (1d XAUUSD)")
    parser.add_argument("--symbol",  type=str, default=None, help="run single symbol only, e.g. --symbol XAUUSD")
    parser.add_argument("days",      nargs="?", type=int, default=180)
    args = parser.parse_args()

    mt5_client.initialize()
    try:
        if args.probe:
            probe()
        elif args.short:
            run_short()
        elif args.verbose:
            run_verbose()
        elif args.symbol:
            results = run_backtest(args.symbol.upper(), days=args.days)
            json_store.save(config.BACKTEST_FILE, results)
        else:
            run_all(days=args.days)
    finally:
        mt5_client.shutdown()
