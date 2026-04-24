"""
main.py — Entry point for the ICT Forex Signal Bot.

Usage:
    python main.py              # run live scanner
    python main.py --report     # print performance report and exit
    python main.py --backtest [days]  # run backtest and exit
"""

import asyncio
import sys
import traceback

import config
from storage import json_store
from services import mt5_client, telegram


async def run_scanner() -> None:
    from scanner.realtime_scanner import ForexScanner
    scanner = ForexScanner()
    await scanner.run_forever()


def run_report() -> None:
    from analytics.reporter import print_summary
    print_summary()


def run_backtest(days: int = 180, symbol: str = None) -> None:
    from backtest.backtester import run_all, run_backtest as run_single
    if symbol:
        run_single(symbol.upper(), days=days)
    else:
        run_all(days=days)


def main() -> None:
    args = sys.argv[1:]

    if "--report" in args:
        run_report()
        return

    if "--backtest" in args:
        idx = args.index("--backtest")
        days = int(args[idx + 1]) if idx + 1 < len(args) and args[idx + 1].isdigit() else 180
        symbol = None
        if "--symbol" in args:
            sidx = args.index("--symbol")
            symbol = args[sidx + 1] if sidx + 1 < len(args) else None
        mt5_client.initialize()
        try:
            run_backtest(days, symbol=symbol)
        finally:
            mt5_client.shutdown()
        return

    # Default: live scanner
    try:
        config.validate()
    except ValueError as e:
        print(f"[ERROR] Config validation failed: {e}")
        sys.exit(1)

    json_store.ensure_data_dir()

    print("[main] Connecting to MetaTrader5...")
    try:
        mt5_client.initialize()
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        telegram.send_error_alert(f"Bot failed to start: {e}")
        sys.exit(1)

    print(f"[main] MT5 connected. Monitoring: {', '.join(config.SYMBOLS)}")
    print(f"[main] Scan interval: {config.LOOP_INTERVAL}s  |  Anti-spam: {config.ANTISPAM_HOURS}h")
    print(f"[main] Min RR: {config.MIN_RR}  |  News blackout: "
          f"{config.NEWS_BLACKOUT_BEFORE_MINS}m before / {config.NEWS_BLACKOUT_AFTER_MINS}m after")

    try:
        asyncio.run(run_scanner())
    except KeyboardInterrupt:
        print("\n[main] Stopped by user.")
    except Exception:
        err = traceback.format_exc()
        print(f"[ERROR] Unexpected error:\n{err}")
        telegram.send_error_alert(f"Bot crashed:\n{err[:500]}")
    finally:
        mt5_client.shutdown()
        print("[main] MT5 disconnected. Bye.")


if __name__ == "__main__":
    main()
