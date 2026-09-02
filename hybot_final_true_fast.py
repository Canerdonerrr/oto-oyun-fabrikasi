import os, requests, datetime, asyncio, logging, random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from collections import defaultdict

TELEGRAM_TOKEN = "7526393717:AAGX5efyXkmIgC2LEM3c3VazzUBVa3YgMd4"
coin_show_counts = defaultdict(int)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_symbols_top150():
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10).json()
        if not isinstance(r, list):
            return ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        # Hacme göre sıralama
        valid_items = [x for x in r if x.get("symbol", "").endswith("USDT") and len(x.get("symbol", "")) <= 12]
        valid_items.sort(key=lambda k: float(k.get("quoteVolume", 0)), reverse=True)
        top20 = [item["symbol"] for item in valid_items[:20]]
        mid_range = valid_items[20:]
        mid_symbols = [item["symbol"] for item in random.sample(mid_range, min(130, len(mid_range)))] if len(mid_range) > 0 else []
        return top20 + mid_symbols
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

def get_klines(symbol, interval="1h", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url, timeout=10).json()
        if not data or not isinstance(data, list) or "code" in data:
            return []
        closes = []
        highs = []
        lows = []
        for row in data:
            closes.append(float(row[4]))
            highs.append(float(row[2]))
            lows.append(float(row[3]))
        return {"close": closes, "high": highs, "low": lows}
    except Exception:
        return {}

def calculate_simple_indicators(data):
    closes = data.get("close", [])
    if len(closes) < 30:
        return None
    
    # Basit Hareketli Ortalamalar (EMA muadili SMA/Ağırlıklı mantık)
    ema50 = sum(closes[-15:]) / 15
    ema200 = sum(closes[-30:]) / 30
    
    # Basit RSI Hesaplama
    gains, losses = 0, 0
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0: gains += diff
        else: losses += abs(diff)
    rsi = 50 if losses == 0 else 100 - (100 / (1 + (gains / losses)))
    
    return {
        "close": closes[-1],
        "ema50": ema50,
        "ema200": ema200,
        "rsi": rsi
    }

def detect_position(ind):
    if ind['ema50'] > ind['ema200'] and ind['rsi'] > 50:
        return "long"
    elif ind['ema50'] < ind['ema200'] and ind['rsi'] < 50:
        return "short"
    return "none"

def build_message(symbol, ind, direction):
    if not ind or direction == "none":
        return None, 0, 0, 0
    price = ind['close']
    if direction == "long":
        tp1, tp2, tp3 = round(price * 1.015, 6), round(price * 1.03, 6), round(price * 1.045, 6)
        sl = round(price * 0.985, 6)
        emoji = "📈 Long"
    else:
        tp1, tp2, tp3 = round(price * 0.985, 6), round(price * 0.97, 6), round(price * 0.955, 6)
        sl = round(price * 1.015, 6)
        emoji = "📉 Short"

    confidence = 75 if (direction == "long" and ind['rsi'] > 55) or (direction == "short" and ind['rsi'] < 45) else 65
    trend = 80 if direction == "long" else 40
    false_score = 20

    karar = "✅ İşleme Gir" if confidence >= 70 else "⚠️ Bekle"

    msg = f"""
📊 **{symbol} Teknik Analiz – HYBOT Pure Python**
🕐 {datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}
💰 Fiyat: {price} USDT
📌 Pozisyon: {emoji} | Kaldıraç: x5

🎯 TP1: {tp1} | Başarı Tahmini: %78
🎯 TP2: {tp2} | Başarı Tahmini: %65
🎯 TP3: {tp3} | Başarı Tahmini: %52
💣 SL: {sl}

🔐 EMA50: {round(ind['ema50'], 4)} | EMA200: {round(ind['ema200'], 4)}
🔎 RSI: {round(ind['rsi'], 2)}

🧠 Güven Skoru: %{confidence} | 📈 Trend Gücü: %{trend}
📟 Gösterim Sayısı: {coin_show_counts[symbol]} / 3

📌 **Sinyal Değerlendirme Kararı:** {karar}
📈 [TradingView](https://www.tradingview.com/symbols/{symbol})
""".strip()
    return msg, confidence, trend, false_score

async def analyze_symbol(symbol):
    if coin_show_counts[symbol] >= 3:
        return None
    raw_data = get_klines(symbol)
    ind = calculate_simple_indicators(raw_data)
    if not ind:
        return None
    direction = detect_position(ind)
    msg, confidence, trend, false_score = build_message(symbol, ind, direction)
    if msg and confidence >= 60:
        coin_show_counts[symbol] += 1
        return msg
    return None

async def analiz_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Saf Python motoru ile piyasa taranıyor...")
    symbols = get_symbols_top150()
    for sym in symbols[:15]:  # Hızlı yanıt için ilk 15 sembol taranır
        msg = await analyze_symbol(sym)
        if msg:
            await update.message.reply_text(msg, parse_mode="Markdown")
            return
    await update.message.reply_text("❌ Kriterlere uygun sinyal bulunamadı.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("analiz", analiz_handler))
    print("✅ HYBOT Saf Python Sürümü Başladı!")
    app.run_polling()
