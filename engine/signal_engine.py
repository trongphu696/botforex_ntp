"""
Signal Engine — orchestrates all core modules in a strict 13-step pipeline.
Returns (Signal, rejection_reason) where Signal is None on any gate failure.
This same pipeline is used identically by the live scanner and the backtester.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
import pandas as pd

import config
from core.models import Signal
from core import (
    market_structure,
    liquidity as liq_module,
    sweep as sweep_module,
    confirmation as conf_module,
    fvg as fvg_module,
    volatility,
    session,
    news as news_module,
    correlation,
    risk,
    scorer,
)
from core.indicators import get_atr_value


def analyze(
    symbol: str,
    df_d1:  pd.DataFrame,
    df_h4:  pd.DataFrame,
    df_h1:  pd.DataFrame,
    df_m5: pd.DataFrame,
    news_events: List[dict],
    active_signals: List[Signal],
    now_utc: datetime = None,
) -> Tuple[Optional[Signal], str]:
    """
    Full 13-step ICT analysis pipeline.
    Returns (Signal, "") on success or (None, rejection_reason) on failure.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    # Ensure UTC timezone aware
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    filters = {}

    # ── Gate 1: Session Filter ──────────────────────────────────────────────────
    valid_sess, session_name = session.is_valid_session(symbol, now_utc)
    if not valid_sess:
        return None, "outside_session"
    filters["session"] = session_name

    # ── Gate 2: News Blackout ──────────────────────────────────────────────────
    in_blackout, news_title = news_module.is_news_blackout(symbol, now_utc, news_events)
    if in_blackout:
        return None, f"news_blackout:{news_title}"

    # ── Gate 3: Correlation Filter ─────────────────────────────────────────────
    active = correlation.get_active_signals(active_signals, now_utc)
    corr_blocked, corr_reason = correlation.is_correlated_blocked(symbol, active)
    if corr_blocked:
        return None, corr_reason
    soft_corr_note = corr_reason if not corr_blocked and corr_reason else ""

    # ── Gate 4: Combined Trend Bias (H4 structure + H1 EMA200) ────────────────
    if len(df_h4) < 20 or len(df_h1) < config.EMA200_PERIOD + 5:
        return None, "insufficient_data"

    bias = market_structure.get_combined_bias(df_h4, df_h1)
    if bias == "neutral":
        return None, "h4_h1_bias_neutral"

    h4_bias  = market_structure.get_h4_bias(df_h4)
    h1e_bias = market_structure.get_h1_ema_bias(df_h1)
    h1_ema_aligned = True  # guaranteed by combined_bias gate

    # ── Gate 5: Volatility Filter ──────────────────────────────────────────────
    if len(df_m5) < config.ATR_PERIOD + 5:
        return None, "insufficient_m5_data"

    atr_m5 = get_atr_value(df_m5, config.ATR_PERIOD)
    if not volatility.passes_volatility_filter(symbol, atr_m5):
        return None, "atr_out_of_range"

    # ── Build Liquidity Map ────────────────────────────────────────────────────
    levels = liq_module.get_all_liquidity_levels(df_d1, df_h1, df_m5, now_utc)

    # ── Gate 6: Liquidity Sweep Detection ─────────────────────────────────────
    sweep_event = sweep_module.detect_sweep(df_m5, levels, bias)
    if sweep_event is None:
        return None, "no_sweep"

    # ── Gate 7: Confirmation — at least one of MSS / BOS / Displacement ───────
    mss_event  = conf_module.detect_mss(df_m5, sweep_event)
    bos_event  = conf_module.detect_bos(df_m5, bias)
    disp_event = conf_module.detect_displacement(df_m5, bias, atr_m5)

    if mss_event is None and bos_event is None and disp_event is None:
        return None, "no_confirmation"

    # ── Gate 8: FVG Entry ──────────────────────────────────────────────────────
    fvg_result = fvg_module.find_fvg(df_m5, bias, atr_m5)
    if fvg_result is None:
        return None, "no_fvg"

    entry = fvg_result.midpoint

    # ── Gate 9: Risk/RR Calculation ────────────────────────────────────────────
    sl  = risk.calculate_sl(sweep_event, atr_m5, bias, df_m5=df_m5, entry=entry)

    # SL must be on correct side
    if bias == "bullish" and sl >= entry:
        return None, "sl_invalid"
    if bias == "bearish" and sl <= entry:
        return None, "sl_invalid"

    # SL must meet minimum distance (avoids noise trades with tiny SL)
    sl_min = config.SL_MIN_DISTANCE.get(symbol, 0)
    if abs(entry - sl) < sl_min:
        return None, "sl_too_close"

    tp1 = risk.calculate_tp1(df_m5, bias, entry, atr_m5, levels)
    tp2 = risk.calculate_tp2(levels, bias, entry, tp1)

    rr_ok, rr_val = risk.check_min_rr(entry, sl, tp1)
    if not rr_ok:
        return None, f"rr_fail:{rr_val:.2f}"

    rr_tp2 = risk.calc_rr_tp2(entry, sl, tp2)

    # ── Confidence Score ───────────────────────────────────────────────────────
    confidence = scorer.compute_confidence(mss_event, bos_event, disp_event, fvg_result, h1_ema_aligned)
    if confidence < config.CONFIDENCE_MIN_SIGNAL:
        return None, f"low_confidence:{confidence}"

    # ── EqualHigh/EqualLow require MSS (stricter confirmation for noisy levels) ─
    if sweep_event.swept_level.kind in ("EqualHigh", "EqualLow") and mss_event is None:
        return None, "equal_hl_no_mss"

    # ── Build Setup Tag List ───────────────────────────────────────────────────
    setup_parts = [f"Sweep:{sweep_event.swept_level.kind}"]
    if mss_event:
        setup_parts.append("MSS")
    if bos_event:
        setup_parts.append("BOS")
    if disp_event:
        setup_parts.append("Displacement")
    setup_parts.append("FVG")
    if soft_corr_note:
        setup_parts.append("⚠️CorrNote")

    direction = "BUY" if bias == "bullish" else "SELL"

    signal = Signal(
        id=uuid.uuid4().hex[:12],
        symbol=symbol,
        direction=direction,
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        rr=rr_val,
        rr_tp2=rr_tp2,
        confidence_score=confidence,
        setup_tags=setup_parts,
        session=session_name,
        bias_h4=h4_bias,
        bias_h1_ema=h1e_bias,
        swept_level_type=sweep_event.swept_level.kind,
        swept_level_price=sweep_event.swept_level.price,
        fvg_top=fvg_result.top,
        fvg_bottom=fvg_result.bottom,
        fvg_midpoint=fvg_result.midpoint,
        atr_m5=atr_m5,
        timestamp=now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    return signal, ""
