import ccxt
import pandas as pd
import time
import requests

print("FINAL HYBRID BOT STARTING...")

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
    'options': {'defaultType': 'swap'}
})

# ====== COINS ======
symbols = [
"BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT","XRP/USDT:USDT","DOGE/USDT:USDT",
"BNB/USDT:USDT","ADA/USDT:USDT","AVAX/USDT:USDT","LINK/USDT:USDT","MATIC/USDT:USDT",
"APT/USDT:USDT","ARB/USDT:USDT","OP/USDT:USDT","SUI/USDT:USDT","INJ/USDT:USDT",
"RNDR/USDT:USDT","FTM/USDT:USDT","NEAR/USDT:USDT","GALA/USDT:USDT","ATOM/USDT:USDT",
"LTC/USDT:USDT","ETC/USDT:USDT","FIL/USDT:USDT","AAVE/USDT:USDT","DYDX/USDT:USDT",
"GMX/USDT:USDT","SNX/USDT:USDT","UNI/USDT:USDT","SAND/USDT:USDT","APE/USDT:USDT",
"TRX/USDT:USDT","EOS/USDT:USDT","PEPE/USDT:USDT","SHIB/USDT:USDT","CRV/USDT:USDT",
"BLUR/USDT:USDT","SEI/USDT:USDT","ORDI/USDT:USDT","STX/USDT:USDT","FLOW/USDT:USDT"
]

# ====== SETTINGS ======
USD_SIZE = 7
LEVERAGE = 10

SL_PERCENT = 0.02
TP1_PERCENT = 0.04
TP2_PERCENT = 0.07

COOLDOWN = 60 * 30
last_trade_time = 0

positions = []

# ====== HELPERS ======
def get_price(symbol):
    try:
        return exchange.fetch_ticker(symbol)["last"]
    except:
        return None

def set_leverage(symbol):
    try:
        exchange.set_leverage(LEVERAGE, symbol)
    except:
        pass

def size(symbol):
    price = get_price(symbol)
    if price is None:
        return 0
    return max(round((USD_SIZE * LEVERAGE) / price, 4), 0.001)

def get_data(symbol, tf):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=100)
        return pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
    except:
        return None

# ====== FILTERS ======
def news_spike(df):
    last = df.iloc[-1]
    move = abs(last["c"] - last["o"]) / last["o"]
    return move > 0.02

# ====== LOGIC ======
def trend(df):
    ma = df["c"].rolling(20).mean()
    return "bullish" if df["c"].iloc[-1] > ma.iloc[-1] else "bearish"

def sweep(df):
    if df["l"].iloc[-1] < df["l"].iloc[-10:-1].min():
        return "low"
    if df["h"].iloc[-1] > df["h"].iloc[-10:-1].max():
        return "high"
    return None

def bos(df):
    if df["c"].iloc[-1] > df["h"].iloc[-2]:
        return "bullish"
    if df["c"].iloc[-1] < df["l"].iloc[-2]:
        return "bearish"
    return None

def fvg(df):
    for i in range(len(df)-3):
        if df["l"].iloc[i+2] > df["h"].iloc[i]:
            return "bullish"
        if df["h"].iloc[i+2] < df["l"].iloc[i]:
            return "bearish"
    return None

# ====== SCORING ======
def score_setup(df5, df15, df1h):
    score = 0

    t5 = trend(df5)
    t15 = trend(df15)
    t1h = trend(df1h)

    if t5 == t15 == t1h:
        score += 25

    if sweep(df5):
        score += 20

    if bos(df5):
        score += 20

    if fvg(df5):
        score += 15

    momentum = abs(df5["c"].iloc[-1] - df5["c"].iloc[-5])
    if momentum > 0:
        score += 10

    return score, t5

# ====== EXECUTION ======
def execute_trade(symbol, side):
    global last_trade_time

    if time.time() - last_trade_time < COOLDOWN:
        return

    set_leverage(symbol)
    price = get_price(symbol)
    qty = size(symbol)

    if price is None or qty == 0:
        return

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
        "trail_active": False
    })

    last_trade_time = time.time()

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
            df5 = get_data(sym, "5m")
            df15 = get_data(sym, "15m")
            df1h = get_data(sym, "1h")

            if df5 is None or df15 is None or df1h is None:
                continue

            if news_spike(df5):
                print(sym, "SKIP: spike")
                continue

            score, trend_dir = score_setup(df5, df15, df1h)

            print(sym, "Score:", score)

            if score >= 55:
                if trend_dir == "bullish":
                    execute_trade(sym, "LONG")
                elif trend_dir == "bearish":
                    execute_trade(sym, "SHORT")

        except Exception as e:
            print(sym, "ERR", e)

    for p in positions[:]:
        try:
            price = get_price(p["symbol"])
            df = get_data(p["symbol"], "5m")

            if df is None or price is None:
                continue

            if p["side"] == "LONG":
                if not p["tp1_hit"] and price >= p["tp1"]:
                    exchange.create_market_sell_order(p["symbol"], p["qty"]/2)
                    p["tp1_hit"] = True
                    p["sl"] = p["entry"]
                    p["trail_active"] = True
                    send_telegram(f"✅ TP1 {p['symbol']}")

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
                    send_telegram(f"✅ TP1 {p['symbol']}")

                if p["trail_active"]:
                    p["sl"] = min(p["sl"], price * 1.01)

                if price <= p["tp2"] or price >= p["sl"]:
                    close_trade(p)
                    positions.remove(p)

        except Exception as e:
            print("Monitor error:", e)

    time.sleep(60)
