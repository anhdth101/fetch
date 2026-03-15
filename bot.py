import os
import requests
import threading
import time
import logging
import ccxt
import numpy as np
import pytz
from datetime import datetime
from flask import Flask

# ================= CONFIG =================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

SYMBOLS = ["BTC/USDT","ETH/USDT"]

SCHEDULE_TIMES = [
"07:30","07:45","07:55",
"15:30","15:45","15:55",
"19:30","20:00","20:15","20:25"
]

# ================= LOG =================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BattlefieldBot")

# ================= WEB SERVER =================

app = Flask(__name__)

@app.route("/")
def health():
    return "SYSTEM ALIVE",200

# ================= TELEGRAM =================

def send_telegram(msg):

    if not TOKEN or not CHAT_ID:
        logger.error("Telegram config missing")
        return

    url=f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:

        requests.post(url,data={
            "chat_id":CHAT_ID,
            "text":msg,
            "parse_mode":"HTML"
        },timeout=20)

    except Exception as e:
        logger.error(e)

# ================= EXCHANGE =================

exchange = ccxt.okx({
'enableRateLimit':True
})

# ================= MARKET DATA =================

def get_ohlc(symbol,tf,limit):

    data = exchange.fetch_ohlcv(symbol,tf,limit=limit)
    arr = np.array(data)

    high = arr[:,2]
    low = arr[:,3]
    close = arr[:,4]
    vol = arr[:,5]

    return high,low,close,vol

# ================= 6H RANGE =================

def calc_range_6h(symbol):

    high,low,close,vol = get_ohlc(symbol,"5m",72)

    return max(high),min(low),close[-1]

# ================= MOMENTUM =================

def momentum(symbol,minutes):

    data = exchange.fetch_ohlcv(symbol,"1m",limit=minutes+1)

    p0 = data[0][4]
    p1 = data[-1][4]

    return (p1-p0)/p0*100

# ================= VOLUME CHANGE =================

def volume_change(symbol,minutes):

    _,_,_,vol = get_ohlc(symbol,"1m",minutes+1)

    v0 = sum(vol[:-1])
    v1 = sum(vol)

    if v0==0:
        return 0

    return (v1-v0)/v0*100

# ================= FUNDING =================

def get_funding(symbol):

    try:

        inst=symbol.replace("/","-")+"-SWAP"

        r=requests.get(
        f"https://www.okx.com/api/v5/public/funding-rate?instId={inst}",
        timeout=10).json()

        return float(r["data"][0]["fundingRate"])*100

    except:

        return 0

# ================= OPEN INTEREST =================

def get_open_interest(symbol):

    try:

        inst=symbol.replace("/","-")+"-SWAP"

        r=requests.get(
        f"https://www.okx.com/api/v5/public/open-interest?instId={inst}",
        timeout=10).json()

        return float(r["data"][0]["oi"])

    except:

        return 0

# ================= WHALE DETECT =================

def whale_detect(symbol):

    whales=[]

    try:

        trades=exchange.fetch_trades(symbol,limit=50)

        for t in trades:

            size=t["amount"]*t["price"]

            if size>100000:

                side=t["side"].upper()

                whales.append(f"{side} {int(size/1000)}k")

    except:
        pass

    return whales[:3]

# ================= LIQUIDATION =================

def liquidation():

    try:

        r=requests.get(
        "https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP",
        timeout=10).json()

        data=r.get("data",[])

        long_liq=0
        short_liq=0

        for x in data:

            v=float(x["sz"])*float(x["px"])

            if x["side"]=="sell":
                long_liq+=v
            else:
                short_liq+=v

        return f"Long {int(long_liq/1000000)}M | Short {int(short_liq/1000000)}M"

    except:

        return "N/A"

# ================= HEALTH CHECK =================

def health_log():

    msg="🩺 <b>HEALTH CHECK</b>\n"

    msg+="Exchange: OKX\n"
    msg+=f"Symbols: {', '.join(SYMBOLS)}\n"

    try:

        t=exchange.fetch_ticker("BTC/USDT")

        msg+=f"BTC Feed: OK ({int(t['last'])})\n"

    except:

        msg+="BTC Feed: FAIL\n"

    msg+=f"Server Time: {datetime.now(TIMEZONE).strftime('%H:%M:%S')}"

    send_telegram(msg)

# ================= REPORT =================

def build_report():

    now=datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")

    msg=f"🔥 <b>BATTLEFIELD INTELLIGENCE REPORT</b>\nTime: {now}\n\n"

    for s in SYMBOLS:

        high,low,price=calc_range_6h(s)

        v5=volume_change(s,5)
        v15=volume_change(s,15)
        v60=volume_change(s,60)

        m5=momentum(s,5)
        m15=momentum(s,15)
        m60=momentum(s,60)

        funding=get_funding(s)
        oi=get_open_interest(s)

        whales=whale_detect(s)

        msg+=f"<b>{s}</b>\n"
        msg+=f"6H High: {high:,.0f}\n"
        msg+=f"6H Low : {low:,.0f}\n"
        msg+=f"Current: {price:,.0f}\n\n"

        msg+=f"Funding: {funding:.4f}%\n"
        msg+=f"OI: {oi:,.0f}\n\n"

        msg+="Volume Δ\n"
        msg+=f"5m: {v5:.2f}% | 15m: {v15:.2f}% | 1h: {v60:.2f}%\n\n"

        msg+="Momentum\n"
        msg+=f"5m: {m5:.2f}% | 15m: {m15:.2f}% | 1h: {m60:.2f}%\n\n"

        if whales:
            msg+="🐋 Whale: "+", ".join(whales)+"\n\n"

    msg+=f"Liquidation: {liquidation()}"

    return msg

# ================= SCHEDULER =================

def scheduler():

    send_telegram("🚀 <b>Battlefield Bot Online</b>")

    health_log()

    try:
        send_telegram("🧪 <b>TEST REPORT</b>\n\n"+build_report())
    except Exception as e:
        send_telegram(f"❌ TEST REPORT FAILED\n{e}")

    last_hour=None

    while True:

        now=datetime.now(TIMEZONE)

        hm=now.strftime("%H:%M")

        if hm in SCHEDULE_TIMES:

            send_telegram(build_report())

            time.sleep(60)

        if last_hour!=now.hour:

            send_telegram(build_report())

            last_hour=now.hour

        time.sleep(10)

# ================= MAIN =================

if __name__=="__main__":

    threading.Thread(target=scheduler,daemon=True).start()

    port=int(os.environ.get("PORT",10000))

    app.run(host="0.0.0.0",port=port)