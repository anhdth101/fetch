import ccxt
import requests
import time
from datetime import datetime
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler

print("=== BATTLEFIELD INTELLIGENCE BOT v1.3 24/7 ===")
print("Chế độ chạy liên tục 24/7 - Báo cáo tự động trước session")
print("Open Interest + OI Change 1m/5m/15m/30m/1h + Taker Flow")

# ================= CONFIG =================
TOKEN = "8748933238:AAFO6Crfew1PfxuPrpU6paLF3KV4x8LkKLw"
CHAT_ID = "5047088212"

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

# ================= EXCHANGE =================
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# ================= TELEGRAM =================
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# ================= CORE DATA FETCHER =================
def get_asset_data(symbol: str):
    try:
        ticker = exchange.fetch_ticker(symbol)
        ob = exchange.fetch_order_book(symbol, limit=20)

        bids_vol = sum(float(b[1]) for b in ob['bids'])
        asks_vol = sum(float(a[1]) for a in ob['asks']) or 1.0
        imbalance = bids_vol / asks_vol

        # === OPEN INTEREST HIỆN TẠI (USD) ===
        oi_raw = exchange.fetch_open_interest(symbol)
        oi_contracts = float(oi_raw.get('openInterest', 0))
        price = ticker.get('last', 0.0)
        oi_usd = oi_contracts * price

        # === TAKER FLOW ===
        info = ticker.get('info', {})
        taker_buy_quote = float(info.get('takerBuyQuoteVolume', 0))
        total_vol = float(ticker.get('quoteVolume', 0)) or 1.0
        taker_buy_pct = round((taker_buy_quote / total_vol) * 100, 1)
        flow_label = "TAKER BUYING MẠNH" if taker_buy_pct > 52 else \
                     "TAKER SELLING MẠNH" if taker_buy_pct < 48 else "NEUTRAL"

        # === OI CHANGE (1m/5m/15m/30m/1h) ===
        oi_changes = {}
        for tf in ['1m', '5m', '15m', '30m', '1h']:
            try:
                hist = exchange.fetch_open_interest_history(symbol, tf, limit=2)
                if len(hist) >= 2:
                    prev = float(hist[-2]['openInterest'])
                    curr = float(hist[-1]['openInterest'])
                    pct = round((curr - prev) / prev * 100, 2) if prev > 0 else 0.0
                    oi_changes[tf] = pct
                else:
                    oi_changes[tf] = 0.0
            except Exception:
                oi_changes[tf] = 'N/A'

        # Funding, Vol, Deltas (giữ nguyên)
        high = ticker.get('high', 0.0)
        low = ticker.get('low', 0.0)
        volume = ticker.get('quoteVolume', 0.0)
        vol_idx = ((high - low) / price * 100) if price > 0 else 0.0

        funding_info = exchange.fetch_funding_rate(symbol)
        funding = funding_info.get('fundingRate', 0.0) * 100

        deltas = {}
        for tf in ['5m', '15m', '1h', '4h', '8h', '1d']:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=2)
                if len(ohlcv) >= 2:
                    deltas[tf] = round((ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4] * 100, 2)
                else:
                    deltas[tf] = 0.0
            except:
                deltas[tf] = 0.0

        return {
            'high': high, 'low': low, 'price': price,
            'volume': volume, 'imbalance': imbalance,
            'funding': funding, 'vol_idx': vol_idx,
            'deltas': deltas,
            'oi_usd': oi_usd,
            'taker_buy_pct': taker_buy_pct,
            'flow_label': flow_label,
            'oi_changes': oi_changes
        }

    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

# ================= REPORT =================
def generate_report(t_label: str):
    now_str = datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    report = f"""**🔥 BATTLEFIELD INTELLIGENCE REPORT v1.3 24/7**
[{t_label}] | Time: {now_str} VN
"""

    for asset in ['BTC', 'ETH']:
        sym = f"{asset}/USDT:USDT"
        data = get_asset_data(sym)
        if not data:
            report += f"{asset} - DATA FETCH FAILED\n"
            continue

        oi_delta_list = []
        for tf in ['1m', '5m', '15m', '30m', '1h']:
            val = data['oi_changes'][tf]
            if isinstance(val, str):
                oi_delta_list.append(f"{tf}:{val}")
            else:
                oi_delta_list.append(f"{tf}:{val:+.2f}%")
        oi_delta_str = " | ".join(oi_delta_list)

        line = (
            f"{asset} - High: {data['high']:,.2f} - Low: {data['low']:,.2f} - Current: {data['price']:,.2f} | "
            f"Vol: {data['volume']:,.0f} USDT | "
            f"Funding: {data['funding']:.4f}% | "
            f"Volatility Index: {data['vol_idx']:.2f}% | "
            f"Buy/Sell Pressure: {data['imbalance']:.2f}x | "
            f"**OI: {data['oi_usd']:,.0f} USD** | "
            f"**Taker Flow: {data['taker_buy_pct']:.1f}% ({data['flow_label']})** | "
            f"**OI Δ: {oi_delta_str}** | "
            f"Momentum: 5m: {data['deltas']['5m']:.2f}% | 15m: {data['deltas']['15m']:.2f}% | "
            f"1h: {data['deltas']['1h']:.2f}% | 4h: {data['deltas']['4h']:.2f}% | "
            f"8h: {data['deltas']['8h']:.2f}% | 1d: {data['deltas']['1d']:.2f}%"
        )
        report += line + "\n"

    report += "\n*ccxt • 24/7 realtime • OI + Taker Flow • Ready for Grok/ChatGPT*"

    print(report)
    send_telegram(report)

# ================= SCHEDULER 24/7 =================
sched = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")

# 12 thời điểm countdown gốc (giữ nguyên)
report_times = [
    (7,0,"60m"), (7,30,"30m"), (7,45,"15m"), (7,55,"5m"),
    (15,0,"60m"), (15,30,"30m"), (15,45,"15m"), (15,55,"5m"),
    (19,30,"60m"), (20,0,"30m"), (20,15,"15m"), (20,25,"5m")
]

# Bạn có thể uncomment phần dưới để thêm báo cáo mỗi giờ (full 24/7 hourly)
# for h in range(24):
#     report_times.append((h, 0, "Hourly"))

for hour, minute, countdown in report_times:
    if countdown == "Hourly":
        t_label = f"Hourly 24/7 Report"
    else:
        t_label = f"T-{countdown} Report"
    sched.add_job(generate_report, 'cron', hour=hour, minute=minute,
                  args=[t_label], id=f"battlefield_{hour}_{minute}")

print("✅ Scheduler 24/7 đã chạy (báo cáo tự động trước session)")
print("Nhấn Ctrl+C để dừng")
print("Để chạy background 24/7 thật sự: dùng screen/tmux hoặc systemd")

if __name__ == "__main__":
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nBot dừng an toàn")
