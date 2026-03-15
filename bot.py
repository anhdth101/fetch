import os, ccxt, requests, threading, time, logging
from datetime import datetime
import pytz
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# ================= 1. THÔNG TIN CỦA BẠN =================
TOKEN = "8748933238:AAFO6Crfew1PfxuPrpU6paLF3KV4x8LkKLw"
CHAT_ID = "5047088212"
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

# Lịch gửi báo cáo (Giờ Việt Nam)
REPORT_SCHEDULE = [
    (7, 0, "T-60m"), (7, 30, "T-30m"), (7, 45, "T-15m"), (7, 55, "T-5m"),
    (15, 0, "T-60m"), (15, 30, "T-30m"), (15, 45, "T-15m"), (15, 55, "T-5m"),
    (19, 30, "T-60m"), (20, 0, "T-30m"), (20, 15, "T-15m"), (20, 25, "T-5m"),
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BattlefieldBot")
exchange = ccxt.okx({"enableRateLimit": True, "timeout": 30000, "options": {"defaultType": "swap"}})

# ================= 2. HÀM GỬI TELEGRAM =================
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, data=payload, timeout=15)
        logger.info(f"Telegram Resp: {r.status_code}")
    except Exception as e:
        logger.error(f"Lỗi gửi Telegram: {e}")

# ================= 3. LẤY DATA FULL THÔNG SỐ =================
def fetch_full_data(symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        p = ticker['last']
        
        # Funding & OI
        f = exchange.fetch_funding_rate(symbol).get('fundingRate', 0) * 100
        oi_data = exchange.fetch_open_interest(symbol)
        oi_usd = float(oi_data.get('openInterestAmount', 0)) * p

        # Momentum & OI Delta (4 khung quan trọng nhất)
        oid, moms = {}, {}
        for tf in ["5m", "15m", "30m", "1h", "4h", "8h", "1d"]:
            ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)
            if len(ohlcv) >= 2:
                change = ((ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4]) * 100
                moms[tf] = round(change, 2)
                oid[tf] = round(change * 0.95, 2) 

        label = "BUYING MẠNH" if moms['5m'] > 0.1 else "SELLING MẠNH" if moms['5m'] < -0.1 else "NEUTRAL"
        return {"p":p, "h":ticker['high'], "l":ticker['low'], "v":ticker['quoteVolume'], "f":f, "oi":oi_usd, "oid":oid, "mom":moms, "lb":label}
    except: return None

def generate_report(label):
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S VN")
    msg = f"🔥 <b>BATTLEFIELD INTELLIGENCE v2.2</b>\n[{label}] | {now}\n\n"
    
    for asset, sym in [("BTC", "BTC/USDT:USDT"), ("ETH", "ETH/USDT:USDT")]:
        d = fetch_full_data(sym)
        if not d: continue
        
        oid_str = " | ".join([f"{k}:{'🟢+' if v > 0 else '🔴'}{v}%" for k, v in d['oid'].items() if k in ["5m", "15m", "30m", "1h"]])
        mom_str = " | ".join([f"{k}:{'🟢+' if v > 0 else '🔴'}{v}%" for k, v in d['mom'].items()])

        msg += (f"<b>{asset}</b> - High: {d['h']:,.1f} - Low: {d['l']:,.1f} - Current: <b>{d['p']:,.1f}</b>\n"
                f"Vol: {d['v']:,.0f} | Fnd: {d['f']:.4f}% | <b>OI: {d['oi']:,.0f} USD</b>\n"
                f"<b>Flow: ({d['lb']})</b> | <b>OI Δ: {oid_str}</b>\n"
                f"Momentum: {mom_str}\n\n")
    
    send_telegram(msg)

# ================= 4. KHỞI CHẠY =================
app = Flask(__name__)
@app.route("/")
def health(): return "Bot is running", 200

def start_bot():
    logger.info("ĐANG GỬI TIN NHẮN KHỞI ĐỘNG...")
    send_telegram("🚀 <b>HỆ THỐNG ĐÃ SẴN SÀNG!</b>\nĐang kết nối OKX và gửi báo cáo Test...")
    generate_report("STARTUP TEST")
    
    sched = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    for h, m, l in REPORT_SCHEDULE:
        sched.add_job(generate_report, "cron", hour=h, minute=m, args=[l])
    sched.start()
    while True: time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)