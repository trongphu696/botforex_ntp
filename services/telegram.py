"""
Telegram alert service — formats signals as HTML messages and sends
them via the Bot API with exponential-backoff retry.
"""

import time
from datetime import timedelta
import requests
import config
from core.models import Signal

_UTC7 = timedelta(hours=7)


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"


def format_signal(signal: Signal, win_rate_info: dict = None) -> str:
    """Build an HTML-formatted Telegram message for the given signal."""
    emoji = "🟢" if signal.direction == "BUY" else "🔴"
    sl_note = (
        f"below {signal.swept_level_type} sweep low"
        if signal.direction == "BUY"
        else f"above {signal.swept_level_type} sweep high"
    )

    # Entry context
    price_in_fvg = signal.fvg_bottom <= signal.entry <= signal.fvg_top
    entry_note = "immediate entry" if price_in_fvg else "limit order — wait for retrace"

    # Win rate line
    if win_rate_info and win_rate_info.get("total", 0) >= 10:
        wr_pct  = round(win_rate_info["rate"] * 100)
        wins    = win_rate_info["wins"]
        losses  = win_rate_info["losses"]
        wr_line = f"📉 Win Rate (30d): <b>{wr_pct}%</b>  ({wins}W / {losses}L)"
    else:
        total = win_rate_info.get("total", 0) if win_rate_info else 0
        wr_line = f"📉 Win Rate (30d): <i>N/A — building sample ({total}/10)</i>"

    # Low confidence warning
    conf_warning = ""
    if signal.confidence_score < 65:
        conf_warning = "\n⚡ <i>Low confidence — observe only</i>"

    setup_str = " + ".join(signal.setup_tags)

    # Timestamp: UTC+7 display ("23/04 16:15 ICT")
    try:
        from datetime import datetime, timezone
        ts_utc = datetime.fromisoformat(signal.timestamp.replace("Z", "+00:00"))
        ts_vn  = ts_utc + _UTC7
        ts_display = ts_vn.strftime("%d/%m %H:%M ICT")
        ts_utc_display = ts_utc.strftime("%H:%M UTC")
    except Exception:
        ts_display = signal.timestamp
        ts_utc_display = signal.timestamp

    # Split-lot trade management block
    split_block = ""
    if config.USE_SPLIT_LOTS:
        split_block = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📦 <b>Quản lý 2 Lot (mỗi lot risk 1%)</b>\n"
            f"  Lot 1 → đóng tại TP1  (<b>{signal.tp1}</b>)\n"
            f"  Lot 2 → sau TP1, kéo SL về Entry  (<b>{signal.entry}</b>)\n"
            f"  Lot 2 → target TP2  (<b>{signal.tp2}</b>)\n"
        )

    msg = (
        f"{emoji} <b>{signal.direction} {signal.symbol}</b>  |  "
        f"Confidence: <b>{signal.confidence_score}%</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Entry   : <b>{signal.entry}</b>  ({entry_note})\n"
        f"🛑 SL      : <b>{signal.sl}</b>  ({sl_note})\n"
        f"🎯 TP1     : <b>{signal.tp1}</b>  — RR <b>{signal.rr}R</b>\n"
        f"🎯 TP2     : <b>{signal.tp2}</b>  — RR <b>{signal.rr_tp2}R</b>\n"
        f"{split_block}"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Setup   : {setup_str}\n"
        f"💧 Swept   : {signal.swept_level_type} @ {signal.swept_level_price}\n"
        f"📈 Bias    : H4 {signal.bias_h4.capitalize()} | "
        f"H1 {'&gt;' if signal.bias_h1_ema == 'above' else '&lt;'} EMA200\n"
        f"⏰ Session : {signal.session}  |  {ts_utc_display}"
        f"{conf_warning}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{wr_line}\n"
        f"🕐 {ts_display}  ({ts_utc_display})\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <i>Signal only — no auto-execution. Manage your own risk.</i>"
    )
    return msg


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """
    POST to Telegram sendMessage with exponential-backoff retry (1s, 2s, 4s).
    Returns True on success, False on final failure (never raises).
    """
    payload = {"chat_id": config.CHAT_ID, "text": text, "parse_mode": parse_mode}
    for attempt in range(3):
        try:
            resp = requests.post(_api_url("sendMessage"), data=payload, timeout=10)
            if resp.status_code == 200:
                return True
            print(f"[telegram] HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            print(f"[telegram] Request error (attempt {attempt+1}): {exc}")
        time.sleep(2 ** attempt)  # 1s, 2s, 4s
    return False


def send_signal(signal: Signal, win_rate_info: dict = None) -> bool:
    """Format and send a trading signal alert."""
    text = format_signal(signal, win_rate_info)
    return send_message(text)


def send_error_alert(message: str) -> None:
    """Send a plain-text error notification (best effort)."""
    send_message(f"⚠️ BOT ERROR:\n{message}", parse_mode="HTML")
