# oanda_client.py — Kết nối OANDA API và lấy dữ liệu nến

import pandas as pd
import oandapyV20
import oandapyV20.endpoints.instruments as instruments

from config import OANDA_API_TOKEN, OANDA_ENVIRONMENT


# Khởi tạo client OANDA một lần duy nhất (dùng chung toàn bộ ứng dụng)
_client = oandapyV20.API(
    access_token=OANDA_API_TOKEN,
    environment=OANDA_ENVIRONMENT,
)


def get_candles(symbol: str, granularity: str, count: int = 100) -> pd.DataFrame:
    """
    Lấy dữ liệu nến từ OANDA API.

    Tham số:
        symbol      : Ký hiệu cặp tiền, ví dụ "XAU_USD", "EUR_USD"
        granularity : Khung thời gian, ví dụ "H4", "M15", "M5"
        count       : Số lượng nến cần lấy (bao gồm cả nến chưa đóng)

    Trả về:
        DataFrame với các cột: time, open, high, low, close, volume
        Chỉ bao gồm các nến đã đóng (complete = True)
    """
    # Tham số request tới OANDA
    params = {
        "price":       "M",           # Mid price (giá trung bình bid/ask)
        "granularity": granularity,
        "count":       count,
    }

    # Tạo endpoint và gọi API
    endpoint = instruments.InstrumentsCandles(instrument=symbol, params=params)
    _client.request(endpoint)
    response = endpoint.response

    # Chuyển đổi dữ liệu thô thành danh sách dict
    rows = []
    for candle in response.get("candles", []):
        # Chỉ lấy nến đã đóng hoàn toàn
        if not candle.get("complete", False):
            continue

        mid = candle["mid"]
        rows.append({
            "time":   candle["time"],
            "open":   float(mid["o"]),
            "high":   float(mid["h"]),
            "low":    float(mid["l"]),
            "close":  float(mid["c"]),
            "volume": int(candle.get("volume", 0)),
        })

    if not rows:
        raise ValueError(
            f"Không có nến đã đóng nào cho {symbol} ({granularity})"
        )

    # Tạo DataFrame, reset index để index liên tục từ 0
    df = pd.DataFrame(rows)
    df.reset_index(drop=True, inplace=True)
    return df
