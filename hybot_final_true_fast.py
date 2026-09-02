import os, requests, datetime, asyncio, logging, threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.request import HTTPXRequest
from collections import defaultdict

TELEGRAM_TOKEN = "7526393717:AAGX5efyXkmIgC2LEM3c3VazzUBVa3YgMd4"
CHAT_ID = "1239624540"

API_KEY = "dtYSGe1tCktjVZsyaaHTJs2iuJt99BBjnCgAHC03dJ4By7dEeG31JAB88bc36GeQ"
SECRET_KEY = "kQPqTY1udXGOLUYbAo14hqBlNr8Lknhnzny49ohb6RDjLVlUQfWdfpYaeVppzqHL"
BASE_URL = "https://testnet.binance.vision"

coin_show_counts = defaultdict(int)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Önbellekleme (Cache) yapmayan özel HTTP sunucusu
class NoCacheHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        super().end_headers()

def run_web_server():
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, NoCacheHTTPRequestHandler)
    print("🌐 Termux Önbelleksiz Web Paneli Yayında: http://localhost:8080")
    httpd.serve_forever()

def get_all_usdt_symbols():
    try:
        url = f"{BASE_URL}/api/v3/ticker/24hr"
        r = requests.get(url, timeout=10).json()
        if not isinstance(r, list):
            return ["BTCUSDT", "ETHUSDT"]
        valid_items = [
            x["symbol"] for x in r 
            if x.get("symbol", "").endswith("USDT") 
            and not any(sub in x.get("symbol", "") for sub in ["DOWN", "UP", "BULL", "BEAR"])
        ]
        return valid_items
    except Exception as e:
        logger.error(f"Semboller alınamadı: {e}")
        return ["BTCUSDT", "ETHUSDT"]

def get_ohlcv(symbol, interval="1h", limit=250):
    url = f"{BASE_URL}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=5).json()
        if not data or not isinstance(data, list) or "code" in data:
            return None
        closes = [float(row[4]) for row in data]
        highs = [float(row[2]) for row in data]
        lows = [float(row[3]) for row in data]
        return {"close": closes, "high": highs, "low": lows}
    except Exception:
        return None

def analyze(symbol):
    df = get_ohlcv(symbol, "1h", 200)
    if not df or len(df["close"]) < 50:
        return None
    
    closes = df["close"]
    ema50 = sum(closes[-50:]) / 50
    ema200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else sum(closes) / len(closes)
    
    gains, losses = 0, 0
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0: gains += diff
        else: losses += abs(diff)
    rsi = 50 if losses == 0 else 100 - (100 / (1 + (gains / losses)))

    # Filtre kriterleri esnetildi: Daha fazla sinyal yakalaması sağlandı
    if ema50 >= ema200 * 0.995 and rsi > 40:
        pos = "LONG"
    elif ema50 < ema200 * 1.005 and rsi < 60:
        pos = "SHORT"
    else:
        return None

    price = closes[-1]
    tp1 = round(price * 1.015 if pos == "LONG" else price * 0.985, 6)
    tp2 = round(price * 1.03 if pos == "LONG" else price * 0.97, 6)
    tp3 = round(price * 1.045 if pos == "LONG" else price * 0.955, 6)
    sl = round(price * 0.985 if pos == "LONG" else price * 1.015, 6)

    confidence = round(70 + (abs(rsi - 50) * 0.6), 2)
    if confidence > 95: confidence = 95

    shown = coin_show_counts[symbol]
    if shown >= 5:
        return None
    coin_show_counts[symbol] = shown + 1

    return {
        "symbol": symbol,
        "price": price,
        "confidence": confidence,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "sl": sl, "pos": pos,
        "shown": coin_show_counts[symbol],
        "rsi": round(rsi, 2),
        "ema50": round(ema50, 4),
        "ema200": round(ema200, 4)
    }

def format_message(d):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    renk = "🟢" if d["confidence"] >= 80 else "🟡"
    msg = f"""
🧪 *HYBOT AI Testnet Filtrelenmiş Sinyal*

📌 *Sembol:* `{d['symbol']}` – Gösterim: {d['shown']}/5  
🕒 *Tarih:* {now}  
💰 *Testnet Fiyat:* `{d['price']}` USDT  
📊 *Pozisyon:* {'📈 *LONG*' if d['pos']=='LONG' else '📉 *SHORT*'}  
🎯 *Güven Skoru:* {renk} %{d['confidence']}

---
### 🎯 Testnet TP & SL Hedefleri:
• TP1: `{d['tp1']}`  
• TP2: `{d['tp2']}`  
• TP3: `{d['tp3']}`  
💣 SL: `{d['sl']}`

---
### 📈 Teknik Göstergeler (Esnetilmiş Filtre):
• EMA50: {d['ema50']} | EMA200: {d['ema200']}  
• RSI: {d['rsi']}  

🔗 [📊 Testnet TradingView](https://www.tradingview.com/chart/?symbol=BINANCE:{d['symbol']})  
📬 *İletişim:* caner-doner@hotmail.com
"""
    return msg

async def send_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Testnet üzerindeki **tüm USDT çiftleri** esnetilmiş filtrelerle taranıyor...")
    symbols = get_all_usdt_symbols()
    found_count = 0
    for s in symbols:
        d = analyze(s)
        if d:
            msg = format_message(d)
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Favori", callback_data=f"fav_{d['symbol']}")]])
            await update.message.reply_text(text=msg, parse_mode="Markdown", reply_markup=keyboard)
            found_count += 1
            if found_count >= 3:
                break
    if found_count == 0:
        await update.message.reply_text("❌ Testnet havuzunda bu turda sinyal yakalanamadı, tekrar deneyin.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📈 Tüm Piyasayı Tara ve Sinyal Al", callback_data='analiz')],
        [InlineKeyboardButton("ℹ️ Yardım", callback_data='yardim')]
    ]
    await update.message.reply_text("👋 *HYBOT AI Termux Testnet Moduna Hoş Geldin!*\nAşağıdaki butona basarak taramayı başlatabilirsin:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "analiz":
        await send_signal(update, context)
    elif data == "yardim":
        await query.message.reply_text(
            "ℹ️ *HYBOT AI Yardım Menüsü (Testnet)*\n\n"
            "• /start – Bot menüsünü açar\n"
            "• /analiz – Tüm USDT paritelerini tarayıp sinyalleri listeler",
            parse_mode="Markdown"
        )
    elif data.startswith("fav_"):
        symbol = data.split("_")[1]
        await query.message.reply_text(f"⭐ `{symbol}` favorilere eklendi.", parse_mode="Markdown")

if __name__ == "__main__":
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()

    request_client = HTTPXRequest(read_timeout=30.0, write_timeout=30.0, connect_timeout=30.0, pool_timeout=30.0)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request_client).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analiz", send_signal))
    app.add_handler(CallbackQueryHandler(callback))
    print("✅ HYBOT Binance Testnet Tam Tarama ve Önbelleksiz Web Paneli Aktif!")
    app.run_polling()
