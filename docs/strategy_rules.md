# Strategy Rules

## Symbols
- XAUUSD
- EURUSD
- GBPUSD
- USDJPY
- USDCHF

---

## Timeframes

HTF:
- H4
- H1

LTF:
- M5
- M1

---

## Trend Filter

Bullish:
- H4 HH/HL
- Price above H1 EMA200

Bearish:
- H4 LH/LL
- Price below H1 EMA200

---

## Liquidity

Detect:
- Previous day high
- Previous day low
- Asia high
- Asia low
- Equal highs
- Equal lows

---

## Sweep

BUY:
- sweep low
- close above liquidity

SELL:
- sweep high
- close below liquidity

---

## MSS

BUY:
- break previous swing high

SELL:
- break previous swing low

---

## FVG

Bullish:
candle1.high < candle3.low

Bearish:
candle1.low > candle3.high

Entry:
50% retracement

---

## Session

XAUUSD:
London + NY

GBPUSD:
London

EURUSD:
London + NY

USDJPY:
Asia + NY

USDCHF:
London + NY

---

## News filter

Block:
- CPI
- NFP
- FOMC
- ECB
- BOE

30 mins before
15 mins after

---

## Risk

RR >= 1:2