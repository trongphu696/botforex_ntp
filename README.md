# ICT Forex Signal Bot

Bot giao dịch Forex/Vàng tự động theo phương pháp **ICT (Inner Circle Trader)**, phân tích Top-Down H4 → M15 → M5, gửi tín hiệu qua Telegram.

---

## Tính năng

- Phân tích **Top-Down 3 khung thời gian**: H4 (bias) → M15 (setup) → M5 (confirm)
- Chỉ giao dịch trong **Kill Zone** có thanh khoản cao (London / New York Open)
- Phát hiện **Liquidity Sweep**, **Fair Value Gap (FVG)**, **Order Block (OB)**
- Tính **SL/TP** tự động dựa trên ATR và cấu trúc giá
- **Win rate tracker**: lưu lịch sử, tự động tạm dừng nếu win rate < 50%
- Gửi tín hiệu qua **Telegram** với format HTML đẹp, đầy đủ thông tin
- Chống spam: mỗi cặp chỉ gửi khi tín hiệu thay đổi

---

## Cấu trúc project

```
Forex/
├── .env                    ← Thông tin xác thực (không commit lên git)
├── requirements.txt        ← Danh sách thư viện
├── config.py               ← Load biến môi trường, cấu hình chung
├── oanda_client.py         ← Kết nối OANDA API, lấy dữ liệu nến
├── ict_engine.py           ← Toàn bộ logic ICT
├── signal_scorer.py        ← Lưu lịch sử, tính win rate
├── telegram_bot.py         ← Format và gửi tín hiệu Telegram
├── main.py                 ← Vòng lặp chính
└── signals_history.json    ← Tự tạo khi bot chạy
```

---

## Cài đặt

### Yêu cầu
- Python 3.10+
- Tài khoản OANDA Practice
- Telegram Bot

### 1. Cài Python

