
import requests
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

TELEGRAM_TOKEN = "7534683921:AAHVRAJpK6_gA-48kAcD_dz8ChYFeaaEF8o"
TELEGRAM_CHAT_ID = "923087333"

SYMBOLS = {
    "ethereum": "ETHUSDT",
    "bitcoin": "BTCUSDT",
    "neo": "NEOUSDT",
    "ripple": "XRPUSDT"
}

TP_LEVELS = [1.0, 1.5, 2.0, 2.5, 3.0]
TP_RECOMMENDATIONS = {
    1: "Pozisyonun %20’sini kapat.",
    2: "Pozisyonun %40’ını kapat.",
    3: "Pozisyonun %60’ını kapat.",
    4: "Pozisyonun %80’ini kapat.",
    5: "Tüm pozisyonu kapat."
}

last_signals = {}

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=data)

def send_telegram_photo(image_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    files = {"photo": open(image_path, "rb")}
    data = {"chat_id": TELEGRAM_CHAT_ID}
    requests.post(url, files=files, data=data)

def get_prices(symbol="ETHUSDT", interval="1h", limit=100):
    url = f"https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params)
    data = r.json()
    return [float(k[4]) for k in data]

def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period).mean().iloc[-1]

def calculate_rsi(prices, period=14):
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = pd.Series(gains).rolling(window=period).mean().iloc[-1]
    avg_loss = pd.Series(losses).rolling(window=period).mean().iloc[-1]
    rs = avg_gain / avg_loss if avg_loss != 0 else 0.001
    return 100 - (100 / (1 + rs))

def calculate_macd(prices):
    short_ema = pd.Series(prices).ewm(span=12).mean()
    long_ema = pd.Series(prices).ewm(span=26).mean()
    macd_line = short_ema - long_ema
    signal_line = macd_line.ewm(span=9).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1], macd_line.iloc[-1] - signal_line.iloc[-1]

def calculate_atr(prices, period=14):
    return pd.Series([abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]).rolling(window=period).mean().iloc[-1]

def suggest_leverage(rsi, trend_strength, volatility):
    score = 0
    score += 3 if trend_strength > 1.5 else 2 if trend_strength > 0.5 else 1
    score += 3 if 30 < rsi < 60 else 2 if 20 < rsi <= 30 or 60 <= rsi < 70 else 1
    score += 3 if volatility < 1.5 else 2 if volatility < 2.5 else 1
    if score >= 8: return "10x", score
    elif score >= 6: return "5x", score
    else: return "2x", score

def draw_chart(prices, ema50, ema200, tps, stop, price, symbol):
    plt.figure(figsize=(10, 5))
    plt.plot(prices, label="Fiyat", color="black")
    plt.axhline(ema50, label="EMA50", linestyle="--", color="blue")
    plt.axhline(ema200, label="EMA200", linestyle="--", color="red")
    plt.axhline(stop, label="Stop", color="gray")
    for i, tp in enumerate(tps):
        plt.axhline(tp, linestyle=":", label=f"TP{i+1}", color="green")
    plt.axhline(price, label="Giriş", color="orange")
    plt.title(f"{symbol} Teknik Grafik")
    plt.legend()
    plt.tight_layout()
    plt.savefig("chart.png")
    plt.close()
    send_telegram_photo("chart.png")

def analyze_and_signal(symbol_key, symbol_label):
    prices = get_prices(symbol_key)
    if len(prices) < 60: return
    price = round(prices[-1], 4)
    ema50 = calculate_ema(prices, 50)
    ema200 = calculate_ema(prices, 200)
    rsi = calculate_rsi(prices)
    atr = calculate_atr(prices)
    macd, _, _ = calculate_macd(prices)
    volatility = np.std(prices)
    trend_strength = (prices[-1] - prices[0]) / prices[0] * 100
    leverage, confidence = suggest_leverage(rsi, trend_strength, volatility)
    trend = "YUKARI" if ema50 > ema200 else "AŞAĞI"
    signal = None
    if trend == "YUKARI" and rsi < 35: signal = "LONG"
    elif trend == "AŞAĞI" and rsi > 65: signal = "SHORT"
    if signal:
        stop = round(price - atr if signal == "LONG" else price + atr, 4)
        tp_list = [round(price + atr * level, 4) if signal == "LONG" else round(price - atr * level, 4) for level in TP_LEVELS]
        last_signals[symbol_label] = {"tps": tp_list, "notified": [False]*5, "type": signal}
        msg = f"[SİNYAL] {symbol_label} - {signal}\nFiyat: {price}\nTrend: {trend}\nRSI: {round(rsi,2)}\nMACD: {round(macd,2)}\nATR: {round(atr,2)}\nEMA50: {round(ema50,2)}\nEMA200: {round(ema200,2)}\nKaldıraç: {leverage} ({confidence}/9)\nStop: {stop}\n" + '\n'.join([f"TP{i+1}: {tp}" for i, tp in enumerate(tp_list)])
        send_telegram_message(msg)
        draw_chart(prices, ema50, ema200, tp_list, stop, price, symbol_label)

def check_tp_hits():
    for symbol, data in last_signals.items():
        current_price = get_prices([k for k,v in SYMBOLS.items() if v == symbol][0])[-1]
        for i, tp in enumerate(data["tps"]):
            if not data["notified"][i]:
                if (data["type"] == "LONG" and current_price >= tp) or (data["type"] == "SHORT" and current_price <= tp):
                    send_telegram_message(f"[TP{i+1} HİT] {symbol}: {tp} hedefi ulaşıldı. {TP_RECOMMENDATIONS[i+1]}")
                    data["notified"][i] = True

print("Ultra Ultimate bot çalışıyor...")
while True:
    try:
        for key, label in SYMBOLS.items():
            analyze_and_signal(key, label)
            time.sleep(2)
        check_tp_hits()
        time.sleep(90)
    except Exception as e:
        print("HATA:", e)
        time.sleep(60)
