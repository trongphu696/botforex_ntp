# config.py — Tải cấu hình từ file .env

import os
from dotenv import load_dotenv

# Tải biến môi trường từ file .env trong thư mục hiện tại
load_dotenv()

# --- Thông tin xác thực OANDA ---
OANDA_API_TOKEN  = os.getenv("OANDA_API_TOKEN", "")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", "")
OANDA_ENVIRONMENT = "practice"  # Dùng tài khoản demo (practice)

# --- Thông tin Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID   = os.getenv("CHAT_ID", "")

# --- Danh sách cặp tiền cần theo dõi ---
SYMBOLS = ["XAU_USD", "EUR_USD", "GBP_USD", "USD_JPY"]

# --- Kill Zone (giờ UTC) — chỉ gửi tín hiệu trong khung giờ này ---
# London Open : 02:00 – 05:00 UTC
# New York Open: 07:00 – 10:00 UTC
KILL_ZONES = {
    "London Open":   (2, 5),
    "New York Open": (7, 10),
}

# --- Chu kỳ vòng lặp chính (giây) ---
LOOP_INTERVAL = 60

# --- Kiểm tra cấu hình khi import ---
def validate_config():
    """Kiểm tra các biến môi trường bắt buộc đã được điền chưa."""
    missing = []
    for var in ["OANDA_API_TOKEN", "OANDA_ACCOUNT_ID", "BOT_TOKEN", "CHAT_ID"]:
        if not os.getenv(var):
            missing.append(var)
    if missing:
        raise EnvironmentError(
            f"Thiếu các biến môi trường trong .env: {', '.join(missing)}"
        )
