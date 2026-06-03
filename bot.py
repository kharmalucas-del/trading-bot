import ccxt
import pandas as pd
import time
import requests

print("AI FILTER BOT STARTING...")

# ====== KEYS ======
api_key = "mx0vgld2XcJBQm9tff"
secret = "bb1b53bf127b474a90909fa83b81be8d"

# ====== TELEGRAM ======
TELEGRAM_TOKEN = "8881043666:AAFuqQPppcOv3BAQx-pZTJp2EkDzo7SPqxs"
CHAT_ID = "7157590486"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass

# ====== EXCHANGE ======
exchange = ccxt.mexc({
    'apiKey': api_key,
    'secret': secret,
    'options': {'defaultType': 'swap'},
    'urls': {
        'api': {
            'public': 'https://contract.mexc.com',
            'private': 'https://contract.mexc.com',
        }
    }
})

symbols = [
    "BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT",
    "XRP/USDT:USDT","DOGE/USDT:USDT","BNB/USDT:USDT",
    "ADA/USDT:USDT","AVAX/USDT:USDT","LINK/USDT:USDT",
    "MATIC/USDT:USDT","APT/USDT:USDT","ARB/USDT:USDT",
    "OP/USDT:USDT","SUI/USDT:USDT"
]

# ====== SETTINGS ======
USD_SIZE = 7
LEVERAGE = 10

SL_PERCENT = 0.02
TP1_PERCENT = 0.04
TP2_PERCENT = 0.07

COOLDOWN = 60 * 60 * 2
last_trade_time = 0

positions = []

# ====== HELPERS ======
def set_leverage(symbol):
    try:
        exchange.set_leverage(LEVERAGE, symbol)
    except:
        pass

def size(symbol):
    price = exchange.fetch_ticker(symbol)["last"]
    return round((USD_SIZE * LEVERAGE) / price, 6)

def get_data(symbol, tf):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=100)
        return pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])
    except:
        return None

# ====== AI FILTERS ======
def high_volatility(df):
    last = df.iloc[-1]
    move = abs(last["close"] - last["open"]) / last["open"]
    wick = (last["high"] - last["low"]) / last["low"]
    return move > 0.02 or wick > 0.03

def ranging_market(df):
    high = df["high"].iloc[-20:].max()
    low = df["low"].iloc[-20:].min()
    return (high - low) / low < 0.01

def strong_momentum(df):
    return abs(df["close"].iloc[-1] - df["close"].iloc[-5]) > 0

def strong_trend(df):
    ma = df["close"].rolling(20).mean()
    return abs(df["close"].iloc[-1] - ma.iloc[-1]) / ma.iloc[-1] > 0.002

# ====== LOGIC ======
def trend(df):
    ma = df["close"].rolling(20).mean()
    return "bullish" if df["close"].iloc[-1] > ma.iloc[-1] else "bearish"

def sweep(df):
    if df["low"].iloc[-1] < df["low"].iloc[-10:-1].min():
        return "sweep_low"
    if df["high"].iloc[-1] > df["high"].iloc[-10:-1].max():
        return "sweep_high"
    return None

def bos(df):
    if df["close"].iloc[-1] > df["high"].iloc[-2]:
        return "bullish"
    if df["close"].iloc[-1] < df["low"].iloc[-2]:
        return "bearish"
    return None

def fvg(df):
    for i in range(len(df)-3):
        if i+2 >= len(df):
            continue
        if df["low"].iloc[i+2] > df["high"].iloc[i]:
            return "bullish"
        if df["high"].iloc[i+2] < df["low"].iloc[i]:
            return "bearish"
    return None

