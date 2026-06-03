import ccxt
import pandas as pd
import time
import requests
import os

print("FINAL BULLETPROOF BOT RUNNING")

# ===== ENV =====
api_key = os.getenv("API_KEY")
secret = os.getenv("API_SECRET")
TG = os.getenv("TG_TOKEN")
CHAT = os.getenv("CHAT_ID")

def tg(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG}/sendMessage",
            data={"chat_id": CHAT, "text": msg}
        )
    except:
        pass

exchange = ccxt.mexc({
    'apiKey': api_key,
    'secret': secret,
    'options': {'defaultType': 'swap'}
})

SL_P = 0.02
COOLDOWN = 3600

positions = []

# ===== COOLDOWN =====
def load_cd():
    try:
        return float(open("cd.txt").read())
    except:
        return 0

def save_cd(t):
    open("cd.txt", "w").write(str(t))

last_trade = load_cd()

# ===== HELPERS =====
def price(sym):
    try:
        return exchange.fetch_ticker(sym)["last"]
    except:
        return None

def open_positions():
    try:
        return [p for p in exchange.fetch_positions() if float(p['contracts']) > 0]
    except:
        return []

# ===== SIZE (HARD FIX) =====
def size(sym):
    try:
        p = price(sym)

        qty = 10 / p  # target $10
        qty = float(exchange.amount_to_precision(sym, qty))

        real = qty * p
        print(sym, "SIZE:", round(real, 2))

        if real < 9:
            print("BLOCKED SMALL SIZE")
            return 0

        return qty

    except Exception as e:
        print("SIZE ERROR:", e)
        return 0

# ===== DATA =====
def data(sym, tf):
    try:
        ohlcv = exchange.fetch_ohlcv(sym, tf, limit=100)
        return pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])
    except:
        return None

# ===== FILTERS =====
def news(df):
    last = df.iloc[-1]
    return abs(last["c"] - last["o"]) / last["o"] > 0.02

def wick(df):
    last = df.iloc[-1]
    return (last["h"] - last["l"]) / last["l"] > 0.03

# ===== LOGIC =====
def trend(df):
    ma = df["c"].rolling(20).mean()
    return "bull" if df["c"].iloc[-1] > ma.iloc[-1] else "bear"

def sweep(df):
    return df["l"].iloc[-1] < df["l"].iloc[-10:-1].min() or df["h"].iloc[-1] > df["h"].iloc[-10:-1].max()

def bos(df):
    return df["c"].iloc[-1] > df["h"].iloc[-2] or df["c"].iloc[-1] < df["l"].iloc[-2]

def fvg(df):
    for i in range(len(df)-3):
        if df["l"].iloc[i+2] > df["h"].iloc[i] or df["h"].iloc[i+2] < df["l"].iloc[i]:
            return True
    return False

def score(df5, df15, df1h):
    s = 0
    if trend(df5) == trend(df15) == trend(df1h): s += 25
    if sweep(df5): s += 20
    if bos(df5): s += 20
    if fvg(df5): s += 15
    if abs(df5["c"].iloc[-1] - df5["c"].iloc[-5]) > 0: s += 10
    return s, trend(df5)

# ===== EXECUTE =====
def execute(sym, side):
    global last_trade

    if len(open_positions()) >= 2:
        print("MAX POSITIONS")
        return

    if time.time() - last_trade < COOLDOWN:
        print("COOLDOWN")
        return

    qty = size(sym)
    if qty == 0:
        return

    p = price(sym)

    if side == "LONG":
        sl = p * (1 - SL_P)
        tp1 = p * (1 + 2*SL_P)
        tp2 = p * (1 + 3.5*SL_P)
        close = "sell"
    else:
        sl = p * (1 + SL_P)
        tp1 = p * (1 - 2*SL_P)
        tp2 = p * (1 - 3.5*SL_P)
        close = "buy"

    try:
        # OPEN
        if side == "LONG":
            exchange.create_market_buy_order(sym, qty)
        else:
            exchange.create_market_sell_order(sym, qty)

        time.sleep(1)

        # TP1
        tp1_order = exchange.create_order(
            sym, "limit", close, qty/2, tp1, {"reduceOnly": True}
        )

        # TP2
        tp2_order = exchange.create_order(
            sym, "limit", close, qty/2, tp2, {"reduceOnly": True}
        )

        # SL
        sl_order = exchange.create_order(
            sym,
            "market",
            close,
            qty,
            None,
            {
                "stopPrice": sl,
                "triggerPrice": sl,
                "reduceOnly": True
            }
        )

        print("TP + SL SET")

    except Exception as e:
        print("FAIL → FORCE CLOSE:", e)

        try:
            if side == "LONG":
                exchange.create_market_sell_order(sym, qty)
            else:
                exchange.create_market_buy_order(sym, qty)
        except:
            pass

        return

    # FINAL SAFETY
    if not tp1_order or not tp2_order or not sl_order:
        print("MISSING SL/TP → CLOSE")

        try:
            if side == "LONG":
                exchange.create_market_sell_order(sym, qty)
            else:
                exchange.create_market_buy_order(sym, qty)
        except:
            pass

        return

    last_trade = time.time()
    save_cd(last_trade)

    tg(f"{sym} {side} OPEN\nSL + TP ACTIVE")

# ===== SYMBOLS =====
symbols = [
"BTC/USDT:USDT","ETH/USDT:USDT","XRP/USDT:USDT","DOGE/USDT:USDT","ADA/USDT:USDT",
"TRX/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","LINK/USDT:USDT","APT/USDT:USDT",
"ARB/USDT:USDT","OP/USDT:USDT","SUI/USDT:USDT","INJ/USDT:USDT","NEAR/USDT:USDT",
"ATOM/USDT:USDT","LTC/USDT:USDT","ETC/USDT:USDT","DYDX/USDT:USDT","UNI/USDT:USDT",
"SAND/USDT:USDT","APE/USDT:USDT","PEPE/USDT:USDT","SHIB/USDT:USDT","POL/USDT:USDT"
]

# ===== MAIN LOOP =====
while True:
    best = None
    best_score = 0
    best_side = None

    for sym in symbols:
        df5 = data(sym, "5m")
        df15 = data(sym, "15m")
        df1h = data(sym, "1h")

        if df5 is None or df15 is None or df1h is None:
            continue

        if news(df5) or wick(df5):
            continue

        s, t = score(df5, df15, df1h)
        perc = (s / 90) * 100

        if perc >= 75 and perc > best_score:
            best = sym
            best_score = perc
            best_side = "LONG" if t == "bull" else "SHORT"

    if best and best_score >= 75:
        print("BEST:", best)
        execute(best, best_side)

    time.sleep(60)
