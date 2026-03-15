import os, ccxt, requests, threading, time, logging
from datetime import datetime
import pytz
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# ================= 1. BẢO MẬT (LẤY TỪ RENDER SETTINGS) =================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BattlefieldBot")

# Kiểm tra xem bạn đã điền biến trên Render chưa
if not TOKEN or not CHAT_ID:
    logger.error("!!! THIẾU BIẾN MÔI TRƯỜNG !!! Hãy vào Render Settings để điền.")

exchange = ccxt.okx({
    'enableRateLimit': True, 
    'timeout': 15000,
    'options': {'defaultType': 'swap'}
})

def send_telegram(text):
    if not TOKEN or not CHAT_ID: return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        return r.status_code == 200
    except: return False

# ================= 2. LOGIC FETCH DATA =================
def fetch_with_retry(symbol):
    data = {"p": 0, "oi": "N/A", "f": "N/A", "status": "Error"}
    for _ in range(3):
        try:
            ticker = exchange.fetch_ticker(symbol)
            data["p"] = ticker['last']
            data["status"] = "OK"
            break
        except: time.sleep(1)

    if data["status"] == "Error": return None

    try:
        f_rate = exchange.fetch_funding_rate(symbol)
        data["f"] = f"{f_rate.get('fundingRate', 0) * 100:.4f}%"
        oi_res = exchange.fetch_open_interest(symbol)
        oi_val = float(oi_res.get('openInterestAmount', 0)) * data["p"]
        data["oi"] = f"${oi_val:,.0f}"
    except: pass
    return data

def get_report(label="REPORT"):
    now = datetime.now(TIMEZONE).strftime("%H:%M:%S")
    msg = f"🔥 <b>BATTLEFIELD v2.6 (SECURE)</b>\n[{label}] | {now}\n\n"
    success = False
    for sym in SYMBOLS:
        d = fetch_with_retry(sym)
        if d:
            success = True
            name = sym.split('-')[0]
            msg += f"<b>{name}</b>: <b>{d['p']:,.1f}</b>\nOI: {d['oi']} | Fnd: {d['f']}\n\n"
    if success: send_telegram(msg)

# ================= 3. KHỞI CHẠY =================
app = Flask(__name__)
@app.route("/")
def health(): return "ONLINE", 200

def start_bot():
    time.sleep(5)
    send_telegram("🚀 <b>Hệ thống v2.6 đã bảo mật!</b>\nĐang quét dữ liệu sàn...")
    get_report("STARTUP TEST")
    
    sched = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    sched.add_job(get_report, 'interval', minutes=30)
    sched.start()
    while True: time.sleep(10)

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)