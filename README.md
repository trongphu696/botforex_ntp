# ICT Forex Signal Bot

Production-ready Python signal bot implementing an institutional-style strategy across 5 currency pairs. Generates Telegram alerts only — no auto-execution.

## Symbols

XAUUSD · EURUSD · GBPUSD · USDJPY · USDCHF

## Target Performance

- 10–20 signals/week across all symbols
- Win rate: 45–60%
- Minimum RR: 1:2

---

## Strategy Overview

| Layer | Component | Logic |
| --- | --- | --- |
| Trend | H4 Market Structure | HH/HL = bullish, LH/LL = bearish |
| Trend | H1 EMA200 | Price > EMA → long only; < EMA → short only |
| Entry | Liquidity Sweep | PDH/PDL, Asia High/Low, Equal Highs/Lows |
| Context | Wyckoff | Spring, Upthrust, Accumulation, Distribution |
| Confirm | MSS / BOS / Displacement | At least one required post-sweep |
| Entry | Fair Value Gap | 50% retracement of M15 FVG |
| Filter | Volatility (ATR) | Skip low-volatility and news spikes |
| Filter | Session | Per-symbol session windows |
| Filter | News Blackout | ±30/15 min around CPI/NFP/FOMC/Powell/ECB/BOE |
| Filter | Correlation | EURUSD↔USDCHF, GBPUSD↔EURUSD, XAUUSD soft |

---

## Folder Structure

```text
botforex_ntp/
├── main.py                    # Entry point
├── config.py                  # All constants (edit this first)
├── core/                      # Pure strategy logic
│   ├── models.py              # Dataclasses (Signal, FVG, SweepEvent, …)
│   ├── indicators.py          # ATR (Wilder), EMA
│   ├── swing.py               # n-bar pivot detection
│   ├── market_structure.py    # H4 HH/HL + H1 EMA200 combined bias
│   ├── liquidity.py           # PDH/PDL, Asia range, Equal H/L
│   ├── sweep.py               # Liquidity sweep detection
│   ├── wyckoff.py             # Spring/Upthrust/Accum/Dist
│   ├── confirmation.py        # MSS, BOS, Displacement candle
│   ├── fvg.py                 # Fair Value Gap + midpoint entry
│   ├── volatility.py          # ATR threshold filter
│   ├── session.py             # Session window validator
│   ├── news.py                # News blackout logic
│   ├── correlation.py         # Correlated-pair filter
│   ├── risk.py                # SL/TP/RR calculation
│   └── scorer.py              # Confidence scoring (50–95%)
├── engine/
│   └── signal_engine.py       # 13-step orchestration pipeline
├── services/
│   ├── mt5_client.py          # MT5 connection + OHLCV fetcher
│   ├── telegram.py            # Alert formatter + sender
│   └── news_feed.py           # ForexFactory calendar HTTP cache
├── storage/
│   ├── json_store.py          # Atomic JSON read/write
│   └── data/                  # signals.json, trades.json, etc.
├── scanner/
│   └── realtime_scanner.py    # asyncio scan loop (60s interval)
├── analytics/
│   └── reporter.py            # Win rate, outcomes, metrics report
└── backtest/
    └── backtester.py          # Historical replay (same pipeline)
```

---

## Installation

### 1. Requirements

