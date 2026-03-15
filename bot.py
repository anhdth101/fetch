import os, requests, threading, time, logging, ccxt
from datetime import datetime
import pytz
from flask import Flask
from dotenv import load_dotenv

# Tự động nạp file .env nếu đang chạy ở máy cá nhân
load_dotenv()

# Lấy biến môi trường (Ưu tiên từ Render Settings)
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BattlefieldBot")

app = Flask(__name__)

@app.route("/")
def health(): return "SYSTEM ALIVE", 200

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        logger.error("❌ LỖI: Không tìm thấy TOKEN hoặc CHAT_ID. Kiểm tra lại Render Environment!")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=20)
        logger.info(f"📡 Status: {r.status_code}")
    except Exception as e:
        logger.error(f"❌ Lỗi gửi tin: {e}")

def main_logic():
    time.sleep(5)
    send_telegram("🚀 <b>Hệ thống v3.7 (Final Fix) đã Online!</b>")
    
    # Khởi tạo sàn OKX
    exchange = ccxt.okx({'timeout': 30000, 'enableRateLimit': True})
    
    while True:
        try:
            now = datetime.now(TIMEZONE).strftime("%H:%M:%S")
            # Quét BTC & ETH
            btc = exchange.fetch_ticker("BTC-USDT-SWAP")
            eth = exchange.fetch_ticker("ETH-USDT-SWAP")
            
            msg = (f"📊 <b>BÁO CÁO THỊ TRƯỜNG</b>\n🕒 {now}\n\n"
                   f"<b>BTC</b>: <code>{btc['last']:,.1f}</code>\n"
                   f"<b>ETH</b>: <code>{eth['last']:,.2f}</code>")
            
            send_telegram(msg)
        except Exception as e:
            logger.error(f"Sàn lỗi: {e}")
            
        time.sleep(3600) # 1 tiếng báo một lần

if __name__ == "__main__":
    threading.Thread(target=main_logic, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)