# main.py — Vòng lặp chính của ICT Forex Signal Bot (v2)

import time
from datetime import datetime, timezone

from config import SYMBOLS, LOOP_INTERVAL, KILL_ZONES, M15_COUNT, validate_config
from mt5_client import initialize as mt5_init, shutdown as mt5_shutdown, get_candles
from ict_engine import analyze, is_kill_zone
from signal_scorer import save_signal, update_outcomes, get_win_rate, should_send_signal
from telegram_bot import send_signal


def log(msg: str) -> None:
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


def _current_session(now_utc: datetime) -> str:
    """Trả về tên kill zone đang active, hoặc chuỗi rỗng."""
    _, zone = is_kill_zone(now_utc)
    return zone


def main():
    validate_config()
    mt5_init()

    log("=" * 60)
    log("  ICT Forex Signal Bot v2 khởi động")
    log(f"  Symbols  : {', '.join(SYMBOLS)}")
    log(f"  Interval : {LOOP_INTERVAL}s")
    log("=" * 60)

    last_signals:  dict[str, str | None] = {s: None for s in SYMBOLS}
    last_session:  dict[str, str]        = {s: ""   for s in SYMBOLS}
    session_count: dict[str, int]        = {s: 0    for s in SYMBOLS}

    while True:
        log("--- Bắt đầu vòng quét ---")
        now_utc          = datetime.now(tz=timezone.utc)
        current_session  = _current_session(now_utc)
        current_prices:  dict[str, float] = {}

        for symbol in SYMBOLS:
            try:
                # Reset bộ đếm khi vào session mới
                if current_session != last_session.get(symbol, ""):
                    if last_session.get(symbol):
                        log(f"  [{symbol}] Session mới ({current_session}), reset trade count")
                    session_count[symbol] = 0
                    last_session[symbol]  = current_session

                log(f"  [{symbol}] Lấy dữ liệu (H4/M15/M5)...")
                df_h4  = get_candles(symbol, "H4",  count=60)
                df_m15 = get_candles(symbol, "M15", count=M15_COUNT)
                df_m5  = get_candles(symbol, "M5",  count=50)

                current_prices[symbol] = float(df_m5["close"].iloc[-1])

                log(f"  [{symbol}] Phân tích ICT (H4→M15→M5) | session trades={session_count[symbol]}...")
                result, reject_reason = analyze(
                    symbol,
                    df_h4,
                    df_m15,
                    df_m5,
                    session_trade_count=session_count[symbol],
                )

                if result is None:
                    # Log lý do từ chối hữu ích (bỏ qua các lý do thông thường)
                    _silent = ("outside kill zone", "max trades per session")
                    if reject_reason and reject_reason not in _silent:
                        log(f"  [{symbol}] Reject: {reject_reason}")
                    continue

                signal = result["signal"]

                if signal == last_signals.get(symbol):
                    log(f"  [{symbol}] Tín hiệu {signal} trùng lần trước, bỏ qua")
                    continue

                if not should_send_signal(symbol):
                    wr     = get_win_rate(symbol)
                    wr_pct = int(wr["rate"] * 100)
                    log(f"  [{symbol}] Win rate {wr_pct}% < 50% ({wr['wins']}W/{wr['losses']}L) — bỏ qua")
                    continue

                wr_info = get_win_rate(symbol)

                log(
                    f"  [{symbol}] ✓ {signal} | Entry={result['entry']} "
                    f"SL={result['sl']} TP1={result['tp1']} TP2={result['tp2']} "
                    f"RR={result.get('rr','?')} | "
                    f"Zone={result['zone']} | H4={result['bias']} | "
                    f"Setup={result['setup']}"
                )

                send_signal(result, wr_info)
                save_signal(result)
                last_signals[symbol]  = signal
                session_count[symbol] += 1

            except Exception as e:
                log(f"  [{symbol}] [ERROR] {type(e).__name__}: {e}")

        if current_prices:
            update_outcomes(current_prices)
            log(f"  Đã cập nhật outcome cho {len(current_prices)} symbol")

        log(f"--- Vòng quét hoàn thành. Chờ {LOOP_INTERVAL}s ---\n")
        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Bot đã dừng bởi người dùng]")
    except EnvironmentError as e:
        print(f"\n[LỖI CẤU HÌNH] {e}")
        print("Vui lòng kiểm tra file .env và điền đầy đủ thông tin.")
    finally:
        mt5_shutdown()
