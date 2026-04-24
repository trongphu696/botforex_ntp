import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID   = os.getenv("CHAT_ID", "")

# ── Position Sizing ────────────────────────────────────────────────────────────
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", "1000"))
RISK_PCT        = float(os.getenv("RISK_PCT", "1.0"))   # % of balance per trade

# ── MT5 credentials (optional — broker terminal can be pre-logged-in) ───────────
MT5_LOGIN    = os.getenv("MT5_LOGIN", "")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")

# ── Symbols ────────────────────────────────────────────────────────────────────
SYMBOLS = ["XAUUSD", "GBPUSD", "USDJPY", "GBPJPY", "AUDUSD", "NZDUSD"]

# Broker-specific symbol names — adjust suffix for your broker
MT5_SYMBOL_MAP = {
    "XAUUSD": "XAUUSDm",
    "GBPUSD": "GBPUSDm",
    "USDJPY": "USDJPYm",
    "GBPJPY": "GBPJPYm",
    "AUDUSD": "AUDUSDm",
    "NZDUSD": "NZDUSDm",
}

# ── Session windows (UTC hours) [start_inclusive, end_exclusive) ───────────────
SESSION_WINDOWS = {
    "XAUUSD": [(7, 16), (13, 21)],
    "GBPUSD": [(7, 16), (13, 21)],
    "USDJPY": [(0, 9),  (13, 21)],
    "GBPJPY": [(7, 16), (13, 21)],   # GBP active in London + NY
    "AUDUSD": [(0, 9),  (7, 16)],    # AUD active in Asia + London
    "NZDUSD": [(0, 9),  (7, 16)],    # NZD active in Asia + London
}

SESSION_NAMES = {
    (0, 9):   "Asia",
    (7, 16):  "London",
    (13, 21): "New York",
}

ASIA_SESSION_UTC   = (0, 9)
LONDON_SESSION_UTC = (7, 16)
NY_SESSION_UTC     = (13, 21)

# ── Volatility thresholds (minimum ATR(14) on M15 per instrument) ──────────────
ATR_MIN_THRESHOLD = {
    "XAUUSD": 2.0,     # Gold: quiet M5 = $2-3, normal = $4-8
    "GBPUSD": 0.00035,
    "USDJPY": 0.040,
    "GBPJPY": 0.040,   # GBPJPY very volatile, ~40 pip M5 ATR minimum
    "AUDUSD": 0.00025,
    "NZDUSD": 0.00020,
}
ATR_SPIKE_MULTIPLIER = 8.0  # skip if ATR > threshold * multiplier (news spike)
# XAUUSD max = 2.0 × 8 = $16/bar → genuine spike filter

# ── Swing detection ────────────────────────────────────────────────────────────
H4_SWING_N = 3
H1_SWING_N = 2
M5_SWING_N = 2

# ── Equal Highs/Lows ───────────────────────────────────────────────────────────
EQUAL_HL_TOLERANCE_PCT = 0.0003  # 0.03% price tolerance
EQUAL_HL_MIN_TOUCHES   = 2
EQUAL_HL_LOOKBACK      = 50
EQUAL_HL_MAX_CLUSTER_PCT = 0.40  # discard if cluster > 40% of bars (noise)

# ── Sweep / structure ──────────────────────────────────────────────────────────
SWEEP_LOOKBACK       = 30
CHOCH_MAX_BARS_AFTER = 30
DISPLACEMENT_LOOKBACK = 5
DISPLACEMENT_ATR_MULT = 1.0  # body must be >= 1.0 × ATR

# ── FVG ────────────────────────────────────────────────────────────────────────
MIN_FVG_ATR_RATIO = 0.3
FVG_LOOKBACK      = 30

# ── News blackout ──────────────────────────────────────────────────────────────
NEWS_BLACKOUT_BEFORE_MINS = 30
NEWS_BLACKOUT_AFTER_MINS  = 15
NEWS_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
NEWS_CACHE_TTL    = 3600  # seconds
HIGH_IMPACT_KEYWORDS = [
    "CPI", "NFP", "Non-Farm", "FOMC", "Powell", "ECB", "BOE",
    "Interest Rate", "Employment", "GDP", "Inflation",
]

