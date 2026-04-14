# ict_engine.py — Toàn bộ logic phân tích ICT (Inner Circle Trader)
# Phân tích Top-Down: H4 (bias) → M15 (setup) → M5 (confirm entry)

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from config import KILL_ZONES


# ---------------------------------------------------------------------------
# Hàm tiện ích
# ---------------------------------------------------------------------------

def _round_price(value: float, symbol: str) -> float:
    """
    Làm tròn giá theo quy ước từng cặp tiền:
    - XAU_USD : 2 chữ số thập phân
    - Các cặp khác: 5 chữ số thập phân
    """
    decimals = 2 if symbol == "XAU_USD" else 5
    return round(value, decimals)


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Tính Average True Range (ATR) thủ công bằng pandas.

    True Range = max(
        high - low,
        |high - close_trước|,
        |low  - close_trước|
    )
    ATR = rolling mean của TR trong `period` kỳ.
    """
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean()


# ---------------------------------------------------------------------------
# 1. Kill Zone Filter
# ---------------------------------------------------------------------------

def is_kill_zone(dt_utc: datetime) -> tuple[bool, str]:
    """
    Kiểm tra thời điểm hiện tại có nằm trong Kill Zone không.

    Kill Zone là các khung giờ có thanh khoản cao:
    - London Open : 02:00 – 05:00 UTC
    - New York Open: 07:00 – 10:00 UTC

    Trả về:
        (True, tên_zone)  nếu đang trong Kill Zone
        (False, "")       nếu ngoài Kill Zone
    """
    hour = dt_utc.hour

    for zone_name, (start, end) in KILL_ZONES.items():
        if start <= hour < end:
            return True, zone_name

    return False, ""


# ---------------------------------------------------------------------------
# 2. Market Structure (H4) — xác định bias
# ---------------------------------------------------------------------------

def get_market_structure(df_h4: pd.DataFrame) -> str:
    """
    Xác định xu hướng thị trường dựa trên cấu trúc nến H4.

    Logic:
    - Bullish: đỉnh sau cao hơn đỉnh trước (HH) VÀ đáy sau cao hơn đáy trước (HL)
    - Bearish: đỉnh sau thấp hơn đỉnh trước (LH) VÀ đáy sau thấp hơn đáy trước (LL)
    - So sánh 10 cặp nến liên tiếp gần nhất, đếm số lần bullish/bearish

    Trả về: "bullish", "bearish", hoặc "neutral"
    """
    # Lấy 50 nến gần nhất để phân tích
    df = df_h4.tail(50).reset_index(drop=True)

    if len(df) < 3:
        return "neutral"

    bullish_count = 0
    bearish_count = 0

    # Duyệt 10 cặp nến cuối cùng
    lookback = min(10, len(df) - 1)
    for i in range(len(df) - lookback, len(df)):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]

        # Bullish: Higher High VÀ Higher Low
        is_hh = curr["high"] > prev["high"]
        is_hl = curr["low"]  > prev["low"]
        if is_hh and is_hl:
            bullish_count += 1

        # Bearish: Lower High VÀ Lower Low
        is_lh = curr["high"] < prev["high"]
        is_ll = curr["low"]  < prev["low"]
        if is_lh and is_ll:
            bearish_count += 1

    # Xác định bias: cần áp đảo rõ ràng (tỷ lệ 1.5x)
    if bullish_count > bearish_count * 1.5:
        return "bullish"
    elif bearish_count > bullish_count * 1.5:
        return "bearish"
    else:
        return "neutral"


# ---------------------------------------------------------------------------
# 3. Liquidity Sweep (M15)
# ---------------------------------------------------------------------------

def find_liquidity_sweep(df_m15: pd.DataFrame) -> Optional[dict]:
    """
    Phát hiện Liquidity Sweep trên M15 trong Kill Zone.

    Liquidity Sweep xảy ra khi giá "quét" qua vùng thanh khoản (đỉnh/đáy cũ)
    rồi đảo chiều đóng cửa lại bên trong — dấu hiệu market maker lấy thanh khoản.

    - Bullish sweep: wick đâm dưới đáy thấp nhất 20 nến trước, đóng cửa trở lại trên
    - Bearish sweep: wick đâm trên đỉnh cao nhất 20 nến trước, đóng cửa trở lại dưới

    Trả về dict với thông tin sweep, hoặc None nếu không tìm thấy.
    """
    # Cần ít nhất 22 nến để tính reference window
    if len(df_m15) < 22:
        return None

    # Duyệt từ nến thứ 21 trở đi để có đủ 20 nến tham chiếu
    for i in range(20, len(df_m15)):
        candle = df_m15.iloc[i]

        # Kiểm tra nến này có trong Kill Zone không
        try:
            candle_time = datetime.fromisoformat(
                candle["time"].replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            continue

        in_zone, zone_name = is_kill_zone(candle_time)
        if not in_zone:
            continue

        # Lấy 20 nến ngay trước đó làm reference
        ref = df_m15.iloc[i - 20 : i]
        recent_low  = ref["low"].min()
        recent_high = ref["high"].max()

        # Bullish sweep: wick xuống dưới đáy, đóng cửa lại trên đáy
        if candle["low"] < recent_low and candle["close"] > recent_low:
            return {
                "type":        "bullish",
                "sweep_low":   candle["low"],
                "sweep_high":  None,
                "candle_time": candle["time"],
                "zone":        zone_name,
            }

        # Bearish sweep: wick lên trên đỉnh, đóng cửa lại dưới đỉnh
        if candle["high"] > recent_high and candle["close"] < recent_high:
            return {
                "type":        "bearish",
                "sweep_low":   None,
                "sweep_high":  candle["high"],
                "candle_time": candle["time"],
                "zone":        zone_name,
            }

    return None


# ---------------------------------------------------------------------------
# 4. Fair Value Gap — FVG (M15)
# ---------------------------------------------------------------------------

def find_fvg(df_m15: pd.DataFrame, bias: str) -> Optional[dict]:
    """
    Phát hiện Fair Value Gap (vùng mất cân bằng giá) trên M15.

    FVG là khoảng trống giữa nến[i-1] và nến[i+1] — thường xảy ra khi
    có impulse move mạnh. Giá hay quay lại "lấp đầy" vùng này.

    - Bullish FVG: nến[i-1].high < nến[i+1].low  → gap tăng
    - Bearish FVG: nến[i-1].low  > nến[i+1].high → gap giảm

    Điều kiện hợp lệ:
    - Cùng chiều với H4 bias
    - Còn "open": giá hiện tại chưa lấp đầy gap

    Trả về FVG gần nhất thỏa điều kiện, hoặc None.
    """
    if len(df_m15) < 3:
        return None

    current_close = df_m15["close"].iloc[-1]

    # Duyệt 10 nến cuối (tính từ nến thứ 2 tới thứ -2)
    search_start = max(1, len(df_m15) - 11)
    search_end   = len(df_m15) - 1

    # Duyệt ngược để lấy FVG gần nhất trước
    for i in range(search_end - 1, search_start - 1, -1):
        prev_candle = df_m15.iloc[i - 1]
        next_candle = df_m15.iloc[i + 1]

        if bias == "bullish":
            # Bullish FVG: gap giữa high[i-1] và low[i+1]
            fvg_bottom = prev_candle["high"]
            fvg_top    = next_candle["low"]

            if fvg_bottom < fvg_top:
                # Kiểm tra còn open: giá chưa đi vào vùng gap
                if current_close > fvg_top:
                    # Giá đã vượt qua gap — chưa retest, còn open
                    return {
                        "type":   "bullish",
                        "top":    fvg_top,
                        "bottom": fvg_bottom,
                        "candle_time": df_m15.iloc[i]["time"],
                    }

        elif bias == "bearish":
            # Bearish FVG: gap giữa low[i-1] và high[i+1]
            fvg_top    = prev_candle["low"]
            fvg_bottom = next_candle["high"]

            if fvg_top > fvg_bottom:
                # Kiểm tra còn open: giá chưa lấp vào vùng gap
                if current_close < fvg_bottom:
                    return {
                        "type":   "bearish",
                        "top":    fvg_top,
                        "bottom": fvg_bottom,
                        "candle_time": df_m15.iloc[i]["time"],
                    }

    return None


# ---------------------------------------------------------------------------
# 5. Order Block — OB (M15)
# ---------------------------------------------------------------------------

def find_order_block(df_m15: pd.DataFrame, bias: str) -> Optional[dict]:
    """
    Phát hiện Order Block trên M15.

    Order Block là nến cuối cùng ngược chiều trước khi có impulse move mạnh
    — đây là vùng mà các tổ chức lớn đặt lệnh.

    - Bullish OB: nến đỏ cuối cùng trước 3 nến xanh liên tiếp
    - Bearish OB: nến xanh cuối cùng trước 3 nến đỏ liên tiếp

    Điều kiện hợp lệ:
    - Giá hiện tại đang test lại vùng OB (nằm trong [low, high] của nến OB)

    Trả về thông tin OB, hoặc None.
    """
    if len(df_m15) < 5:
        return None

    current_close = df_m15["close"].iloc[-1]

    # Duyệt 20 nến cuối
    search_start = max(0, len(df_m15) - 20)

    # Duyệt ngược để tìm OB gần nhất
    for i in range(len(df_m15) - 4, search_start - 1, -1):
        candle = df_m15.iloc[i]

        if bias == "bullish":
            # Bullish OB: nến đỏ (close < open)
            if candle["close"] >= candle["open"]:
                continue

            # Kiểm tra 3 nến xanh liên tiếp ngay sau
            next_three = df_m15.iloc[i + 1 : i + 4]
            if len(next_three) < 3:
                continue

            all_bullish = all(
                next_three.iloc[j]["close"] > next_three.iloc[j]["open"]
                for j in range(3)
            )
            if not all_bullish:
                continue

            # Kiểm tra giá hiện tại đang test vùng OB
            if candle["low"] <= current_close <= candle["high"]:
                return {
                    "type":        "bullish",
                    "ob_high":     candle["high"],
                    "ob_low":      candle["low"],
                    "candle_time": candle["time"],
                }

        elif bias == "bearish":
            # Bearish OB: nến xanh (close > open)
            if candle["close"] <= candle["open"]:
                continue

            # Kiểm tra 3 nến đỏ liên tiếp ngay sau
            next_three = df_m15.iloc[i + 1 : i + 4]
            if len(next_three) < 3:
                continue

            all_bearish = all(
                next_three.iloc[j]["close"] < next_three.iloc[j]["open"]
                for j in range(3)
            )
            if not all_bearish:
                continue

            # Kiểm tra giá hiện tại đang test vùng OB
            if candle["low"] <= current_close <= candle["high"]:
                return {
                    "type":        "bearish",
                    "ob_high":     candle["high"],
                    "ob_low":      candle["low"],
                    "candle_time": candle["time"],
                }

    return None


# ---------------------------------------------------------------------------
# 6. Entry Confirmation (M5)
# ---------------------------------------------------------------------------

def confirm_entry_m5(df_m5: pd.DataFrame, bias: str) -> bool:
    """
    Xác nhận entry trên khung M5 sau khi có setup trên M15.

    Điều kiện xác nhận:
    - Bullish: nến cuối xanh (close > open) VÀ thân nến > 50% ATR M5
    - Bearish: nến cuối đỏ (close < open) VÀ thân nến > 50% ATR M5

    Thân nến lớn hơn 50% ATR đảm bảo có momentum thực sự, không phải nhiễu.
    """
    if len(df_m5) < 15:
        return False

    atr_series = calc_atr(df_m5, period=14)
    atr_value  = atr_series.iloc[-1]

    if pd.isna(atr_value) or atr_value == 0:
        return False

    last_candle = df_m5.iloc[-1]
    body = abs(last_candle["close"] - last_candle["open"])

    if bias == "bullish":
        return (
            last_candle["close"] > last_candle["open"]
            and body > 0.5 * atr_value
        )
    elif bias == "bearish":
        return (
            last_candle["close"] < last_candle["open"]
            and body > 0.5 * atr_value
        )

    return False


# ---------------------------------------------------------------------------
# 7. Tính SL / TP
# ---------------------------------------------------------------------------

def calc_sl_tp(
    sweep: dict,
    fvg: Optional[dict],
    ob: Optional[dict],
    df_m15: pd.DataFrame,
    bias: str,
    symbol: str,
    entry: float,
) -> dict:
    """
    Tính Stop Loss và hai mức Take Profit theo ICT.

    BUY:
    - SL  = đáy Liquidity Sweep - ATR M15 * 0.5  (buffer dưới wick)
    - TP1 = swing high gần nhất trên M15           (đóng 50% vị thế)
    - TP2 = FVG top (nếu có FVG) hoặc OB high     (đóng 50% còn lại)

    SELL:
    - SL  = đỉnh Liquidity Sweep + ATR M15 * 0.5
    - TP1 = swing low gần nhất trên M15
    - TP2 = FVG bottom (nếu có FVG) hoặc OB low
    """
    atr_m15 = calc_atr(df_m15, period=14).iloc[-1]

    if bias == "bullish":
        sl = sweep["sweep_low"] - atr_m15 * 0.5

        # TP1: swing high gần nhất phía trên entry trong 10 nến cuối
        highs_above = df_m15["high"].tail(10)
        highs_above = highs_above[highs_above > entry]
        tp1 = highs_above.max() if not highs_above.empty else entry + atr_m15 * 2

        # TP2: ưu tiên FVG, sau đó OB
        if fvg is not None:
            tp2 = fvg["top"]
        elif ob is not None:
            tp2 = ob["ob_high"]
        else:
            tp2 = entry + atr_m15 * 3

        # Đảm bảo TP2 > TP1 > entry
        if tp2 <= tp1:
            tp2 = tp1 + atr_m15

    else:  # bearish
        sl = sweep["sweep_high"] + atr_m15 * 0.5

        # TP1: swing low gần nhất phía dưới entry trong 10 nến cuối
        lows_below = df_m15["low"].tail(10)
        lows_below = lows_below[lows_below < entry]
        tp1 = lows_below.min() if not lows_below.empty else entry - atr_m15 * 2

        # TP2: ưu tiên FVG, sau đó OB
        if fvg is not None:
            tp2 = fvg["bottom"]
        elif ob is not None:
            tp2 = ob["ob_low"]
        else:
            tp2 = entry - atr_m15 * 3

        # Đảm bảo TP2 < TP1 < entry
        if tp2 >= tp1:
            tp2 = tp1 - atr_m15

    return {
        "sl":  _round_price(sl,  symbol),
        "tp1": _round_price(tp1, symbol),
        "tp2": _round_price(tp2, symbol),
    }


# ---------------------------------------------------------------------------
# 8. Orchestrator chính
# ---------------------------------------------------------------------------

def analyze(
    symbol: str,
    df_h4:  pd.DataFrame,
    df_m15: pd.DataFrame,
    df_m5:  pd.DataFrame,
) -> Optional[dict]:
    """
    Phân tích Top-Down ICT và tổng hợp tín hiệu giao dịch.

    Quy trình 4 bước:
    1. Kiểm tra Kill Zone — chỉ giao dịch giờ có thanh khoản cao
    2. Xác định H4 bias — chỉ giao dịch theo xu hướng lớn
    3. Tìm setup M15 — Liquidity Sweep + FVG hoặc OB
    4. Xác nhận M5 — chờ nến đảo chiều có momentum

    Trả về dict tín hiệu đầy đủ nếu thỏa tất cả, hoặc None.
    """
    now_utc = datetime.now(tz=timezone.utc)

    # --- Bước 1: Kill Zone ---
    in_zone, zone_name = is_kill_zone(now_utc)
    if not in_zone:
        return None

    # --- Bước 2: H4 Market Structure ---
    bias = get_market_structure(df_h4)
    if bias == "neutral":
        return None

    # --- Bước 3a: Liquidity Sweep (M15) ---
    sweep = find_liquidity_sweep(df_m15)
    if sweep is None:
        return None

    # Sweep phải cùng chiều với bias
    if sweep["type"] != bias:
        return None

    # --- Bước 3b: FVG hoặc OB (M15) ---
    fvg = find_fvg(df_m15, bias)
    ob  = find_order_block(df_m15, bias)

    if fvg is None and ob is None:
        return None

    # --- Bước 4: Entry Confirmation (M5) ---
    confirmed = confirm_entry_m5(df_m5, bias)
    if not confirmed:
        return None

    # --- Tổng hợp tín hiệu ---
    entry = _round_price(df_m5["close"].iloc[-1], symbol)
    sltp  = calc_sl_tp(sweep, fvg, ob, df_m15, bias, symbol, entry)

    # Mô tả setup đã kích hoạt
    setup_parts = ["Liquidity Sweep"]
    if fvg is not None:
        setup_parts.append("FVG")
    if ob is not None:
        setup_parts.append("OB")
    setup_desc = " + ".join(setup_parts)

    return {
        "symbol":    symbol,
        "signal":    "BUY" if bias == "bullish" else "SELL",
        "entry":     entry,
        "sl":        sltp["sl"],
        "tp1":       sltp["tp1"],
        "tp2":       sltp["tp2"],
        "setup":     setup_desc,
        "zone":      zone_name,
        "bias":      bias.capitalize(),
        "timestamp": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