- Python 3.9+
- MetaTrader5 terminal installed and running (Windows only for MT5 library)
- A Telegram bot token ([BotFather](https://t.me/BotFather))

### 2. Install dependencies

```bash
pip install MetaTrader5 pandas numpy requests python-dotenv openpyxl
```

Optional (for cleaner ISO datetime parsing in news filter):

```bash
pip install python-dateutil
```

### 3. Configure `.env`

```env
BOT_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id

# Optional — if MT5 terminal is not pre-logged-in
MT5_LOGIN=123456
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Server
```

### 4. Configure `config.py`

Key settings to check:

```python
# Broker symbol names — adjust suffix for your broker
MT5_SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",     # some brokers use "XAUUSDm" or "XAUUSD."
    "EURUSD": "EURUSD",
    ...
}
```

---

## Usage

### Run live scanner (default)

```bash
python main.py
```

The bot scans every 60 seconds. Signals are sent to Telegram and saved to `storage/data/signals.json`.

### Run backtest (180 days default)

```bash
python main.py --backtest
python main.py --backtest 90
```

Results saved to `storage/data/backtest_results.json`.

### Print performance report

```bash
python main.py --report
```

---

## Telegram Signal Format

```text
🟢 BUY EURUSD  |  Confidence: 80%
━━━━━━━━━━━━━━━━━━━━
📍 Entry  : 1.08450  (limit order — wait for retrace)
🛑 SL     : 1.08200  (below PDL sweep low)
🎯 TP1    : 1.08950  — RR 2.0R
🎯 TP2    : 1.09350  — RR 3.6R
━━━━━━━━━━━━━━━━━━━━
📊 Setup  : Sweep:PDL + MSS + FVG + Wyckoff:Spring
💧 Swept  : PDL @ 1.08220
📈 Bias   : H4 Bullish | H1 > EMA200
⏰ Session: London  |  09:15 UTC
🔄 Wyckoff: Spring on H4
━━━━━━━━━━━━━━━━━━━━
📉 Win Rate (30d): 58%  (14W / 10L)
🕐 23/04 09:15 UTC
⚠️ Signal only — no auto-execution. Manage your own risk.
```

---

## Signal JSON Schema

Each entry in `storage/data/signals.json`:

```json
{
  "id": "a3f8c2d1e4b7",
  "symbol": "EURUSD",
  "direction": "BUY",
  "entry": 1.08450,
  "sl": 1.08200,
  "tp1": 1.08950,
  "tp2": 1.09350,
  "rr": 2.00,
  "rr_tp2": 3.60,
  "confidence": 80,
  "setup_components": ["Sweep:PDL", "MSS", "FVG", "Wyckoff:Spring"],
  "session": "London",
  "bias_h4": "bullish",
  "bias_h1_ema": "above",
  "wyckoff_pattern": "spring",
  "swept_level_type": "PDL",
  "swept_level_price": 1.08220,
  "fvg_top": 1.08500,
  "fvg_bottom": 1.08400,
  "fvg_midpoint": 1.08450,
  "atr_m15": 0.00085,
  "timestamp": "2026-04-23T09:15:00Z",
  "status": "open",
  "outcome_price": null,
  "outcome_time": null,
  "pnl_r": null
}
```

Status lifecycle: `open` → `tp1` | `tp2` | `loss` | `expired`

---

## Confidence Scoring

| Component | Bonus |
| --- | --- |
| Base (all hard gates passed) | 50 |
| H4 + H1 bias aligned | +10 |
| Wyckoff spring / upthrust | +15 |
| Wyckoff accumulation / distribution | +10 |
| MSS confirmed | +10 |
| Displacement candle | +5 |
| FVG present | +10 |
| **Maximum** | **95** |

Signals below 65% confidence show a `⚡ Low confidence — observe only` warning.

---

## Tuning Signal Frequency

**Too many signals (>20/week):**

- Increase `MIN_FVG_ATR_RATIO` (e.g. 0.3 → 0.5)
- Require both MSS AND displacement in `signal_engine.py` Gate 7

**Too few signals (<10/week):**

- Lower `EQUAL_HL_MIN_TOUCHES` from 2 to 1
- Widen `EQUAL_HL_TOLERANCE_PCT` from 0.0003 to 0.0005

---

## Deployment

### Windows (Task Scheduler)

1. Create a `.bat` file:

```bat
@echo off
cd /d "d:\My Document\My_SOURCE\botforex_ntp"
python main.py >> bot.log 2>&1
```

1. Schedule via Task Scheduler to run at system startup.

### VPS / Linux

```bash
# Install on Ubuntu
pip3 install MetaTrader5 pandas numpy requests python-dotenv openpyxl

# Run with screen
screen -S forex_bot
python3 main.py
# Ctrl+A, D to detach

# Or with nohup
nohup python3 main.py > bot.log 2>&1 &
```

Note: MT5 Python library only works natively on Windows. For Linux VPS, run MT5 terminal under Wine or use a Windows VM.

---

## Disclaimer

This bot generates trading signals for informational purposes only. It does **not** place trades automatically. All trading decisions are the sole responsibility of the user. Past performance does not guarantee future results. Forex and gold trading involves significant risk of loss.
