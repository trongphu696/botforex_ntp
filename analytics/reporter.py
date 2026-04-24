"""
Analytics reporter — computes win rate, drawdown, and performance metrics
from signals.json. Also updates open signal outcomes based on current prices.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import config
from storage import json_store


def _parse_ts(ts_str: str) -> Optional[datetime]:
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return ts.astimezone(timezone.utc)
    except Exception:
        return None


def get_win_rate(symbol: str = None, days: int = 30) -> dict:
    """
    Load signals.json and compute win/loss metrics over the last `days` days.
    Optionally filter by symbol.
    """
    signals = json_store.load(config.SIGNALS_FILE)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    filtered = []
    for s in signals:
        ts = _parse_ts(s.get("timestamp", ""))
        if ts is None or ts < cutoff:
            continue
        if symbol and s.get("symbol") != symbol:
            continue
        if s.get("status") not in ("tp1", "tp2", "loss"):
            continue
        filtered.append(s)

    wins   = sum(1 for s in filtered if s["status"] in ("tp1", "tp2"))
    losses = sum(1 for s in filtered if s["status"] == "loss")
    total  = wins + losses

    rr_list = [s["rr"] for s in filtered if isinstance(s.get("rr"), (int, float))]
    avg_rr = round(sum(rr_list) / len(rr_list), 2) if rr_list else 0.0

    return {
        "wins": wins,
        "losses": losses,
        "rate": round(wins / total, 3) if total > 0 else 0.0,
        "total": total,
        "avg_rr": avg_rr,
    }


def get_performance_metrics() -> dict:
    """Full performance breakdown: by symbol, session, setup, and overall."""
    signals = json_store.load(config.SIGNALS_FILE)
    closed = [s for s in signals if s.get("status") in ("tp1", "tp2", "loss")]

    if not closed:
        return {"by_symbol": {}, "by_session": {}, "by_setup": {}, "overall": {}}

    def _bucket(key_fn):
        buckets: Dict[str, dict] = {}
        for s in closed:
            key = key_fn(s)
            if key not in buckets:
                buckets[key] = {"wins": 0, "losses": 0, "total": 0, "confidence_sum": 0}
            b = buckets[key]
            b["total"] += 1
            b["confidence_sum"] += s.get("confidence_score", 0)
            if s["status"] in ("tp1", "tp2"):
                b["wins"] += 1
            else:
                b["losses"] += 1
        for key, b in buckets.items():
            b["win_rate"] = round(b["wins"] / b["total"], 3) if b["total"] > 0 else 0.0
            b["avg_confidence"] = round(b["confidence_sum"] / b["total"]) if b["total"] > 0 else 0
            del b["confidence_sum"]
        return buckets

    by_symbol  = _bucket(lambda s: s.get("symbol", "unknown"))
    by_session = _bucket(lambda s: s.get("session", "unknown"))

    def _setup_key(s):
        parts = s.get("setup_tags", [])
        key_parts = [p for p in parts if p in ("MSS", "BOS", "FVG", "Displacement")]
        return "+".join(key_parts) if key_parts else "other"

    by_setup = _bucket(_setup_key)

    total_wins = sum(1 for s in closed if s["status"] in ("tp1", "tp2"))
    total = len(closed)
    best_sym = max(by_symbol, key=lambda k: by_symbol[k]["win_rate"]) if by_symbol else ""

    overall = {
        "total_signals": total,
        "wins": total_wins,
        "win_rate": round(total_wins / total, 3) if total > 0 else 0.0,
        "best_symbol": best_sym,
    }

    metrics = {
        "by_symbol": by_symbol,
        "by_session": by_session,
        "by_setup": by_setup,
        "overall": overall,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    json_store.save(config.METRICS_FILE, [metrics])
    return metrics


def update_open_signal_outcomes(current_prices: Dict[str, float]) -> None:
    """
    Check all 'open' signals against current prices.
    BUY:  price >= tp2 → tp2; price >= tp1 → tp1; price <= sl → loss
    SELL: price <= tp2 → tp2; price <= tp1 → tp1; price >= sl → loss
    Expire signals older than SIGNAL_EXPIRE_HOURS.
    """
    now_utc = datetime.now(timezone.utc)
    expire_cutoff = now_utc - timedelta(hours=config.SIGNAL_EXPIRE_HOURS)

    def match(rec: dict) -> bool:
        return rec.get("status") == "open"

    def update(rec: dict) -> dict:
        symbol = rec.get("symbol")
        price = current_prices.get(symbol)
        ts = _parse_ts(rec.get("timestamp", ""))

        # Expiry check
        if ts and ts < expire_cutoff:
            rec["status"] = "expired"
            rec["outcome_time"] = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            return rec

        if price is None:
            return rec

        direction = rec.get("direction")
        entry = rec.get("entry", 0)
        sl    = rec.get("sl", 0)
        tp1   = rec.get("tp1", 0)
        tp2   = rec.get("tp2", 0)

        outcome = None
        if direction == "BUY":
            if price >= tp2:
                outcome = "tp2"
            elif price >= tp1:
                outcome = "tp1"
            elif price <= sl:
                outcome = "loss"
        elif direction == "SELL":
            if price <= tp2:
                outcome = "tp2"
            elif price <= tp1:
                outcome = "tp1"
            elif price >= sl:
                outcome = "loss"

        if outcome:
            rec["status"] = outcome
            rec["outcome_price"] = price
            rec["outcome_time"] = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            # pnl in R-multiples
            risk = abs(entry - sl)
            if risk > 0:
                rec["pnl_r"] = round(abs(price - entry) / risk * (1 if outcome != "loss" else -1), 2)

        return rec

    json_store.update_record(config.SIGNALS_FILE, match, update)


def print_summary() -> None:
    """Print a human-readable performance summary to stdout."""
    m = get_performance_metrics()
    overall = m.get("overall", {})
    print("\n" + "=" * 50)
    print("  SIGNAL BOT PERFORMANCE REPORT")
    print("=" * 50)
    print(f"  Total Signals : {overall.get('total_signals', 0)}")
    print(f"  Win Rate      : {overall.get('win_rate', 0)*100:.1f}%")
    print(f"  Best Symbol   : {overall.get('best_symbol', 'N/A')}")
    print()
    print("  BY SYMBOL:")
    for sym, stats in m.get("by_symbol", {}).items():
        print(f"    {sym:8s}  {stats['wins']}W / {stats['losses']}L  "
              f"({stats['win_rate']*100:.0f}%)  conf:{stats['avg_confidence']}")
    print()
    print("  BY SESSION:")
    for sess, stats in m.get("by_session", {}).items():
        print(f"    {sess:20s}  {stats['wins']}W / {stats['losses']}L  "
              f"({stats['win_rate']*100:.0f}%)")
    print("=" * 50 + "\n")
