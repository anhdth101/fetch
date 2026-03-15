import os, ccxt, requests, threading, time, logging
from datetime import datetime
import pytz
from flask import Flask

# ================= 1. BẢO MẬT (LẤY TỪ RENDER) =================
# Tuyệt đối không dán ID thật vào đây để tránh lộ trên GitHub
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BattlefieldBot")

# Cấu hình sàn OKX
exchange = ccxt.okx({
    'enableRateLimit': True, 
    'timeout': 30000, 
    'options': {'defaultType': 'swap'}
})

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        logger.error("Thiếu TOKEN hoặc CHAT_ID. Kiểm tra lại Environment Variables trên Render.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=15)
        logger.info(f"Telegram Resp: {r.status_code}")
    except Exception as e:
        logger.error(f"Lỗi gửi Telegram: {e}")

# ================= 2. LOGIC LẤY DỮ LIỆU SÀN =================
def get_market_report():
    now = datetime.now(TIMEZONE).strftime("%H:%M:%S")
    msg = f"📊 <b>BATTLEFIELD v3.1 (SECURE)</b>\n🕒 {now} VN\n\n"
    
    has_data = False
    for sym in SYMBOLS:
        try:
            # Ưu tiên lấy giá trước (Tránh lỗi tin nhắn trống)
            ticker = exchange.fetch_ticker(sym)
            price = ticker['last']
            
            # Thử lấy thêm OI và Funding (Nếu lỗi thì bỏ qua, vẫn hiện giá)
            try:
                f_rate = exchange.fetch_funding_rate(sym).get('fundingRate', 0) * 100
                msg += f"<b>{sym.split('-')[0]}</b>: <code>{price:,.1f}</code> | Fnd: {f_rate:.4f}%\n"
            except:
                msg += f"<b>{sym.split('-')[0]}</b>: <code>{price:,.1f}</code>\n"
            
            has_data = True
        except Exception as e:
            logger.error(f"Lỗi fetch {sym}: {e}")
            msg += f"<b>{sym.split('-')[0]}</b>: ⚠️ Sàn phản hồi chậm\n"

    if has_data:
        send_telegram(msg)

# ================= 3. KHỞI CHẠY & WEB SERVER =================
app = Flask(__name__)
@app.route("/")
def health(): return "OK", 200

def start_bot():
    time.sleep(5)
    # Kiểm tra biến môi trường
    if not TOKEN or not CHAT_ID:
        logger.error("KHÔNG TÌM THẤY BIẾN MÔI TRƯỜNG TRÊN RENDER!")
        return
        
    send_telegram("🚀 <b>Hệ thống v3.1 Bảo mật đã Online!</b>")
    get_market_report()
    
    # Gửi báo cáo định kỳ mỗi 60 phút
    while True:
        time.sleep(3600)
        get_market_report()

if __name__ == "__main__":
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)