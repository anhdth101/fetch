import os
import ccxt
import requests
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask
import logging
import threading

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = "5047088212"

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not set!")

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]

TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

REPORT_SCHEDULE = [
    (7, 0, "T-60m"), (7, 30, "T-30m"), (7, 45, "T-15m"), (7, 55, "T-5m"),
    (15, 0, "T-60m"), (15, 30, "T-30m"), (15, 45, "T-15m"), (15, 55, "T-5m"),
    (19, 30, "T-60m"), (20, 0, "T-30m"), (20, 15, "T-15m"), (20, 25, "T-5m"),
]

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("BattlefieldBot")

logger.info("=== BATTLEFIELD BOT v1.5 - Render Web Service Ready ===")

# ================= EXCHANGE =================
exchange = ccxt.binance({
    "enableRateLimit": True,
    "timeout": 20000,
    "options": {"defaultType": "future", "adjustForTimeDifference": True}
})

# ================= TELEGRAM =================
def send_telegram(text: str):
    text = text[:3900] + "..." if len(text) > 3900 else text
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=12).raise_for_status()
    except Exception as e:
        logger.error(f"Telegram failed: {e}")

# ================= DATA FETCH (giữ nguyên như cũ, rút gọn comment) =================
def fetch_market_data(symbol: str) -> dict | None:
    try:
        ticker = exchange.fetch_ticker(symbol)
        ob = exchange.fetch_order_book(symbol, limit=20)
        bids_vol = sum(b[1] for b in ob["bids"])
        asks_vol = sum(a[1] for a in ob["asks"]) or 1.0
        imbalance = bids_vol / asks_vol

        price = ticker["last"]
        vol_usdt = ticker["quoteVolume"] or 0
        oi_data = exchange.fetch_open_interest(symbol)
        oi_usd = float(oi_data.get("openInterest", 0)) * price

        info = ticker.get("info", {})
        taker_buy_quote = float(info.get("takerBuyQuoteVolume", 0))
        taker_buy_pct = round((taker_buy_quote / (vol_usdt or 1)) * 100, 1)
        flow_label = "TAKER BUYING" if taker_buy_pct > 52 else "TAKER SELLING" if taker_buy_pct < 48 else "NEUTRAL"

        oi_changes = {}
        for tf in ["1m", "5m", "15m", "30m", "1h"]:
            try:
                hist = exchange.fetch_open_interest_history(symbol, tf, limit=2)
                if len(hist) >= 2:
                    prev, curr = float(hist[-2]["openInterest"]), float(hist[-1]["openInterest"])
                    oi_changes[tf] = round(((curr - prev) / prev * 100) if prev else 0, 2)
                else:
                    oi_changes[tf] = "N/A"
            except:
                oi_changes[tf] = "N/A"

        deltas = {}
        for tf in ["5m", "15m", "1h", "4h", "8h", "1d"]:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)
                if len(ohlcv) >= 2:
                    deltas[tf] = round((ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4] * 100, 2)
                else:
                    deltas[tf] = 0.0
            except:
                deltas[tf] = 0.0

        funding = exchange.fetch_funding_rate(symbol).get("fundingRate", 0) * 100

        return {
            "price": price, "high": ticker["high"], "low": ticker["low"],
            "volume_usdt": vol_usdt, "imbalance": imbalance, "funding": funding,
            "oi_usd": oi_usd, "taker_buy_pct": taker_buy_pct, "flow_label": flow_label,
            "oi_changes": oi_changes, "deltas": deltas
        }
    except Exception as e:
        logger.error(f"Data error {symbol}: {e}")
        return None

# ================= REPORT (giữ nguyên) =================
def generate_report(label: str):
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    report = f"🔥 <b>BATTLEFIELD REPORT</b> — {label}\nTime: {now}\n\n"

    for asset, sym in [("BTC", "BTC/USDT:USDT"), ("ETH", "ETH/USDT:USDT")]:
        data = fetch_market_data(sym)
        if not data:
            report += f"<b>{asset}</b>\nDATA ERROR\n\n"
            continue

        oi_str = " | ".join(
            f"{tf}:{data['oi_changes'][tf] if isinstance(data['oi_changes'][tf], str) else f'{data['oi_changes'][tf]:+.2f}%'}"
            for tf in ["1m", "5m", "15m", "30m", "1h"]
        )
        mom_str = " | ".join(f"{tf} {data['deltas'][tf]:+.2f}%" for tf in ["5m", "15m", "1h", "4h", "8h", "1d"])

        report += f"""<b>{asset}</b>

Price: {data['price']:,.2f} | H/L: {data['high']:,.2f}/{data['low']:,.2f}
Vol: {data['volume_usdt']:,.0f} USDT | Funding: {data['funding']:.4f}%
OI: {data['oi_usd']:,.0f} USD | OI Δ: {oi_str}
Taker: {data['taker_buy_pct']}% ({data['flow_label']})
OB: {data['imbalance']:.2f}x
Momentum: {mom_str}

"""
    logger.info(report.strip())
    send_telegram(report)

# ================= SCHEDULER =================
scheduler = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")

for h, m, label in REPORT_SCHEDULE:
    scheduler.add_job(generate_report, "cron", hour=h, minute=m, args=[label],
                      id=f"report-{h:02d}{m:02d}", misfire_grace_time=300)

logger.info("Scheduler ready")

# Test startup
generate_report("TEST REPORT (STARTUP)")
send_telegram("🚀 BOT STARTED on Render Web Service")

# ================= FLASK DUMMY SERVER =================
app = Flask(__name__)

@app.route("/")
def health():
    return "Battlefield Bot is alive!"

# Chạy scheduler trong thread riêng, Flask ở main thread
def run_scheduler():
    try:
        scheduler.start()
    except Exception as e:
        logger.critical(f"Scheduler error: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_scheduler, daemon=True).start()
    # Gunicorn sẽ override phần này, không cần app.run() nữa
    # Chỉ giữ app để gunicorn import