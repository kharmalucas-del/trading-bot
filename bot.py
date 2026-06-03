import ccxt
import pandas as pd
import time
import requests
import os

print("FINAL SECURE BOT RUNNING...")

# ===== ENV (DO NOT HARDCODE KEYS) =====
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
USD_SIZE = 1        # ≈ $10 position
LEV = 10
SL_P = 0.02
COOLDOWN = 3600

positions = []

# ===== COOLDOWN STORAGE =====
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

def size(sym):
    p = price(sym)
    if not p:
        return 0

    qty = (USD_SIZE * LEV) / p

    try:
        qty = float(exchange.amount_to_precision(sym, qty))
    except:
        return 0

    # HARD SAFETY CAP (~$12 max position)
    if qty * p > 12:
        return 0

    return qty

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

    # MAX 2 POSITIONS
    if len(open_positions()) >= 2:
        return

    # PREVENT SAME COIN
    for p in positions:
        if p["symbol"] == sym:
            return

    # COOLDOWN
    if time.time() - last_trade < COOLDOWN:
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
            close = "sell"
        else:
            exchange.create_market_sell_order(sym, qty)
            sl = p * (1 + SL_P)
            tp1 = p * (1 - 2*SL_P)
            tp2 = p * (1 - 3.5*SL_P)
            close = "buy"

        # 🔥 MUST HAVE STOP LOSS
        exchange.create_order(sym, "stop_market", close, qty, None, {"stopPrice": sl})

    except Exception as e:
        print("ORDER FAILED:", e)
        last_trade = time.time()
        save_cd(last_trade)
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

    tg(f"{sym} {side}\nSL set\nTP1: {tp1}\nTP2: {tp2}")

# ===== MANAGE =====
def manage():
    for p in positions[:]:
        pr = price(p["symbol"])
        if pr is None:
            continue

        try:
            if p["side"] == "LONG":

                # TP1
                if not p["tp1_hit"] and pr >= p["tp1"]:
                    exchange.create_market_sell_order(p["symbol"], p["qty"]/2)
                    p["tp1_hit"] = True
                    p["sl"] = p["entry"]
                    tg(f"TP1 HIT {p['symbol']}")

                # TRAILING
                if p["tp1_hit"]:
                    new_sl = pr * 0.99
                    if new_sl > p["sl"]:
                        p["sl"] = new_sl

                # FINAL CLOSE
                if pr >= p["tp2"] or pr <= p["sl"]:
                    exchange.create_market_sell_order(p["symbol"], p["qty"])
                    positions.remove(p)
                    tg(f"CLOSED {p['symbol']}")

            else:

                # TP1
                if not p["tp1_hit"] and pr <= p["tp1"]:
                    exchange.create_market_buy_order(p["symbol"], p["qty"]/2)
                    p["tp1_hit"] = True
                    p["sl"] = p["entry"]
                    tg(f"TP1 HIT {p['symbol']}")

                # TRAILING
                if p["tp1_hit"]:
                    new_sl = pr * 1.01
                    if new_sl < p["sl"]:
                        p["sl"] = new_sl

                # FINAL CLOSE
                if pr <= p["tp2"] or pr >= p["sl"]:
                    exchange.create_market_buy_order(p["symbol"], p["qty"])
                    positions.remove(p)
                    tg(f"CLOSED {p['symbol']}")

        except Exception as e:
            print("MANAGE ERROR:", e)

# ===== 25 COINS =====
symbols = [
"BTC/USDT:USDT","ETH/USDT:USDT","XRP/USDT:USDT","DOGE/USDT:USDT","ADA/USDT:USDT",
"TRX/USDT:USDT","SOL/USDT:USDT","AVAX/USDT:USDT","LINK/USDT:USDT","APT/USDT:USDT",
"ARB/USDT:USDT","OP/USDT:USDT","SUI/USDT:USDT","INJ/USDT:USDT","NEAR/USDT:USDT",
"ATOM/USDT:USDT","LTC/USDT:USDT","ETC/USDT:USDT","DYDX/USDT:USDT","UNI/USDT:USDT",
"SAND/USDT:USDT","APE/USDT:USDT","PEPE/USDT:USDT","SHIB/USDT:USDT","MATIC/USDT:USDT"
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

    if best:
        execute(best, best_side)

    manage()

    time.sleep(60)
