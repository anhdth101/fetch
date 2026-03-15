import os
import ccxt
import requests
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask
import threading

# ================= CONFIG =================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = "5047088212"

if not TOKEN:
    raise Exception("TELEGRAM_TOKEN not set")

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]

VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

print("=== BATTLEFIELD INTELLIGENCE BOT v1.3 ===")

# ================= EXCHANGE =================
exchange = ccxt.binance({
    "enableRateLimit": True,
    "timeout": 20000,
    "options": {"defaultType": "future"}
})

# ================= TELEGRAM =================
def send_telegram(message):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    try:

        if len(message) > 3900:
            message = message[:3900]

        requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=10
        )

    except Exception as e:
        print("Telegram error:", e)


# ================= MARKET DATA =================
def get_asset_data(symbol):

    try:

        ticker = exchange.fetch_ticker(symbol)
        ob = exchange.fetch_order_book(symbol, limit=20)

        bids = sum(b[1] for b in ob["bids"])
        asks = sum(a[1] for a in ob["asks"]) or 1

        imbalance = bids / asks

        price = ticker["last"]
        high = ticker["high"]
        low = ticker["low"]
        volume = ticker["quoteVolume"]

        # OPEN INTEREST
        oi_raw = exchange.fetch_open_interest(symbol)
        oi_contracts = float(oi_raw.get("openInterest", 0))
        oi_usd = oi_contracts * price

        # TAKER FLOW
        info = ticker.get("info", {})

        taker_buy_quote = float(info.get("takerBuyQuoteVolume", 0))
        total_vol = float(volume or 1)

        taker_buy_pct = round((taker_buy_quote / total_vol) * 100, 1)

        if taker_buy_pct > 52:
            flow_label = "TAKER BUYING"
        elif taker_buy_pct < 48:
            flow_label = "TAKER SELLING"
        else:
            flow_label = "NEUTRAL"

        # OI CHANGE
        oi_changes = {}

        for tf in ["1m", "5m", "15m", "30m", "1h"]:

            try:

                hist = exchange.fetch_open_interest_history(symbol, tf, limit=2)

                if len(hist) >= 2:

                    prev = float(hist[-2]["openInterest"])
                    curr = float(hist[-1]["openInterest"])

                    pct = ((curr - prev) / prev) * 100 if prev else 0
                    oi_changes[tf] = round(pct, 2)

                else:
                    oi_changes[tf] = 0

            except:
                oi_changes[tf] = "N/A"

        # MOMENTUM
        deltas = {}

        for tf in ["5m", "15m", "1h", "4h", "8h", "1d"]:

            try:

                ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)

                if len(ohlcv) >= 2:

                    prev = ohlcv[-2][4]
                    curr = ohlcv[-1][4]

                    deltas[tf] = round((curr - prev) / prev * 100, 2)

                else:
                    deltas[tf] = 0

            except:
                deltas[tf] = 0

        funding = exchange.fetch_funding_rate(symbol).get("fundingRate", 0) * 100

        return {
            "price": price,
            "high": high,
            "low": low,
            "volume": volume,
            "imbalance": imbalance,
            "funding": funding,
            "oi_usd": oi_usd,
            "taker_buy_pct": taker_buy_pct,
            "flow_label": flow_label,
            "oi_changes": oi_changes,
            "deltas": deltas
        }

    except Exception as e:

        print("DATA ERROR:", symbol, e)
        return None


# ================= REPORT =================
def generate_report(label):

    now = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")

    report = f"""
🔥 <b>BATTLEFIELD REPORT</b>
{label}

Time: {now}

"""

    for asset in ["BTC", "ETH"]:

        symbol = f"{asset}/USDT:USDT"
        data = get_asset_data(symbol)

        if not data:
            report += f"{asset} DATA ERROR\n"
            continue

        oi_delta = []

        for tf in ["1m", "5m", "15m", "30m", "1h"]:

            val = data["oi_changes"][tf]

            if isinstance(val, str):
                oi_delta.append(f"{tf}:{val}")
            else:
                oi_delta.append(f"{tf}:{val:+.2f}%")

        oi_delta_str = " | ".join(oi_delta)

        report += f"""
<b>{asset}</b>

Price: {data['price']:,.2f}
High: {data['high']:,.2f}  Low: {data['low']:,.2f}

Volume: {data['volume']:,.0f}

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

for h, m, label in report_times:

    sched.add_job(
        generate_report,
        "cron",
        hour=h,
        minute=m,
        args=[label]
    )

print("Scheduler ready")

generate_report("TEST REPORT")

send_telegram("BOT STARTED 24/7")


# ================= WEB SERVER =================
app = Flask(__name__)

@app.route("/")
def home():
    return "BOT RUNNING"


def run_web():

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )


threading.Thread(target=run_web, daemon=True).start()


# ================= START =================
if __name__ == "__main__":

    try:

        sched.start()

    except (KeyboardInterrupt, SystemExit):

        print("BOT STOPPED")