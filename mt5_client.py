# mt5_client.py — Kết nối MetaTrader 5 và lấy dữ liệu nến

import pandas as pd
import MetaTrader5 as mt5

from config import MT5_SYMBOLS


TIMEFRAME_MAP = {
    "D1":  mt5.TIMEFRAME_D1,
    "H4":  mt5.TIMEFRAME_H4,
    "M15": mt5.TIMEFRAME_M15,
    "M5":  mt5.TIMEFRAME_M5,
    "M1":  mt5.TIMEFRAME_M1,
}


def initialize():
    """Khởi tạo kết nối MT5. Gọi một lần khi bot start."""
    if not mt5.initialize():
        raise RuntimeError(f"Không thể kết nối MetaTrader 5: {mt5.last_error()}")


def shutdown():
    """Đóng kết nối MT5. Gọi khi bot tắt."""
    mt5.shutdown()


def get_candles(symbol: str, granularity: str, count: int = 100) -> pd.DataFrame:
    """
    Lấy dữ liệu nến đã đóng từ MT5.

    Tham số:
        symbol      : Ký hiệu theo định dạng bot (vd: "XAU_USD", "EUR_USD")
        granularity : Khung thời gian ("H4", "M15", "M5", "M1")
        count       : Số lượng nến đã đóng cần lấy

    Trả về:
        DataFrame với các cột: time, open, high, low, close, volume
    """
    mt5_symbol = MT5_SYMBOLS.get(symbol, symbol)
    tf = TIMEFRAME_MAP.get(granularity)
    if tf is None:
        raise ValueError(f"Granularity không hợp lệ: {granularity}")

    # Đảm bảo symbol có trong Market Watch
    mt5.symbol_select(mt5_symbol, True)

    # Lấy count+1 để sau đó bỏ nến cuối (đang hình thành)
    rates = mt5.copy_rates_from_pos(mt5_symbol, tf, 0, count + 1)

    if rates is None or len(rates) == 0:
        error = mt5.last_error()
        raise ValueError(
            f"Không lấy được dữ liệu MT5: {mt5_symbol} ({granularity}) — {error}"
        )

    df = pd.DataFrame(rates)

    # Bỏ nến cuối cùng (nến chưa đóng, đang hình thành)
    df = df.iloc[:-1].copy()

    # Chuẩn hóa tên cột và kiểu dữ liệu
    df = df.rename(columns={"tick_volume": "volume"})
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)

    if df.empty:
        raise ValueError(f"Không có nến đã đóng cho {mt5_symbol} ({granularity})")

    return df
