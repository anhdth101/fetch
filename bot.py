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

# ================= ENV =================

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("battlefield")

# ================= WEB SERVER =================

app = Flask(__name__)

@app.route("/")
def health():
    return "SYSTEM ALIVE",200

# ================= TELEGRAM =================

def send_telegram(msg):

    if not TOKEN or not CHAT_ID:
        logger.error("Missing Telegram config")
        return

    url=f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            data={
                "chat_id":CHAT_ID,
                "text":msg,
                "parse_mode":"HTML"
            },
            timeout=20
        )
    except Exception as e:
        logger.error(e)

# ================= EXCHANGE =================

exchange = ccxt.okx({
    "enableRateLimit": True
})

# ================= UTILS =================

def pct(a,b):

    if b == 0:
        return 0

    return (a-b)/b*100


# ================= SYMBOL REPORT =================

def get_symbol_report(symbol,inst):

    ticker = exchange.fetch_ticker(symbol)

    price = ticker["last"]

    ohlc = exchange.fetch_ohlcv(symbol,"5m",limit=120)

    highs=[x[2] for x in ohlc]
    lows=[x[3] for x in ohlc]
    closes=[x[4] for x in ohlc]
    volumes=[x[5] for x in ohlc]

    high6=max(highs[-72:])
    low6=min(lows[-72:])

    vol5=pct(volumes[-1],volumes[-2])
    vol15=pct(volumes[-1],volumes[-3])
    vol1h=pct(volumes[-1],volumes[-12])

    mom5=pct(closes[-1],closes[-2])
    mom15=pct(closes[-1],closes[-3])
    mom1h=pct(closes[-1],closes[-12])

    funding_url="https://www.okx.com/api/v5/public/funding-rate"
    funding=requests.get(funding_url,params={"instId":inst}).json()
    funding=float(funding["data"][0]["fundingRate"])

    oi_url="https://www.okx.com/api/v5/public/open-interest"
    oi=requests.get(oi_url,params={"instId":inst}).json()
    oi=float(oi["data"][0]["oi"])

    report=f"""
{symbol}

6H High: {high6:,.0f}
6H Low : {low6:,.0f}
Current: {price:,.0f}

Funding: {funding:.4f}%
OI: {oi:,.0f}

Volume Δ
5m: {vol5:.2f}% | 15m: {vol15:.2f}% | 1h: {vol1h:.2f}%

Momentum
5m: {mom5:.2f}% | 15m: {mom15:.2f}% | 1h: {mom1h:.2f}%
"""

    return report


# ================= REPORT =================

def build_report():

    now=datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")

    btc=get_symbol_report("BTC/USDT:USDT","BTC-USDT-SWAP")

    eth=get_symbol_report("ETH/USDT:USDT","ETH-USDT-SWAP")

    liquidation="Liquidation: Long 0M | Short 0M"

    msg=f"""
🔥 BATTLEFIELD INTELLIGENCE REPORT
Time: {now}

{btc}

{eth}

{liquidation}
"""

    return msg


# ================= SCHEDULER =================

def scheduler():

    send_telegram("🚀 Battlefield Bot v7 Online")

    try:
        send_telegram("🧪 TEST REPORT\n" + build_report())
    except Exception as e:
        send_telegram(f"Test report error: {e}")

    while True:

        try:

            report=build_report()

            send_telegram(report)

        except Exception as e:

            logger.error(e)

        time.sleep(3600)


# ================= MAIN =================

if __name__ == "__main__":

    threading.Thread(target=scheduler,daemon=True).start()

    port=int(os.environ.get("PORT",10000))

    app.run(host="0.0.0.0",port=port)