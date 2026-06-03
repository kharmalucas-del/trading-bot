import ccxt

import pandas as pd

import time

import requests

import os

print("FINAL SAFE BOT RUNNING")

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

# ===== SETTINGS =====

SL_P = 0.02

COOLDOWN = 3600

positions = []

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

# 🔥 FIXED SIZE (NO MORE 0.08$ TRADES)

def size(sym):

    try:

        p = price(sym)

        market = exchange.market(sym)

        usd_value = 10  # TARGET POSITION

        qty = usd_value / p

        min_qty = market['limits']['amount']['min'] or 0

        qty = max(qty, min_qty)

        qty = float(exchange.amount_to_precision(sym, qty))

        if qty * p < 5:

            print("SIZE TOO SMALL SKIP")

            return 0

        print("SIZE:", round(qty * p, 2))

        return qty

    except Exception as e:

        print("SIZE ERROR:", e)

        return 0

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

# ===== EXECUTE (SAFE) =====

def execute(sym, side):

    global last_trade

    if len(open_positions()) >= 2:

        print("MAX POSITIONS")

        return

    for p in positions:

        if p["symbol"] == sym:

            return

    if time.time() - last_trade < COOLDOWN:

        print("COOLDOWN")

        return

    qty = size(sym)

    p = price(sym)

    if qty == 0 or p is None:

        return

    try:

        if side == "LONG":

            exchange.create_market_buy_order(sym, qty)

            sl = p * (1 - SL_P)

            tp1 = p * (1 + 2*SL_P)

            tp2 = p * (1 + 3.5*SL_P)

        else:

            exchange.create_market_sell_order(sym, qty)

            sl = p * (1 + SL_P)

            tp1 = p * (1 - 2*SL_P)

            tp2 = p * (1 - 3.5*SL_P)

        print("TRADE OPENED")

    except Exception as e:

        print("ORDER FAILED:", e)

        return

    positions.append({

        "symbol": sym,

        "side": side,

        "qty": qty,

        "entry": p,

        "sl": sl,

        "tp1": tp1,

        "tp2": tp2,

        "tp1_hit": False

    })

    last_trade = time.time()

    save_cd(last_trade)

    tg(f"{sym} {side} OPEN\nSL/TP ACTIVE")

# ===== MANAGE =====

def manage():

    for p in positions[:]:

        pr = price(p["symbol"])

        if pr is None:

            continue

        if p["side"] == "LONG":

            if not p["tp1_hit"] and pr >= p["tp1"]:

                exchange.create_market_sell_order(p["symbol"], p["qty"]/2)

                p["tp1_hit"] = True

                p["sl"] = p["entry"]

                tg(f"TP1 {p['symbol']}")

            if p["tp1_hit"]:

                p["sl"] = max(p["sl"], pr * 0.99)

            if pr >= p["tp2"] or pr <= p["sl"]:

                exchange.create_market_sell_order(p["symbol"], p["qty"])

                positions.remove(p)

                tg(f"CLOSED {p['symbol']}")

        else:

            if not p["tp1_hit"] and pr <= p["tp1"]:

                exchange.create_market_buy_order(p["symbol"], p["qty"]/2)

                p["tp1_hit"] = True

                p["sl"] = p["entry"]

                tg(f"TP1 {p['symbol']}")

            if p["tp1_hit"]:

                p["sl"] = min(p["sl"], pr * 1.01)

            if pr <= p["tp2"] or pr >= p["sl"]:

                exchange.create_market_buy_order(p["symbol"], p["qty"])

                positions.remove(p)

                tg(f"CLOSED {p['symbol']}")

# ===== COINS =====

symbols = [

"BTC/USDT:USDT","ETH/USDT:USDT","XRP/USDT:USDT","DOGE/USDT:USDT","ADA/USDT:USDT",

"TRX/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","LINK/USDT:USDT","APT/USDT:USDT",

"ARB/USDT:USDT","OP/USDT:USDT","SUI/USDT:USDT","INJ/USDT:USDT","NEAR/USDT:USDT",

"ATOM/USDT:USDT","LTC/USDT:USDT","ETC/USDT:USDT","DYDX/USDT:USDT","UNI/USDT:USDT",

"SAND/USDT:USDT","APE/USDT:USDT","PEPE/USDT:USDT","SHIB/USDT:USDT","POL/USDT:USDT"

]

# ===== MAIN LOOP =====

while True:

    print("SCANNING")

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

    if best:

        print("BEST:", best)

        execute(best, best_side)

    manage()

    time.sleep(60)
