# telegram_bot.py — Gửi tín hiệu ICT qua Telegram Bot API

import requests

from config import BOT_TOKEN, CHAT_ID

# Endpoint Telegram Bot API
_TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def format_message(data: dict, win_rate_info: dict) -> str:
    """
    Tạo nội dung tin nhắn HTML để gửi lên Telegram.

    Định dạng:
    - Emoji + tên tín hiệu (BUY/SELL)
    - Entry, SL, TP1, TP2
    - Thông tin setup ICT (Liquidity Sweep, FVG, OB)
    - Kill Zone, H4 Bias
    - Win rate 30 ngày
    - Thời gian UTC
    - Cảnh báo chỉ mang tính tham khảo
    """
    signal = data["signal"]
    symbol = data["symbol"]

    # Emoji và màu theo chiều giao dịch
    if signal == "BUY":
        signal_emoji = "🟢"
        signal_label = "BUY"
    else:
        signal_emoji = "🔴"
        signal_label = "SELL"

    # Tên hiển thị cặp tiền (thay _ bằng /)
    symbol_display = symbol.replace("_", "/")

    # Thông tin win rate
    wins   = win_rate_info["wins"]
    losses = win_rate_info["losses"]
    total  = win_rate_info["total"]
    rate   = win_rate_info["rate"]

    if total < 10:
        wr_text = f"N/A (chưa đủ {total}/10 lệnh)"
    else:
        wr_pct  = int(rate * 100)
        wr_text = f"{wr_pct}% ({wins}W/{losses}L)"

    # Format thời gian UTC thân thiện: "14/04 09:15 UTC"
    try:
        from datetime import datetime
        dt = datetime.strptime(data["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
        time_display = dt.strftime("%d/%m %H:%M UTC")
    except ValueError:
        time_display = data["timestamp"]

    # Kẻ ngang dùng ký tự Unicode (Telegram HTML mode hỗ trợ)
    sep = "━━━━━━━━━━━━━━━━━━"

    lines = [
        f"{signal_emoji} <b>{signal_label} {symbol_display}</b> | ICT Setup",
        sep,
        f"📍 Entry  : <b>{data['entry']}</b>",
        f"🛑 SL     : <b>{data['sl']}</b>",
        f"🎯 TP1    : <b>{data['tp1']}</b>  (50%)",
        f"🎯 TP2    : <b>{data['tp2']}</b>  (50%)",
        sep,
        f"📊 Setup  : {data['setup']}",
        f"⏰ Zone   : {data['zone']}",
        f"📈 H4 Bias: {data['bias']}",
        f"📉 Win Rate (30d): {wr_text}",
        f"🕐 {time_display}",
        sep,
        "⚠️ <i>Chỉ mang tính tham khảo</i>",
    ]

    return "\n".join(lines)


def send_signal(data: dict, win_rate_info: dict) -> None:
    """
    Gửi tín hiệu giao dịch tới Telegram.

    Tham số:
        data           : dict tín hiệu từ ict_engine.analyze()
        win_rate_info  : dict từ signal_scorer.get_win_rate()

    Raise:
        RuntimeError nếu Telegram API trả về lỗi
    """
    message = format_message(data, win_rate_info)

    payload = {
        "chat_id":    CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        # Tắt preview link để tin nhắn gọn hơn
        "disable_web_page_preview": True,
    }

    response = requests.post(_TELEGRAM_URL, json=payload, timeout=10)

    if response.status_code != 200:
        raise RuntimeError(
            f"Telegram API lỗi {response.status_code}: {response.text}"
        )