Tải tại [python.org/downloads](https://www.python.org/downloads/), chọn Python 3.11 hoặc 3.12.

> **Quan trọng:** Tick vào **"Add Python to PATH"** khi cài đặt.

Kiểm tra:
```cmd
python --version
pip --version
```

### 2. Tạo Virtual Environment

```cmd
cd d:\Learning\Forex
python -m venv .venv
.venv\Scripts\activate
```

Dấu nhắc lệnh đổi thành `(.venv)` là thành công.

### 3. Cài dependencies

```cmd
pip install -r requirements.txt
```

---

## Cấu hình

### Lấy OANDA API Token

1. Đăng ký tại [oanda.com](https://www.oanda.com) → chọn **Practice Account**
2. Đăng nhập vào **fxTrade Practice** → **My Account → API Access**
3. Tạo API Token → copy lại
4. Account ID là dãy số hiển thị trên dashboard (dạng `001-001-xxxxxxx-001`)

### Lấy Telegram Bot Token & Chat ID

**Tạo bot:**
1. Mở Telegram → tìm **@BotFather** → gõ `/newbot`
2. Đặt tên → BotFather trả về token dạng `123456789:AAF...`

**Lấy Chat ID:**
1. Gửi một tin nhắn bất kỳ cho bot vừa tạo
2. Truy cập URL sau trên trình duyệt (thay `YOUR_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. Tìm `"chat": {"id": 123456789}` — đó là Chat ID

### Điền file `.env`

```env
OANDA_API_TOKEN=abc123xyz...
OANDA_ACCOUNT_ID=001-001-1234567-001
BOT_TOKEN=123456789:AAFabc...
CHAT_ID=987654321
```

---

## Chạy bot

```cmd
cd d:\Learning\Forex
.venv\Scripts\activate
python main.py
```

Dừng bot: `Ctrl + C`

---

## Logic ICT

Bot yêu cầu **đồng thời đủ 4 điều kiện** mới phát tín hiệu:

```
Bước 1 [UTC Now] Kill Zone?
          │ Không → Bỏ qua
          ↓ Có
Bước 2   [H4] Market Structure → Bullish / Bearish?
          │ Neutral → Bỏ qua
          ↓
Bước 3   [M15] Liquidity Sweep cùng chiều bias?
          │ Không → Bỏ qua
          ↓ Có
          [M15] FVG hoặc Order Block còn open?
          │ Không → Bỏ qua
          ↓ Có
Bước 4   [M5] Nến đảo chiều có momentum (thân > 50% ATR)?
          │ Không → Bỏ qua
          ↓ Có
         PHÁT TÍN HIỆU
```

### Kill Zone (giờ UTC)

| Session | Giờ UTC | Lý do |
|---------|---------|-------|
| London Open | 02:00 – 05:00 | Thanh khoản châu Âu mở |
| New York Open | 07:00 – 10:00 | Thanh khoản Mỹ mở, overlap London |

### SL / TP

| Lệnh | SL | TP1 (50%) | TP2 (50%) |
|------|----|-----------|-----------|
| BUY | Đáy sweep − ATR×0.5 | Swing high M15 gần nhất | FVG top hoặc OB high |
| SELL | Đỉnh sweep + ATR×0.5 | Swing low M15 gần nhất | FVG bottom hoặc OB low |

Làm tròn giá: **XAU_USD** → 2 chữ số thập phân, các cặp khác → 5 chữ số.

---

## Ví dụ tin nhắn Telegram

```
🟢 BUY XAU/USD | ICT Setup
━━━━━━━━━━━━━━━━━━
📍 Entry  : 2312.45
🛑 SL     : 2298.20
🎯 TP1    : 2325.00  (50%)
🎯 TP2    : 2338.50  (50%)
━━━━━━━━━━━━━━━━━━
📊 Setup  : Liquidity Sweep + FVG
⏰ Zone   : London Open
📈 H4 Bias: Bullish
📉 Win Rate (30d): 63% (17W/10L)
🕐 14/04 09:15 UTC
━━━━━━━━━━━━━━━━━━
⚠️ Chỉ mang tính tham khảo
```

---

## Win Rate Tracker

| Trạng thái | Hành động |
|------------|-----------|
| < 10 lệnh đã đóng | Gửi bình thường (chưa đủ mẫu) |
| Win rate ≥ 50% | Gửi bình thường |
| Win rate < 50% | Tạm dừng gửi, log cảnh báo |

Dữ liệu lưu tại `signals_history.json`. Kết quả win/loss được cập nhật tự động mỗi vòng lặp dựa trên giá hiện tại so với SL/TP1.

---

## Log console

```
[2026-04-14 08:00:00] ============================================================
[2026-04-14 08:00:00]   ICT Forex Signal Bot khởi động
[2026-04-14 08:00:00]   Symbols  : XAU_USD, EUR_USD, GBP_USD, USD_JPY
[2026-04-14 08:00:00]   Interval : 60s
[2026-04-14 08:00:00] --- Bắt đầu vòng quét ---
[2026-04-14 08:00:01]   [XAU_USD] Đang lấy dữ liệu nến...
[2026-04-14 08:00:02]   [XAU_USD] Đang phân tích ICT (H4→M15→M5)...
[2026-04-14 08:00:02]   [XAU_USD] Không có tín hiệu (không đủ điều kiện ICT)
[2026-04-14 08:00:03]   [EUR_USD] Đang lấy dữ liệu nến...
...
[2026-04-14 08:00:10] --- Vòng quét hoàn thành. Chờ 60s ---
```

---

## Cấu hình thêm

Chỉnh trong [config.py](config.py):

```python
SYMBOLS       = ["XAU_USD", "EUR_USD", "GBP_USD", "USD_JPY"]  # Thêm/bớt cặp tiền
LOOP_INTERVAL = 60   # Chu kỳ quét (giây)
KILL_ZONES    = {
    "London Open":   (2, 5),   # Thay đổi giờ Kill Zone
    "New York Open": (7, 10),
}
```

---

## Lưu ý

> Bot này chỉ mang tính **giáo dục và tham khảo**. Không phải khuyến nghị đầu tư. Giao dịch Forex có rủi ro mất vốn cao.

---

## Thư viện sử dụng

| Thư viện | Mục đích |
|----------|----------|
| `oandapyV20` | Kết nối OANDA REST API |
| `pandas` | Xử lý dữ liệu nến, tính indicator |
| `python-dotenv` | Load biến môi trường từ `.env` |
| `requests` | Gọi Telegram Bot API |
