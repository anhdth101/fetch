import os
import ccxt
import requests
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask
import threading
import logging

# ================= CONFIGURATION =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = "5047088212"           # Thay bằng chat id của bạn nếu cần

if not TELEGRAM_TOKEN:
    raise ValueError("Environment variable TELEGRAM_TOKEN is not set")

SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
]

TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

# Báo cáo sẽ được gửi vào các mốc thời gian này (giờ VN)
REPORT_SCHEDULE = [
    (7,  0,  "T-60m"),
    (7,  30, "T-30m"),
    (7,  45, "T-15m"),
    (7,  55, "T-5m"),

    (15, 0,  "T-60m"),
    (15, 30, "T-30m"),
    (15, 45, "T-15m"),
    (15, 55, "T-5m"),

    (19, 30, "T-60m"),
    (20, 0,  "T-30m"),
    (20, 15, "T-15m"),
    (20, 25, "T-5m"),
]

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("BattlefieldBot")

print("=== BATTLEFIELD INTELLIGENCE BOT v1.3 ===")

# ================= BINANCE EXCHANGE =================
exchange = ccxt.binance({
    "enableRateLimit": True,
    "timeout": 20000,
    "options": {
        "defaultType": "future",
        "adjustForTimeDifference": True,
    }
})

# ================= TELEGRAM SENDER =================
def send_telegram_message(text: str):
    if len(text) > 3900:
        text = text[:3900] + "... (truncated)"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        resp = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=12
        )
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


# ================= DATA FETCHER =================
def fetch_market_data(symbol: str) -> dict | None:
    try:
        ticker = exchange.fetch_ticker(symbol)
        orderbook = exchange.fetch_order_book(symbol, limit=20)

        bids_volume = sum(b[1] for b in orderbook["bids"])
        asks_volume = sum(a[1] for a in orderbook["asks"]) or 1.0
        orderbook_imbalance = bids_volume / asks_volume

        price = ticker["last"]
        high = ticker["high"]
        low = ticker["low"]
        quote_volume = ticker["quoteVolume"] or 0

        # Open Interest
        oi_data = exchange.fetch_open_interest(symbol)
        oi_contracts = float(oi_data.get("openInterest", 0))
        oi_usd = oi_contracts * price

        # Taker Buy/Sell flow
        info = ticker.get("info", {})
        taker_buy_quote = float(info.get("takerBuyQuoteVolume", 0))
        total_volume = float(quote_volume or 1)
        taker_buy_ratio = round((taker_buy_quote / total_volume) * 100, 1)

        if taker_buy_ratio > 52:
            flow_status = "TAKER BUYING"
        elif taker_buy_ratio < 48:
            flow_status = "TAKER SELLING"
        else:
            flow_status = "NEUTRAL"

        # Open Interest changes
        oi_changes = {}
        for timeframe in ["1m", "5m", "15m", "30m", "1h"]:
            try:
                history = exchange.fetch_open_interest_history(symbol, timeframe, limit=2)
                if len(history) >= 2:
                    prev = float(history[-2]["openInterest"])
                    curr = float(history[-1]["openInterest"])
                    change_pct = ((curr - prev) / prev * 100) if prev != 0 else 0
                    oi_changes[timeframe] = round(change_pct, 2)
                else:
                    oi_changes[timeframe] = "N/A"
            except Exception:
                oi_changes[timeframe] = "N/A"

        # Price momentum
        price_changes = {}
        for timeframe in ["5m", "15m", "1h", "4h", "8h", "1d"]:
            try:
                candles = exchange.fetch_ohlcv(symbol, timeframe, limit=2)
                if len(candles) >= 2:
                    prev_close = candles[-2][4]
                    curr_close = candles[-1][4]
                    pct = (curr_close - prev_close) / prev_close * 100
                    price_changes[timeframe] = round(pct, 2)
                else:
                    price_changes[timeframe] = 0.0
            except Exception:
                price_changes[timeframe] = 0.0

        funding_rate = exchange.fetch_funding_rate(symbol).get("fundingRate", 0) * 100

        return {
            "price": price,
            "high": high,
            "low": low,
            "volume_usdt": quote_volume,
            "orderbook_imbalance": orderbook_imbalance,
            "funding_rate_pct": funding_rate,
            "oi_usd": oi_usd,
            "taker_buy_pct": taker_buy_ratio,
            "taker_flow": flow_status,
            "oi_changes": oi_changes,
            "price_changes": price_changes
        }

    except Exception as e:
        logger.error(f"Failed to fetch data for {symbol}: {str(e)}")
        return None


# ================= REPORT GENERATOR =================
def generate_battlefield_report(label: str):
    now_vn = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    report = f"""
🔥 <b>BATTLEFIELD REPORT</b>  —  {label}
Time: {now_vn}

"""

    for asset, symbol in [("BTC", "BTC/USDT:USDT"), ("ETH", "ETH/USDT:USDT")]:
        data = fetch_market_data(symbol)

        if not data:
            report += f"<b>{asset}</b>\nDATA ERROR\n\n"
            continue

        oi_deltas = []
        for tf in ["1m", "5m", "15m", "30m", "1h"]:
            val = data["oi_changes"].get(tf)
            if isinstance(val, str):
                oi_deltas.append(f"{tf}:{val}")
            else:
                oi_deltas.append(f"{tf}:{val:+.2f}%")

        momentum_lines = []
        for tf in ["5m", "15m", "1h", "4h", "8h", "1d"]:
            pct = data["price_changes"].get(tf, 0)
            momentum_lines.append(f"{tf} {pct:+.2f}%")

        report += f"""
<b>{asset}</b>

Price:          {data['price']:,.2f} USDT
High / Low:     {data['high']:,.2f}  /  {data['low']:,.2f}

Volume (24h):   {data['volume_usdt']:,.0f} USDT

Funding Rate:   {data['funding_rate_pct']:.4f}%

OI:             {data['oi_usd']:,.0f} USD
OI Δ:           {' | '.join(oi_deltas)}

Taker Flow:     {data['taker_buy_pct']}%  ({data['taker_flow']})

Orderbook:      {data['orderbook_imbalance']:.2f}x bids pressure

Momentum:
{' | '.join(momentum_lines)}

"""

    logger.info(report.strip())
    send_telegram_message(report)


# ================= FLASK KEEP-ALIVE SERVER =================
app = Flask(__name__)

@app.route("/")
def health_check():
    return "Battlefield Bot is running..."

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


# ================= MAIN =================
if __name__ == "__main__":
    # Start Flask in background thread (for render.com / railway / heroku / etc.)
    threading.Thread(target=run_flask_server, daemon=True).start()

    scheduler = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")

    for hour, minute, label in REPORT_SCHEDULE:
        scheduler.add_job(
            generate_battlefield_report,
            "cron",
            hour=hour,
            minute=minute,
            args=[label],
            id=f"report-{hour:02d}{minute:02d}",
            misfire_grace_time=300
        )

    logger.info("Scheduler jobs registered. Starting bot...")

    # Test run
    generate_battlefield_report("TEST / MANUAL REPORT")
    send_telegram_message("🚀 BOT STARTED 24/7")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Scheduler crashed: {e}")