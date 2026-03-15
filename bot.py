import os
import ccxt
import requests
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

# ================= CONFIG =================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = "5047088212"

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

print("=== BATTLEFIELD INTELLIGENCE BOT v1.3 24/7 ===")
print("Open Interest + OI Change + Taker Flow")

# ================= EXCHANGE =================
exchange = ccxt.binance({
    "enableRateLimit": True,
    "options": {
        "defaultType": "future"
    },
    "urls": {
        "api": {
            "public": "https://fapi.binance.com/fapi/v1",
            "private": "https://fapi.binance.com/fapi/v1"
        }
    }
})

# ================= TELEGRAM =================
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message
        }, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# ================= CORE DATA =================
def get_asset_data(symbol):

    try:
        ticker = exchange.fetch_ticker(symbol)
        ob = exchange.fetch_order_book(symbol, limit=20)

        bids_vol = sum(float(b[1]) for b in ob['bids'])
        asks_vol = sum(float(a[1]) for a in ob['asks']) or 1

        imbalance = bids_vol / asks_vol

        price = ticker.get('last', 0)
        high = ticker.get('high', 0)
        low = ticker.get('low', 0)
        volume = ticker.get('quoteVolume', 0)

        # ===== OPEN INTEREST =====
        oi_raw = exchange.fetch_open_interest(symbol)
        oi_contracts = float(oi_raw.get('openInterest', 0))
        oi_usd = oi_contracts * price

        # ===== TAKER FLOW =====
        info = ticker.get('info', {})

        taker_buy_quote = float(info.get('takerBuyQuoteVolume', 0))
        total_vol = float(ticker.get('quoteVolume', 1))

        taker_buy_pct = round((taker_buy_quote / total_vol) * 100, 1)

        if taker_buy_pct > 52:
            flow_label = "TAKER BUYING MẠNH"
        elif taker_buy_pct < 48:
            flow_label = "TAKER SELLING MẠNH"
        else:
            flow_label = "NEUTRAL"

        # ===== OI CHANGE =====
        oi_changes = {}

        for tf in ['1m','5m','15m','30m','1h']:

            try:
                hist = exchange.fetch_open_interest_history(symbol, tf, limit=2)

                if len(hist) >= 2:

                    prev = float(hist[-2]['openInterest'])
                    curr = float(hist[-1]['openInterest'])

                    pct = ((curr-prev)/prev)*100 if prev>0 else 0
                    oi_changes[tf] = round(pct,2)

                else:
                    oi_changes[tf] = 0

            except:
                oi_changes[tf] = "N/A"

        # ===== FUNDING =====
        funding_info = exchange.fetch_funding_rate(symbol)
        funding = funding_info.get('fundingRate',0)*100

        # ===== MOMENTUM =====
        deltas = {}

        for tf in ['5m','15m','1h','4h','8h','1d']:

            try:

                ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)

                if len(ohlcv)>=2:

                    prev = ohlcv[-2][4]
                    curr = ohlcv[-1][4]

                    deltas[tf] = round((curr-prev)/prev*100,2)

                else:
                    deltas[tf]=0

            except:
                deltas[tf]=0

        vol_idx = ((high-low)/price*100) if price>0 else 0

        return {
            "high":high,
            "low":low,
            "price":price,
            "volume":volume,
            "imbalance":imbalance,
            "funding":funding,
            "vol_idx":vol_idx,
            "deltas":deltas,
            "oi_usd":oi_usd,
            "taker_buy_pct":taker_buy_pct,
            "flow_label":flow_label,
            "oi_changes":oi_changes
        }

    except Exception as e:

        print(f"Error {symbol}: {e}")
        return None


# ================= REPORT =================
def generate_report(label):

    now = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    report = f"""
🔥 BATTLEFIELD REPORT
{label}
Time: {now}

"""

    for asset in ["BTC","ETH"]:

        sym = f"{asset}/USDT:USDT"

        data = get_asset_data(sym)

        if not data:

            report+=f"{asset} DATA ERROR\n"
            continue

        oi_delta = []

        for tf in ['1m','5m','15m','30m','1h']:

            val=data["oi_changes"][tf]

            if isinstance(val,str):
                oi_delta.append(f"{tf}:{val}")
            else:
                oi_delta.append(f"{tf}:{val:+.2f}%")

        oi_delta_str=" | ".join(oi_delta)

        report+=f"""
{asset}
Price: {data['price']:,.2f}
High: {data['high']:,.2f} Low: {data['low']:,.2f}

Vol: {data['volume']:,.0f}

Funding: {data['funding']:.4f}%

OI: {data['oi_usd']:,.0f} USD
OI Δ: {oi_delta_str}

Taker Flow:
{data['taker_buy_pct']}% ({data['flow_label']})

Orderbook Pressure:
{data['imbalance']:.2f}x

Momentum:
5m {data['deltas']['5m']}%
15m {data['deltas']['15m']}%
1h {data['deltas']['1h']}%
4h {data['deltas']['4h']}%
8h {data['deltas']['8h']}%
1d {data['deltas']['1d']}%

"""

    print(report)

    send_telegram(report)


# ================= SCHEDULER =================
sched = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")

report_times = [

(7,0,"T-60m"),
(7,30,"T-30m"),
(7,45,"T-15m"),
(7,55,"T-5m"),

(15,0,"T-60m"),
(15,30,"T-30m"),
(15,45,"T-15m"),
(15,55,"T-5m"),

(19,30,"T-60m"),
(20,0,"T-30m"),
(20,15,"T-15m"),
(20,25,"T-5m")

]

for h,m,label in report_times:

    sched.add_job(
        generate_report,
        'cron',
        hour=h,
        minute=m,
        args=[label],
        id=f"report_{h}_{m}"
    )


print("Scheduler ready")

generate_report("TEST REPORT")

send_telegram("Bot started 24/7")

# ================= WEB SERVER (RENDER KEEP ALIVE) =================
from flask import Flask
import threading

app = Flask(__name__)

@app.route("/")
def home():
    return "BOT RUNNING"


def run_web():

    port=int(os.environ.get("PORT",10000))

    app.run(host="0.0.0.0",port=port)


threading.Thread(target=run_web).start()


# ================= START BOT =================
if __name__=="__main__":

    try:

        sched.start()

    except (KeyboardInterrupt,SystemExit):

        print("Bot stopped")