# ====== SIGNAL ======
def signal(symbol):
    df = get_data(symbol, "5m")
    df_htf = get_data(symbol, "1h")

    if df is None or df_htf is None:
        return None

    # 🔥 AI FILTERS
    if high_volatility(df):
        print(symbol, "SKIP: volatility")
        return None

    if ranging_market(df):
        print(symbol, "SKIP: ranging")
        return None

    if not strong_momentum(df):
        print(symbol, "SKIP: no momentum")
        return None

    if not strong_trend(df_htf):
        print(symbol, "SKIP: weak trend")
        return None

    t1 = trend(df)
    t2 = trend(df_htf)
    s = sweep(df)
    b = bos(df)
    f = fvg(df)

    print(f"{symbol} → {t1} {t2} {s} {b} {f}")

    if t1 == "bullish" and t2 == "bullish":
        if s == "sweep_low" and (b == "bullish" or f == "bullish"):
            return "LONG"

    if t1 == "bearish" and t2 == "bearish":
        if s == "sweep_high" and (b == "bearish" or f == "bearish"):
            return "SHORT"

    return None

# ====== STRUCTURE BREAK ======
def structure_break(df, side):
    low = df["low"].iloc[-5:].min()
    high = df["high"].iloc[-5:].max()
    price = df["close"].iloc[-1]

    if side == "LONG" and price < low:
        return True
    if side == "SHORT" and price > high:
        return True

    return False

# ====== EXECUTION ======
def execute_trade(symbol, side):
    global last_trade_time

    now = time.time()
    if now - last_trade_time < COOLDOWN:
        return

    set_leverage(symbol)
    price = exchange.fetch_ticker(symbol)["last"]
    qty = size(symbol)

    if side == "LONG":
        exchange.create_market_buy_order(symbol, qty)
        sl = price * (1 - SL_PERCENT)
        tp1 = price * (1 + TP1_PERCENT)
        tp2 = price * (1 + TP2_PERCENT)
    else:
        exchange.create_market_sell_order(symbol, qty)
        sl = price * (1 + SL_PERCENT)
        tp1 = price * (1 - TP1_PERCENT)
        tp2 = price * (1 - TP2_PERCENT)

    positions.append({
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "entry": price,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp1_hit": False,
        "breakeven": False,
        "trail_active": False
    })

    last_trade_time = now

    send_telegram(f"🚀 OPEN {symbol} {side}")
    print("OPEN", symbol, side)

# ====== CLOSE ======
def close_trade(p):
    try:
        if p["side"] == "LONG":
            exchange.create_market_sell_order(p["symbol"], p["qty"])
        else:
            exchange.create_market_buy_order(p["symbol"], p["qty"])

        send_telegram(f"❌ CLOSED {p['symbol']}")
    except:
        pass

# ====== MAIN LOOP ======
while True:
    print("\n=== SCANNING ===")

    for sym in symbols:
        try:
            sig = signal(sym)
            if sig:
                execute_trade(sym, sig)
        except Exception as e:
            print(sym, "ERR", e)

    for p in positions[:]:
        try:
            price = exchange.fetch_ticker(p["symbol"])["last"]
            df = get_data(p["symbol"], "5m")

            if structure_break(df, p["side"]):
                send_telegram(f"⚠️ STRUCTURE BREAK {p['symbol']}")
                close_trade(p)
                positions.remove(p)
                continue

            if p["side"] == "LONG":
                if not p["tp1_hit"] and price >= p["tp1"]:
                    exchange.create_market_sell_order(p["symbol"], p["qty"]/2)
                    p["tp1_hit"] = True
                    p["sl"] = p["entry"]
                    p["trail_active"] = True
                    send_telegram(f"✅ TP1 + BE {p['symbol']}")

                if p["trail_active"]:
                    p["sl"] = max(p["sl"], price * 0.99)

                if price >= p["tp2"] or price <= p["sl"]:
                    close_trade(p)
                    positions.remove(p)

            else:
                if not p["tp1_hit"] and price <= p["tp1"]:
                    exchange.create_market_buy_order(p["symbol"], p["qty"]/2)
                    p["tp1_hit"] = True
                    p["sl"] = p["entry"]
                    p["trail_active"] = True
                    send_telegram(f"✅ TP1 + BE {p['symbol']}")

                if p["trail_active"]:
                    p["sl"] = min(p["sl"], price * 1.01)

                if price <= p["tp2"] or price >= p["sl"]:
                    close_trade(p)
                    positions.remove(p)

        except Exception as e:
            print("Monitor error:", e)

    time.sleep(60)