# Symbol → relevant currencies for news filter
SYMBOL_CURRENCIES = {
    "XAUUSD": ["USD"],
    "GBPUSD": ["GBP", "USD"],
    "USDJPY": ["USD", "JPY"],
    "GBPJPY": ["GBP", "JPY"],
    "AUDUSD": ["AUD", "USD"],
    "NZDUSD": ["NZD", "USD"],
}

# ── Correlation ────────────────────────────────────────────────────────────────
CORRELATED_PAIRS = [
    ("GBPUSD", "GBPJPY"),  # same GBP exposure
    ("USDJPY", "GBPJPY"),  # same JPY exposure
    ("AUDUSD", "NZDUSD"),  # highly correlated Pacific pairs
]
XAUUSD_USD_SOFT_BLOCK = True  # warn but don't hard-block

# ── Risk ───────────────────────────────────────────────────────────────────────
MIN_RR           = 1.2    # Minimum RR at TP1
USE_SPLIT_LOTS   = False  # Single-lot: full position exits at TP1 (or TP2 on strong bar)
SL_ATR_BUFFER    = 1.5   # ATR buffer beyond sweep wick — prevents easy SL sweeps
TP_FALLBACK_ATR  = 3.0   # ATR fallback for TP1 when no level (must clear RR>2)
TP2_EXTEND_MULT  = 2.0   # TP2 = TP1 + (TP1-entry) * this

# Minimum SL distance — no tiny SLs that are easily swept on fill
SL_MIN_DISTANCE = {
    "XAUUSD": 15.0,    # Gold: min $15
    "GBPUSD": 0.0015,  # 15 pips
    "USDJPY": 0.15,    # 15 pips
    "GBPJPY": 0.15,    # 15 pips (GBPJPY pip = 0.01)
    "AUDUSD": 0.0015,  # 15 pips
    "NZDUSD": 0.0015,  # 15 pips
}

# ── Indicators ─────────────────────────────────────────────────────────────────
ATR_PERIOD  = 14
EMA200_PERIOD = 200

# ── Scanner ────────────────────────────────────────────────────────────────────
LOOP_INTERVAL  = 60   # seconds between full scan cycles
ANTISPAM_HOURS = 4    # minimum hours between same-symbol signals (prevent same-day re-entry)
SIGNAL_EXPIRE_HOURS = 48

# ── Candle counts ──────────────────────────────────────────────────────────────
D1_COUNT = 30
H4_COUNT = 100
H1_COUNT = 300  # must be > EMA200_PERIOD + 5 (205) with room for warm-up
M5_COUNT = 500   # M5: ~500 bars ≈ 41h, covers recent swings + FVG window

# ── Confidence scoring ─────────────────────────────────────────────────────────
CONFIDENCE_BASE  = 50
CONFIDENCE_CAP   = 95
CONFIDENCE_MIN_SIGNAL = 80   # skip signals below this threshold

# ── Storage paths ──────────────────────────────────────────────────────────────
STORAGE_DIR  = "storage/data"
SIGNALS_FILE = "storage/data/signals.json"
TRADES_FILE  = "storage/data/trades.json"
BACKTEST_FILE = "storage/data/backtest_results.json"
METRICS_FILE  = "storage/data/performance_metrics.json"

# ── Spread/slippage per symbol (pips, for backtest cost model) ─────────────────
SPREAD = {
    "XAUUSD": 0.30,
    "GBPUSD": 0.00012,
    "USDJPY": 0.020,
    "GBPJPY": 0.020,
    "AUDUSD": 0.00012,
    "NZDUSD": 0.00015,
    "_default": 0.00010,
}


# ── Lot Size Config ────────────────────────────────────────────────────────────
# contract_size: units per standard lot (oz for gold, base currency units for FX)
LOT_CONTRACT_SIZE = {
    "XAUUSD": 100,        # 100 troy oz
    "GBPUSD": 100_000,
    "AUDUSD": 100_000,
    "NZDUSD": 100_000,
    "USDJPY": 100_000,
    "GBPJPY": 100_000,
}
# Pairs where quote currency is JPY — P&L needs /entry conversion to USD
JPY_QUOTED = {"USDJPY", "GBPJPY"}

LOT_MIN  = 0.01   # minimum lot size
LOT_STEP = 0.01   # lot increment


def validate():
    """Raise ValueError if required env vars are missing."""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set in .env")
    if not CHAT_ID:
        raise ValueError("CHAT_ID not set in .env")
