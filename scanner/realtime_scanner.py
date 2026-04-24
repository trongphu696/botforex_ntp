"""
Realtime Scanner — asyncio event loop that scans all symbols every LOOP_INTERVAL seconds.
For each symbol:
  1. Fetches OHLCV data from MT5 (D1/H4/H1/M15)
  2. Runs the signal engine pipeline
  3. Applies anti-spam (ANTISPAM_HOURS between same-symbol signals)
  4. Sends Telegram alerts
  5. Logs signals to JSON
  6. Updates open signal outcomes
"""

import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import config
from core.models import Signal
from core import correlation
from engine.signal_engine import analyze
from services import mt5_client, telegram
from services.news_feed import get_events
from storage import json_store
from analytics import reporter


class ForexScanner:

    def __init__(self):
        self._last_signal_time: Dict[str, datetime] = {}
        self._active_signals: List[Signal] = []
        self._news_last_fetched: Optional[datetime] = None
        self._news_events: list = []

    # ── News refresh ──────────────────────────────────────────────────────────

    def _refresh_news_if_needed(self) -> None:
        now = datetime.now(timezone.utc)
        ttl = timedelta(seconds=config.NEWS_CACHE_TTL)
        if self._news_last_fetched is None or (now - self._news_last_fetched) >= ttl:
            self._news_events = get_events()
            self._news_last_fetched = now

    # ── Anti-spam check ───────────────────────────────────────────────────────

    def _is_antispam_blocked(self, symbol: str) -> bool:
        last = self._last_signal_time.get(symbol)
        if last is None:
            return False
        now = datetime.now(timezone.utc)
        return (now - last) < timedelta(hours=config.ANTISPAM_HOURS)

    # ── Load persisted active signals at startup ──────────────────────────────

    def _load_active_signals(self) -> None:
        raw = json_store.load(config.SIGNALS_FILE)
        now = datetime.now(timezone.utc)
        self._active_signals = []
        for rec in raw:
            if rec.get("status") == "open":
                try:
                    s = Signal(**{k: rec.get(k) for k in Signal.__dataclass_fields__})
                    self._active_signals.append(s)
                except Exception:
                    pass

    # ── Per-symbol scan ───────────────────────────────────────────────────────

    async def scan_symbol(self, symbol: str) -> dict:
        """Returns a filter breakdown dict for diagnostics."""
        filters = {
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "result": "no_signal",
            "reason": "",
        }

        try:
            # Fetch candles (blocking I/O — run in thread executor)
            loop = asyncio.get_event_loop()
            try:
                tfs = await loop.run_in_executor(
                    None, mt5_client.get_all_timeframes, symbol
                )
            except Exception as e:
                filters["reason"] = f"mt5_fetch_error:{e}"
                return filters

            now_utc = datetime.now(timezone.utc)

            signal, rejection = analyze(
                symbol=symbol,
                df_d1=tfs["D1"],
                df_h4=tfs["H4"],
                df_h1=tfs["H1"],
                df_m5=tfs["M5"],
                news_events=self._news_events,
                active_signals=self._active_signals,
                now_utc=now_utc,
            )

            # Update open signal outcomes
            current_price = await loop.run_in_executor(
                None, mt5_client.get_current_price, symbol
            )
            reporter.update_open_signal_outcomes({symbol: current_price})

            if signal is None:
                filters["reason"] = rejection
                return filters

            # Anti-spam check
            if self._is_antispam_blocked(symbol):
                filters["reason"] = "antispam"
                return filters

            # ── Signal accepted — send + log ──────────────────────────────────
            wr = reporter.get_win_rate(symbol=symbol)
            sent = await loop.run_in_executor(
                None, telegram.send_signal, signal, wr
            )

            if sent:
                json_store.append_record(config.SIGNALS_FILE, signal.to_dict())
                self._active_signals.append(signal)
                self._last_signal_time[symbol] = now_utc
                filters["result"] = "signal_sent"
                filters["signal_id"] = signal.id
                filters["direction"] = signal.direction
                filters["confidence"] = signal.confidence_score
                print(
                    f"[{now_utc:%H:%M}Z] ✅ {signal.direction} {symbol}  "
                    f"Entry:{signal.entry}  SL:{signal.sl}  "
                    f"TP1:{signal.tp1}  RR:{signal.rr}R  Conf:{signal.confidence_score}%"
                )
            else:
                filters["reason"] = "telegram_send_failed"

        except Exception:
            filters["reason"] = "unexpected_error"
            filters["traceback"] = traceback.format_exc()
            telegram.send_error_alert(
                f"scan_symbol({symbol}) error:\n{traceback.format_exc()[:500]}"
            )

        return filters

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run_forever(self) -> None:
        """Main asyncio loop: scan all symbols every LOOP_INTERVAL seconds."""
        print(f"[scanner] Starting — {len(config.SYMBOLS)} symbols, "
              f"interval={config.LOOP_INTERVAL}s")

        json_store.ensure_data_dir()
        self._load_active_signals()

        cycle = 0
        while True:
            cycle += 1
            now = datetime.now(timezone.utc)
            print(f"\n[{now:%Y-%m-%d %H:%M}Z] — Cycle #{cycle}")

            # Refresh news calendar
            self._refresh_news_if_needed()

            # Prune stale active signals from memory
            self._active_signals = correlation.get_active_signals(
                self._active_signals, now
            )

            # Scan all symbols concurrently
            tasks = [self.scan_symbol(sym) for sym in config.SYMBOLS]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Print brief filter summary
            for res in results:
                if isinstance(res, dict):
                    sym = res.get("symbol", "?")
                    result = res.get("result", "no_signal")
                    reason = res.get("reason", "")
                    if result == "signal_sent":
                        pass  # already printed in scan_symbol
                    else:
                        print(f"  {sym:8s}  {reason or 'filtered'}")

            await asyncio.sleep(config.LOOP_INTERVAL)
