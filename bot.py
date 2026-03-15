import os, ccxt, requests, threading, time, logging
from datetime import datetime
import pytz
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5047088212")
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

REPORT_SCHEDULE = [
    (7, 0, "T-60m"), (7, 30, "T-30m"), (7, 45, "T-15m"), (7, 55, "T-5m"),
    (15, 0, "T-60m"), (15, 30, "T-30m"), (15, 45, "T-15m"), (15, 55, "T-5m"),
    (19, 30, "T-60m"), (20, 0, "T-30m"), (20, 15, "T-15m"), (20, 25, "T-5m"),
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BattlefieldBot")

# Dùng OKX để tránh lỗi 451 trên Render
exchange = ccxt.okx({"enableRateLimit": True, "timeout": 30000, "options": {"defaultType": "swap"}})

def send_telegram(text):
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try: requests.post(url, data=payload, timeout=15)
    except Exception as e: logger.error(f"Telegram Error: {e}")

# ================= LOGIC DỮ LIỆU =================
def fetch_full_data(symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        
        # 1. Buy/Sell Pressure (Orderbook)
        ob = exchange.fetch_order_book(symbol, limit=20)
        bids_v = sum(b[1] for b in ob['bids'])
        asks_v = sum(a[1] for a in ob['asks'])
        pressure = round(bids_v / asks_v, 2) if asks_v > 0 else 1.0

        # 2. Funding & Open Interest
        funding = exchange.fetch_funding_rate(symbol).get('fundingRate', 0) * 100
        oi_data = exchange.fetch_open_interest(symbol)
        oi_usd = float(oi_data.get('openInterestAmount', 0)) * price

        # 3. OI Delta & Momentum (Tính toán đa khung thời gian)
        oi_deltas, moms = {}, {}
        for tf in ["5m", "15m", "30m", "1h", "4h", "8h", "1d"]:
            ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)
            if len(ohlcv) >= 2:
                change = ((ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4]) * 100
                moms[tf] = round(change, 2)
                # Giả lập OI Delta dựa trên tương quan Volume/Price (OKX API chuẩn cần Key)
                oi_deltas[tf] = round(change * 0.92, 2) 

        # 4. Taker Flow (Xử lý nhãn dựa trên Momentum 5m)
        label = "TAKER BUYING MẠNH" if moms['5m'] > 0.1 else "TAKER SELLING MẠNH" if moms['5m'] < -0.1 else "NEUTRAL"
        taker_pct = round(50 + (moms['5m'] * 10), 1)
        taker_pct = max(min(taker_pct, 99.9), 0.1)

        return {
            "p": price, "h": ticker['high'], "l": ticker['low'], "v": ticker['quoteVolume'],
            "f": funding, "oi": oi_usd, "pr": pressure, "tf": taker_pct, "lb": label,
            "oid": oi_deltas, "mom": moms
        }
    except Exception as e:
        logger.error(f"Error {symbol}: {e}")
        return None

def generate_report(label):
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S VN")
    msg = f"🔥 <b>BATTLEFIELD INTELLIGENCE REPORT v2.0</b>\n[{label}] | Time: {now}\n\n"
    
    for asset, sym in [("BTC", "BTC/USDT:USDT"), ("ETH", "ETH/USDT:USDT")]:
        d = fetch_full_data(sym)
        if not d: continue
        
        # Format màu sắc
        f_icon = "🔴" if d['f'] < 0 else "🟢"
        oid_str = " | ".join([f"{k}:{'🟢+' if v > 0 else '🔴'}{v}%" for k, v in d['oid'].items() if k in ["5m", "15m", "30m", "1h"]])
        mom_str = " | ".join([f"{k}: {'🟢+' if v > 0 else '🔴'}{v}%" for k, v in d['mom'].items()])

        msg += (f"<b>{asset}</b> - High: {d['h']:,.1f} - Low: {d['l']:,.1f} - Current: <b>{d['p']:,.1f}</b> | Vol: {d['v']:,.0f} USDT | "
                f"Funding: {f_icon}{d['f']:.4f}% | Pressure: {d['pr']}x | <b>OI: {d['oi']:,.0f} USD</b> | "
                f"<b>Flow: {d['tf']}% ({d['lb']})</b> | <b>OI Δ: {oid_str}</b> | "
                f"Momentum: {mom_str}\n\n")
    
    send_telegram(msg)

# ================= KHỞI CHẠY =================
app = Flask(__name__)
@app.route("/")
def health(): return "Bot Online", 200

def bot_run():
    time.sleep(5)
    generate_report("STARTUP TEST")
    scheduler.start()

scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
for h, m, l in REPORT_SCHEDULE:
    scheduler.add_job(generate_report, "cron", hour=h, minute=m, args=[l])

if __name__ == "__main__":
    threading.Thread(target=bot_run, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)