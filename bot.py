import os, ccxt, requests, threading, time, logging
from datetime import datetime
import pytz
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# ================= 1. CẤU HÌNH =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5047088212")
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

# Lịch gửi báo cáo
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
    if not TELEGRAM_TOKEN or "token" in TELEGRAM_TOKEN.lower():
        logger.error("Token chưa đúng! Kiểm tra Env Vars trên Render.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=15)
        logger.info(f"Telegram Resp: {r.status_code}")
    except Exception as e:
        logger.error(f"Lỗi gửi tin nhắn: {e}")

# ================= 3. LẤY DATA & GỬI BÁO CÁO =================
def fetch_and_report(label):
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    msg = f"🔥 <b>BATTLEFIELD v2.1</b>\n[{label}] | {now}\n\n"
    
    for sym in SYMBOLS:
        try:
            ticker = exchange.fetch_ticker(sym)
            p = ticker['last']
            oi_data = exchange.fetch_open_interest(sym)
            oi_usd = float(oi_data.get('openInterestAmount', 0)) * p
            
            # Momentum 5m
            ohlcv = exchange.fetch_ohlcv(sym, "5m", limit=2)
            mom5m = round(((ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4]) * 100, 2) if len(ohlcv) >=2 else 0
            icon = "🟢+" if mom5m > 0 else "🔴"

            msg += f"<b>{sym.split('/')[0]}</b>: {p:,.1f}\nOI: ${oi_usd:,.0f}\nΔ5m: {icon}{mom5m}%\n\n"
        except: continue
    
    send_telegram(msg)

# ================= 4. KHỞI CHẠY (BẮT BUỘC ĐÚNG FORM) =================
app = Flask(__name__)

@app.route("/")
def health(): return "ONLINE", 200

def run_scheduler():
    # Gửi tin nhắn TEST ngay lập tức khi vừa bật
    logger.info("BẮT ĐẦU GỬI TIN NHẮN STARTUP...")
    send_telegram("🚀 <b>BOT ĐÃ LIVE!</b>\nĐang chuẩn bị quét dữ liệu...")
    fetch_and_report("STARTUP TEST")
    
    # Chạy lịch trình
    sched = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    for h, m, l in REPORT_SCHEDULE:
        sched.add_job(fetch_and_report, "cron", hour=h, minute=m, args=[l])
    sched.start()
    while True: time.sleep(60) # Giữ thread này sống

if __name__ == "__main__":
    # Chạy logic bot trong thread riêng
    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()
    
    # Chạy Flask ở luồng chính (Main Thread)
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Khởi chạy Flask trên Port {port}")
    app.run(host="0.0.0.0", port=port)