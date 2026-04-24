from dataclasses import dataclass, field
from typing import List, Literal, Optional


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: Literal["high", "low"]
    timestamp: str  # ISO UTC string


@dataclass
class LiquidityLevel:
    price: float
    kind: Literal["PDH", "PDL", "AsiaHigh", "AsiaLow", "EqualHigh", "EqualLow"]
    timestamp: str
    touch_count: int = 1


@dataclass
class FVG:
    top: float
    bottom: float
    midpoint: float
    kind: Literal["bullish", "bearish"]
    candle_index: int


@dataclass
class SweepEvent:
    swept_level: LiquidityLevel
    sweep_candle_index: int
    sweep_low: float    # actual wick extreme (long SL reference)
    sweep_high: float   # actual wick extreme (short SL reference)
    kind: Literal["bullish", "bearish"]


@dataclass
class ConfirmationEvent:
    kind: Literal["MSS", "BOS", "displacement"]
    candle_index: int
    broke_level: float


@dataclass
class Signal:
    id: str
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry: float
    sl: float
    tp1: float
    tp2: float
    rr: float
    rr_tp2: float
    confidence_score: int
    setup_tags: List[str]
    session: str
    bias_h4: str
    bias_h1_ema: str
    swept_level_type: str
    swept_level_price: float
    fvg_top: float
    fvg_bottom: float
    fvg_midpoint: float
    atr_m5: float
    timestamp: str
    status: Literal["open", "tp1", "tp2", "loss", "expired"] = "open"
    outcome_price: Optional[float] = None
    outcome_time: Optional[str] = None
    pnl_r: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": self.entry,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "rr": round(self.rr, 2),
            "rr_tp2": round(self.rr_tp2, 2),
            "confidence_score": self.confidence_score,
            "setup_tags": self.setup_tags,
            "session": self.session,
            "bias_h4": self.bias_h4,
            "bias_h1_ema": self.bias_h1_ema,
            "swept_level_type": self.swept_level_type,
            "swept_level_price": self.swept_level_price,
            "fvg_top": self.fvg_top,
            "fvg_bottom": self.fvg_bottom,
            "fvg_midpoint": self.fvg_midpoint,
            "atr_m5": round(self.atr_m5, 6),
            "timestamp": self.timestamp,
            "status": self.status,
            "outcome_price": self.outcome_price,
            "outcome_time": self.outcome_time,
            "pnl_r": self.pnl_r,
        }
