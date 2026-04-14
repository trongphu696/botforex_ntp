# main.py — Vòng lặp chính của ICT Forex Signal Bot
# Chạy mỗi 60 giây, phân tích từng symbol theo phương pháp ICT Top-Down

import time
from datetime import datetime, timezone

from config import SYMBOLS, LOOP_INTERVAL, validate_config
from oanda_client import get_candles
from ict_engine import analyze
from signal_scorer import save_signal, update_outcomes, get_win_rate, should_send_signal
from telegram_bot import send_signal


def log(msg: str) -> None:
    """In log ra console với timestamp UTC."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


def main():
    """
    Vòng lặp chính của bot.

    Mỗi 60 giây:
    1. Lấy dữ liệu nến H4, M15, M5 từ OANDA cho từng symbol
    2. Chạy phân tích ICT (Kill Zone → H4 bias → M15 setup → M5 confirm)
    3. Nếu có tín hiệu mới khác tín hiệu cũ → kiểm tra win rate → gửi Telegram
    4. Cập nhật kết quả win/loss cho các lệnh đang open
    """
    # Kiểm tra cấu hình trước khi chạy
    validate_config()

    log("=" * 60)
    log("  ICT Forex Signal Bot khởi động")
    log(f"  Symbols  : {', '.join(SYMBOLS)}")
    log(f"  Interval : {LOOP_INTERVAL}s")
    log("=" * 60)

    # Lưu tín hiệu cuối cùng của từng symbol để chống spam
    last_signals: dict[str, str | None] = {s: None for s in SYMBOLS}

    while True:
        log("--- Bắt đầu vòng quét ---")
        current_prices: dict[str, float] = {}

        for symbol in SYMBOLS:
            try:
                log(f"  [{symbol}] Đang lấy dữ liệu nến...")

                # Lấy đủ nến cho từng khung — H4 cần 60, M15 cần 100, M5 cần 50
                df_h4  = get_candles(symbol, "H4",  count=60)
                df_m15 = get_candles(symbol, "M15", count=100)
                df_m5  = get_candles(symbol, "M5",  count=50)

                # Lưu giá hiện tại (nến M5 cuối) để cập nhật win/loss sau
                current_prices[symbol] = df_m5["close"].iloc[-1]

                log(f"  [{symbol}] Đang phân tích ICT (H4→M15→M5)...")
                result = analyze(symbol, df_h4, df_m15, df_m5)

                if result is None:
                    log(f"  [{symbol}] Không có tín hiệu (không đủ điều kiện ICT)")
                    continue

                signal = result["signal"]

                # Chống spam: chỉ gửi khi tín hiệu thay đổi so với lần trước
                if signal == last_signals.get(symbol):
                    log(f"  [{symbol}] Tín hiệu {signal} trùng lần trước, bỏ qua")
                    continue

                # Kiểm tra win rate trước khi gửi
                if not should_send_signal(symbol):
                    wr = get_win_rate(symbol)
                    wr_pct = int(wr["rate"] * 100)
                    log(
                        f"  [{symbol}] Win rate {wr_pct}% < 50% "
                        f"({wr['wins']}W/{wr['losses']}L) — bỏ qua tín hiệu"
                    )
                    continue

                # Lấy win rate để đính kèm vào tin nhắn
                wr_info = get_win_rate(symbol)

                # Gửi tín hiệu lên Telegram
                log(
                    f"  [{symbol}] ✓ Phát tín hiệu {signal} | "
                    f"Entry={result['entry']} SL={result['sl']} "
                    f"TP1={result['tp1']} TP2={result['tp2']} | "
                    f"Setup={result['setup']} Zone={result['zone']}"
                )
                send_signal(result, wr_info)

                # Lưu vào lịch sử và cập nhật trạng thái chống spam
                save_signal(result)
                last_signals[symbol] = signal

            except Exception as e:
                # Bắt lỗi từng symbol riêng — lỗi 1 cặp không làm chết bot
                log(f"  [{symbol}] [ERROR] {type(e).__name__}: {e}")

        # Cập nhật kết quả win/loss cho các lệnh đang mở
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
