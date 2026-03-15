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
                "text":msg
            },
            timeout=20
        )
    except Exception as e:
        logger.error(e)

# ================= EXCHANGE =================

exchange = ccxt.okx({
    "enableRateLimit": True
})

# ================= CACHE =================

last_funding={}
last_oi={}

# ================= UTILS =================

def pct(a,b):

    if b == 0:
        return 0

    return (a-b)/b*100


# ================= SAFE API =================

def safe_get(url,params):

    try:

        r=requests.get(url,params=params,timeout=10)

        data=r.json()

        if "data" not in data or len(data["data"])==0:
            return None

        return data["data"][0]

    except Exception as e:

        logger.error(e)

        return None


# ================= TAKER FLOW =================

def get_taker_ratio(inst):

    try:

        url="https://www.okx.com/api/v5/market/taker-volume"

        r=requests.get(url,params={"instId":inst,"period":"5m"},timeout=10)

        data=r.json()

        if "data" not in data or len(data["data"])==0:
            return (0,0,0)

        row=data["data"][0]

        buy=float(row[1])
        sell=float(row[2])

        total=buy+sell

        if total==0:
            ratio=0
        else:
            ratio=buy/total*100

        return buy,sell,ratio

    except Exception as e:

        logger.error(e)

        return (0,0,0)


# ================= SYMBOL REPORT =================

def get_symbol_report(symbol,inst):

    try:

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

        # ===== funding =====

        funding_data=safe_get(
            "https://www.okx.com/api/v5/public/funding-rate",
            {"instId":inst}
        )

        funding=float(funding_data["fundingRate"]) if funding_data else 0

        # ===== OI =====

        oi_data=safe_get(
            "https://www.okx.com/api/v5/public/open-interest",
            {"instId":inst}
        )

        oi=float(oi_data["oi"]) if oi_data else 0

        # ===== TAKER FLOW =====

        taker_buy,taker_sell,taker_ratio=get_taker_ratio(inst)

        # ===== DELTA =====

        funding_delta=0
        oi_delta=0

        if inst in last_funding:
            funding_delta=pct(funding,last_funding[inst])

        if inst in last_oi:
            oi_delta=pct(oi,last_oi[inst])

        last_funding[inst]=funding
        last_oi[inst]=oi

        report=f"""
{symbol}

6H High: {high6:,.0f}
6H Low : {low6:,.0f}
Current: {price:,.0f}

Funding: {funding:.4f}% ({funding_delta:+.2f}%)
OI: {oi:,.0f} ({oi_delta:+.2f}%)

Taker Flow
Buy: {taker_buy:,.0f}
Sell: {taker_sell:,.0f}
Buy Ratio: {taker_ratio:.1f}%

Volume Δ
5m: {vol5:.2f}% | 15m: {vol15:.2f}% | 1h: {vol1h:.2f}%

Momentum
5m: {mom5:.2f}% | 15m: {mom15:.2f}% | 1h: {mom1h:.2f}%
"""

        return report

    except Exception as e:

        logger.error(e)

        return f"{symbol}\nDATA ERROR"


# ================= REPORT =================

def build_report():

    now=datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")

    btc=get_symbol_report("BTC/USDT:USDT","BTC-USDT-SWAP")

    eth=get_symbol_report("ETH/USDT:USDT","ETH-USDT-SWAP")

    msg=f"""
🔥 BATTLEFIELD INTELLIGENCE REPORT
Time: {now}

{btc}

{eth}
"""

    return msg


# ================= SCHEDULER =================

def scheduler():

    send_telegram("🚀 Battlefield Bot v9 Online")

    # ===== TEST REPORT =====
    try:
        test="🧪 TEST REPORT\n\n"+build_report()
        send_telegram(test)
    except Exception as e:
        send_telegram(f"Test Error: {e}")

    while True:

        try:

            report=build_report()

            send_telegram(report)

        except Exception as e:

            logger.error(e)

            send_telegram(f"⚠️ Bot Error\n{e}")

        time.sleep(3600)


# ================= MAIN =================

if __name__ == "__main__":

    threading.Thread(target=scheduler,daemon=True).start()

    port=int(os.environ.get("PORT",10000))

    app.run(host="0.0.0.0",port=port)