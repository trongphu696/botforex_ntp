# config.py — Tải cấu hình từ file .env

import os
from dotenv import load_dotenv

load_dotenv()

# --- Thông tin Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID   = os.getenv("CHAT_ID", "")

# --- Danh sách cặp tiền cần theo dõi ---
SYMBOLS = ["XAU_USD", "EUR_USD", "GBP_USD", "USD_JPY"]

# --- Mapping sang tên symbol của MT5 (tùy broker) ---
MT5_SYMBOLS = {
    "XAU_USD": "XAUUSDm",
    "EUR_USD": "EURUSDm",
    "GBP_USD": "GBPUSDm",
    "USD_JPY": "USDJPYm",
}

# ---------------------------------------------------------------------------
# Kill Zones — ICT Standard (UTC)
# ---------------------------------------------------------------------------
# London Kill Zone : 02:00–05:00 UTC  ← Pre-London / Frankfurt open
#                                       Đây là lúc smart money sweep stops trước London open
# New York Kill Zone: 07:00–10:00 UTC ← NY macro open session
# London Close      : 10:00–12:00 UTC ← Institutional close / London-NY overlap
#
# LƯU Ý: Bản cũ dùng (7,10) gán nhầm là "London Open" nhưng đây thực chất là NY KZ.
# Bản cũ dùng (12,15) gán nhầm là "NY Open" nhưng đây là NY mid-session.
KILL_ZONES = {
    "London Kill Zone":   (2, 5),
    "New York Kill Zone": (7, 10),
    "London Close":       (10, 12),
}

# ---------------------------------------------------------------------------
# Asia Session (UTC)
# ---------------------------------------------------------------------------
# 20:00–00:00 UTC: Sydney + Tokyo build liquidity pool
# London Kill Zone (02–05 UTC) sẽ sweep range này để lấy stops
#
# Cách dùng: (start=20, end=0) — end=0 là sentinel nghĩa là đến nửa đêm
# Tức là filter giờ: 20 ≤ hour ≤ 23
ASIA_HOURS = (20, 0)

# ---------------------------------------------------------------------------
# Broker timezone
# ---------------------------------------------------------------------------
# Dùng để tính D1/weekly boundary trong backtest.
# Live: mt5_client đã strip forming candle tự động.
BROKER_TIMEZONE_OFFSET = 2   # GMT+2 standard (thay 3 khi DST)

# --- Quản lý vốn ---
ACCOUNT_SIZE = 1_000
RISK_PCT     = 0.1

# --- Chu kỳ vòng lặp ---
LOOP_INTERVAL = 60

# ---------------------------------------------------------------------------
# ICT Engine — Hyperparameters
# ---------------------------------------------------------------------------

# Risk/Reward tối thiểu
MIN_RR = 1

# ATR
ATR_PERIOD  = 14
# Buffer ATR trên/dưới SL structure (nhỏ hơn 0.5 vì SL đã structure-based)
ATR_MULT_SL = 0.3

# ---------------------------------------------------------------------------
# Swing strength — tăng n để loại noise, bắt structural swing thật sự
# ---------------------------------------------------------------------------
D1_SWING_N  = 5   # D1 structural pivot: cao hơn 5 bars hai bên
H4_SWING_N  = 3   # H4 intermediate pivot
M15_SWING_N = 2   # M15 short-term pivot (dùng cho CHOCH reference)

# ---------------------------------------------------------------------------
# CHOCH
# ---------------------------------------------------------------------------
CHOCH_BODY_FACTOR    = 0.6
CHOCH_LOOKBACK       = 20   # bars trước sweep để tìm swing level cần phá
CHOCH_MAX_BARS_AFTER = 20   # bars SAU sweep để tìm CHOCH displacement (~5 giờ M15)
                             # Quá 20 bars = setup đã expired, không còn fresh

# ---------------------------------------------------------------------------
# M5 Confirmation
# ---------------------------------------------------------------------------
M5_BODY_FACTOR    = 0.5
M5_MAX_WICK_RATIO = 0.35

# ---------------------------------------------------------------------------
# Lookback windows
# ---------------------------------------------------------------------------
SWEEP_LOOKBACK     = 20   # equal H/L reference window (bars trước sweep candle)
SWEEP_MAX_LOOKBACK = 40   # freshness: sweep tối đa cũ N bars từ hiện tại (~10 giờ)
FVG_LOOKBACK       = 30
OB_LOOKBACK        = 20

# ---------------------------------------------------------------------------
# FVG minimum size
# ---------------------------------------------------------------------------
# FVG quá nhỏ = noise, không đủ để tạo reaction
MIN_FVG_ATR_RATIO = 0.3   # FVG gap ≥ 30% ATR(14)

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
MAX_TRADES_PER_SESSION = 2

# Số nến lấy
D1_COUNT  = 25
M15_COUNT = 200   # tăng từ 150 để đảm bảo có đủ Asia range data (20:00 UTC hôm qua)

# ---------------------------------------------------------------------------
# Equal Highs/Lows quality filter
# ---------------------------------------------------------------------------
EQUAL_HL_MIN_TOUCHES = 2
EQUAL_HL_TOLERANCE   = 0.0003   # 0.03% ~ 3 pip trên EUR/USD

# ---------------------------------------------------------------------------
# Volatility Regime
# ---------------------------------------------------------------------------
VOLATILITY_MIN_ATR_MULT = 0.5
VOLATILITY_MAX_ATR_MULT = 3.0
SKIP_RANGING_MARKET     = True   # True = skip tín hiệu khi H4 đang chop/ranging

# ---------------------------------------------------------------------------
# Bias alignment
# ---------------------------------------------------------------------------
STRICT_BIAS_ALIGNMENT = True

# ---------------------------------------------------------------------------
# Trade lifecycle metadata
# ---------------------------------------------------------------------------
SESSION_TIMEOUT_HOURS = 3

# ---------------------------------------------------------------------------
# Spread + Slippage (đơn vị giá)
# ---------------------------------------------------------------------------
SPREAD = {
    "XAU_USD": 0.30,
    "EUR_USD": 0.00010,
    "GBP_USD": 0.00015,
    "USD_JPY": 0.015,
    "_default": 0.00010,
}
SLIPPAGE = {
    "XAU_USD": 0.20,
    "EUR_USD": 0.00005,
    "GBP_USD": 0.00005,
    "USD_JPY": 0.010,
    "_default": 0.00005,
}


def validate_config():
    missing = []
    for var in ["BOT_TOKEN", "CHAT_ID"]:
        if not os.getenv(var):
            missing.append(var)
    if missing:
        raise EnvironmentError(
            f"Thiếu các biến môi trường trong .env: {', '.join(missing)}"
        )
