# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ICT Forex Signal Bot — an automated trading signal generator that analyzes forex/gold market structure using the ICT (Inner Circle Trader) Top-Down methodology and delivers signals via Telegram. Targets XAU/USD, EUR/USD, GBP/USD, USD/JPY by default.

## Running the Bot

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # fill in credentials
python main.py
```

Required `.env` variables (validated at startup by `config.py`):
- `OANDA_ACCESS_TOKEN`, `OANDA_ACCOUNT_ID` — OANDA practice account credentials
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram bot credentials

No build step, no test suite, no linter configuration exists in this project.

## Architecture

The bot runs an infinite loop (`main.py`) that scans all symbols every `LOOP_INTERVAL` seconds (default 60s). Each iteration follows a strict pipeline:

```
oanda_client.py  →  ict_engine.py  →  signal_scorer.py  →  telegram_bot.py
   (fetch)            (analyze)          (gate/persist)        (deliver)
```

**`ict_engine.py`** is the core — it implements a 4-step filter where ALL conditions must pass to emit a signal:

1. **Kill Zone** — current UTC hour must be in London Open (02–05) or New York Open (07–10)
2. **H4 Bias** — last 10 candle pairs on H4 must show a clear HH/HL (bullish) or LH/LL (bearish) structure
3. **M15 Setup** — must find both a liquidity sweep (wick past 20-bar reference then close back inside) AND either a Fair Value Gap or an Order Block in the same direction as the bias
4. **M5 Confirmation** — the latest M5 candle must be the correct direction with body > 50% of ATR(14)

**`signal_scorer.py`** persists signals to `signals_history.json` and gates delivery: if ≥10 closed trades exist in the last 30 days, the win rate must be ≥50% to send.

**`config.py`** is the single source of truth for all tunable constants (`SYMBOLS`, `KILL_ZONES`, `LOOP_INTERVAL`, `OANDA_ENVIRONMENT`).

## Key Design Decisions

- **Per-symbol error isolation**: exceptions inside the symbol loop are caught individually so one failing symbol never crashes the bot.
- **Anti-spam**: `last_signals` dict in `main.py` tracks the most recent signal per symbol to suppress immediate re-sends.
- **No database**: signal history uses a plain JSON file (`signals_history.json`) excluded from git.
- **ATR-based SL/TP**: SL = sweep point ± ATR×0.5; TP1 = nearest swing; TP2 = FVG boundary or OB level.
- **XAU_USD rounding**: gold prices round to 2 decimal places; all other pairs to 5.
- **Hardcoded hyperparameters** live inside `ict_engine.py`: ATR period (14), sweep lookback (20 bars), FVG lookback (50 bars), OB lookback (100 bars), momentum body threshold (0.5×ATR).
