import os, ccxt, requests, threading, time, logging
from datetime import datetime
import pytz
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# ================= CONFIG =================
TOKEN = "8748933238:AAFO6Crfew1PfxuPrpU6paLF3KV4x8LkKLw"
CHAT_ID = "5047088212"
# Đổi lại định dạng Symbol chuẩn nhất của OKX
SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

REPORT_SCHEDULE = [
    (7, 0, "T-60m"), (7, 30, "T-30m"), (7, 45, "T-15m"), (7, 55, "T-5m"),
    (15, 0, "T-60m"), (15, 30, "T-30m"), (15, 45, "T-15m"), (15, 55, "T-5m"),
    (19, 30, "T-60m"), (20, 0, "T-30m"), (20, 15, "T-15m"), (20, 25, "T-5m"),
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BattlefieldBot")

# Cấu hình OKX chuyên dụng
exchange = ccxt.okx({
    'enableRateLimit': True, 
    'timeout': 30000,
    'options': {'defaultType': 'swap'}
})

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, data=payload, timeout=15)
        logger.info(f"Telegram Resp: {r.status_code}")
    except Exception as e:
        logger.error(f"Lỗi gửi Telegram: {e}")

# ================= LOGIC DỮ LIỆU CẢI TIẾN =================
def fetch_full_data(symbol):
    try:
        # Lấy Ticker trước (Cơ bản nhất)
        ticker = exchange.fetch_ticker(symbol)
        p = ticker['last']
        
        # Thử lấy OI và Funding, nếu lỗi thì để mặc định 0
        try:
            f = exchange.fetch_funding_rate(symbol).get('fundingRate', 0) * 100
            oi_data = exchange.fetch_open_interest(symbol)
            oi_usd = float(oi_data.get('openInterestAmount', 0)) * p
        except:
            f, oi_usd = 0, 0

        # Lấy Momentum (Nếu lỗi khung nhỏ thì bỏ qua)
        moms = {}
        try:
            for tf in ["5m", "1h", "1d"]:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)
                if len(ohlcv) >= 2:
                    moms[tf] = round(((ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4]) * 100, 2)
        except:
            moms = {"5m": 0, "1h": 0, "1d": 0}

        label = "BUYING MẠNH" if moms.get('5m', 0) > 0.1 else "SELLING MẠNH" if moms.get('5m', 0) < -0.1 else "NEUTRAL"
        
        return {
            "p": p, "h": ticker.get('high', 0), "l": ticker.get('low', 0), 
            "v": ticker.get('quoteVolume', 0), "f": f, "oi": oi_usd, 
            "mom": moms, "lb": label
        }
    except Exception as e:
        logger.error(f"Lỗi fetch {symbol}: {e}")
        return None

def generate_report(label):
    now = datetime.now(TIMEZONE).strftime("%H:%M:%S VN")
    # Thay đổi tiêu đề để nhận diện bản mới
    msg = f"🔥 <b>BATTLEFIELD v2.3 (FIXED)</b>\n[{label}] | {now}\n\n"
    
    has_data = False
    for sym in SYMBOLS:
        d = fetch_full_data(sym)
        if d:
            has_data = True
            name = sym.split('-')[0]
            mom_str = " | ".join([f"{k}:{'🟢+' if v > 0 else '🔴'}{v}%" for k, v in d['mom'].items()])
            
            msg += (f"<b>{name}</b> - Current: <b>{d['p']:,.1f}</b>\n"
                    f"Vol: {d['v']:,.0f} | Fnd: {d['f']:.4f}% | <b>OI: {d['oi']:,.0f} USD</b>\n"
                    f"<b>Flow: ({d['lb']})</b>\n"
                    f"Mom: {mom_str}\n\n")
    
    if not has_data:
        msg += "⚠️ Không lấy được dữ liệu từ sàn OKX. Vui lòng kiểm tra lại kết nối!"
    
    send_telegram(msg)

# ================= KHỞI CHẠY =================
app = Flask(__name__)
@app.route("/")
def health(): return "OK", 200

def start_bot():
    time.sleep(5)
    generate_report("RETRY TEST")
    
    sched = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    for h, m, l in REPORT_SCHEDULE:
        sched.add_job(generate_report, "cron", hour=h, minute=m, args=[l])
    sched.start()
    while True: time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)