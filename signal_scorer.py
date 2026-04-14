# signal_scorer.py — Lưu lịch sử tín hiệu và tính win rate
# Dùng file JSON đơn giản để theo dõi kết quả từng lệnh

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

# Đường dẫn file lưu lịch sử tín hiệu
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "signals_history.json")


# ---------------------------------------------------------------------------
# Đọc / ghi file JSON
# ---------------------------------------------------------------------------

def _load_history() -> list:
    """Đọc toàn bộ lịch sử từ file JSON. Trả về list rỗng nếu chưa có file."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_history(data: list) -> None:
    """Ghi toàn bộ lịch sử xuống file JSON."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Lưu tín hiệu mới
# ---------------------------------------------------------------------------

def save_signal(signal_dict: dict) -> None:
    """
    Lưu một tín hiệu mới vào lịch sử với status = "open".

    Tín hiệu sẽ được cập nhật thành "win" hoặc "loss" sau khi
    giá chạm TP1 hoặc SL.
    """
    history = _load_history()

    record = {
        "symbol":    signal_dict["symbol"],
        "signal":    signal_dict["signal"],
        "entry":     signal_dict["entry"],
        "sl":        signal_dict["sl"],
        "tp1":       signal_dict["tp1"],
        "timestamp": signal_dict["timestamp"],
        "status":    "open",    # Trạng thái ban đầu: chờ kết quả
    }

    history.append(record)
    _save_history(history)


# ---------------------------------------------------------------------------
# Cập nhật kết quả (win/loss) theo giá hiện tại
# ---------------------------------------------------------------------------

def update_outcomes(current_prices: dict) -> None:
    """
    Duyệt tất cả lệnh "open" và cập nhật trạng thái dựa trên giá hiện tại.

    current_prices: dict {symbol: current_close_price}

    Quy tắc:
    - BUY  : nếu giá >= TP1 → "win" | nếu giá <= SL → "loss"
    - SELL : nếu giá <= TP1 → "win" | nếu giá >= SL → "loss"
    """
    history = _load_history()
    changed = False

    for record in history:
        if record["status"] != "open":
            continue

        symbol = record["symbol"]
        price  = current_prices.get(symbol)
        if price is None:
            continue

        sl  = record["sl"]
        tp1 = record["tp1"]

        if record["signal"] == "BUY":
            if price >= tp1:
                record["status"] = "win"
                changed = True
            elif price <= sl:
                record["status"] = "loss"
                changed = True

        elif record["signal"] == "SELL":
            if price <= tp1:
                record["status"] = "win"
                changed = True
            elif price >= sl:
                record["status"] = "loss"
                changed = True

    if changed:
        _save_history(history)


# ---------------------------------------------------------------------------
# Tính win rate
# ---------------------------------------------------------------------------

def get_win_rate(symbol: Optional[str] = None) -> dict:
    """
    Tính win rate dựa trên lịch sử 30 ngày gần nhất.

    Tham số:
        symbol: nếu truyền vào thì chỉ tính cho cặp tiền đó;
                nếu None thì tính tổng tất cả symbol.

    Trả về:
        {"wins": int, "losses": int, "rate": float (0.0–1.0), "total": int}
    """
    history = _load_history()
    cutoff  = datetime.now(tz=timezone.utc) - timedelta(days=30)

    wins   = 0
    losses = 0

    for record in history:
        # Bỏ qua lệnh còn open
        if record["status"] == "open":
            continue

        # Lọc theo thời gian 30 ngày
        try:
            ts = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue

        if ts < cutoff:
            continue

        # Lọc theo symbol nếu có
        if symbol is not None and record["symbol"] != symbol:
            continue

        if record["status"] == "win":
            wins += 1
        elif record["status"] == "loss":
            losses += 1

    total = wins + losses
    rate  = (wins / total) if total > 0 else 0.0

    return {"wins": wins, "losses": losses, "rate": rate, "total": total}


# ---------------------------------------------------------------------------
# Quyết định có nên gửi tín hiệu không
# ---------------------------------------------------------------------------

def should_send_signal(symbol: str) -> bool:
    """
    Kiểm tra win rate của symbol để quyết định có nên gửi tín hiệu không.

    Logic:
    - Nếu chưa đủ 10 lệnh đã đóng → True (chưa đủ mẫu để đánh giá)
    - Nếu win rate >= 50% → True (hiệu suất đạt yêu cầu)
    - Ngược lại → False (tạm dừng tín hiệu vì win rate quá thấp)
    """
    wr = get_win_rate(symbol)

    if wr["total"] < 10:
        return True  # Chưa đủ dữ liệu, cho phép gửi bình thường

    return wr["rate"] >= 0.50
