import os
import time
import ccxt
import requests
import logging
import threading
from datetime import datetime
import pytz
from flask import Flask
from dotenv import load_dotenv

# ===== ENV =====
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

# ===== LOG =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("battlefield")

# ===== WEB SERVER =====
app = Flask(__name__)

@app.route("/")
def health():
    return "SYSTEM ALIVE",200

# ===== TELEGRAM =====
def send_telegram(msg):

    if not TOKEN or not CHAT_ID:
        logger.error("Telegram config missing")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": msg,
                "parse_mode": "HTML"
            },
            timeout=20
        )
    except Exception as e:
        logger.error(e)


# ===== EXCHANGE =====
exchange = ccxt.okx({
    "enableRateLimit": True
})

# ===== STORAGE =====
oi_history = []

# ===== OKX API =====
def get_open_interest():

    url = "https://www.okx.com/api/v5/public/open-interest"

    params = {"instId":"BTC-USDT-SWAP"}

    r = requests.get(url,params=params,timeout=10)

    data = r.json()

    return float(data["data"][0]["oi"])


def get_funding():

    url = "https://www.okx.com/api/v5/public/funding-rate"

    params = {"instId":"BTC-USDT-SWAP"}

    r = requests.get(url,params=params,timeout=10)

    data = r.json()

    return float(data["data"][0]["fundingRate"])


# ===== MARKET DATA =====
def get_price():

    ticker = exchange.fetch_ticker("BTC/USDT:USDT")

    return ticker["last"]


def get_ohlc():

    data = exchange.fetch_ohlcv("BTC/USDT:USDT","5m",limit=120)

    highs = [x[2] for x in data]
    lows = [x[3] for x in data]
    closes = [x[4] for x in data]
    volumes = [x[5] for x in data]

    return highs,lows,closes,volumes


# ===== UTILS =====
def pct(a,b):

    if b == 0:
        return 0

    return (a-b)/b*100


def calc_oi_delta():

    if len(oi_history) < 4:
        return 0,0,0

    oi5 = pct(oi_history[-1],oi_history[-2])
    oi15 = pct(oi_history[-1],oi_history[-3])
    oi60 = pct(oi_history[-1],oi_history[0])

    return oi5,oi15,oi60


# ===== WHALE DETECT =====
def whale_trades():

    trades = exchange.fetch_trades("BTC/USDT",limit=50)

    whales = []

    for t in trades:

        value = t["price"] * t["amount"]

        if value > 100000:

            side = t["side"].upper()

            whales.append(f"{side} {int(value/1000)}k")

    return whales[:3]


# ===== REPORT =====
def build_report():

    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")

    price = get_price()

    highs,lows,closes,volumes = get_ohlc()

    high6 = max(highs[-72:])
    low6 = min(lows[-72:])

    vol_delta = pct(volumes[-1],volumes[-2])

    momentum = pct(closes[-1],closes[-2])

    oi = get_open_interest()

    funding = get_funding()

    oi_history.append(oi)

    if len(oi_history) > 12:
        oi_history.pop(0)

    oi5,oi15,oi60 = calc_oi_delta()

    whales = whale_trades()

    msg = f"""
🔥 BATTLEFIELD INTELLIGENCE

BTC/USDT

Price: {price:,.0f}

6H High: {high6:,.0f}
6H Low : {low6:,.0f}

Funding: {funding:.4f}%

Open Interest: {oi:,.0f}

OI Δ
5m: {oi5:.2f}%
15m: {oi15:.2f}%
1h: {oi60:.2f}%

Volume Δ
5m: {vol_delta:.2f}%

Momentum
5m: {momentum:.2f}%

Whales
{" ".join(whales) if whales else "None"}
"""

    return msg


# ===== SCHEDULER =====
def scheduler():

    send_telegram("🚀 Battlefield Bot v7 Online")

    try:
        send_telegram("🧪 TEST REPORT\n" + build_report())
    except Exception as e:
        send_telegram(f"Test report error: {e}")

    while True:

        try:

            report = build_report()

            send_telegram(report)

        except Exception as e:

            logger.error(e)

        time.sleep(3600)


# ===== MAIN =====
if __name__ == "__main__":

    threading.Thread(target=scheduler,daemon=True).start()

    port = int(os.environ.get("PORT",10000))

    app.run(host="0.0.0.0",port=port)