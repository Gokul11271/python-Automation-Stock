#!/usr/bin/env python3
import MetaTrader5 as mt5
import time
from datetime import datetime

# ---------------- CONFIG ---------------- #
SYMBOL = "XAUUSD"
SLIPPAGE = 500
MAGIC = 12345
POLL_INTERVAL = 0.1
FIXED_PROFIT = 5.0

BUY_PRICE = None
SELL_PRICE = None

buy_volume = 0.01
sell_volume = 0.02

last_action = None

# ---------------- INIT ---------------- #
if not mt5.initialize():
    print("❌ MT5 init failed:", mt5.last_error())
    quit()

print("✅ MT5 Connected")
mt5.symbol_select(SYMBOL, True)

while not mt5.symbol_info_tick(SYMBOL):
    time.sleep(0.05)

# ---------------- HELPERS ---------------- #
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def get_profit():
    acc = mt5.account_info()
    return acc.profit if acc else 0.0

# ---------------- FORCE MARKET ORDER ---------------- #
def force_order(order_type, volume, target_price):
    while True:
        tick = mt5.symbol_info_tick(SYMBOL)

        price = tick.ask if order_type == "BUY" else tick.bid

        result = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": SLIPPAGE,
            "magic": MAGIC,
            "comment": f"FORCED {order_type} @ {target_price}",
        })

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"✅ {order_type} EXECUTED (target {target_price}) actual {price} vol={volume}")
            return True

        time.sleep(0.05)

# ---------------- CLOSE ---------------- #
def close_all():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for pos in positions:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(SYMBOL).bid if pos.type == 0 else mt5.symbol_info_tick(SYMBOL).ask

            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": SLIPPAGE,
            })

    log("💰 ALL CLOSED")

# ---------------- MAIN ---------------- #
def run():
    global BUY_PRICE, SELL_PRICE, last_action, buy_volume, sell_volume

    log("🚀 STRICT STATIC FORCE BOT")

    base_profit = get_profit()

    # 1️⃣ FIRST BUY
    force_order("BUY", buy_volume, "MARKET")

    tick = mt5.symbol_info_tick(SYMBOL)

    # 🔥 LOCK EXACT LEVELS
    BUY_PRICE = int(round(tick.ask))
    SELL_PRICE = BUY_PRICE - 1

    log(f"🔒 BUY  → {BUY_PRICE}")
    log(f"🔒 SELL → {SELL_PRICE}")

    last_action = "BUY"

    # 🔁 LOOP
    while True:
        tick = mt5.symbol_info_tick(SYMBOL)
        bid = tick.bid
        ask = tick.ask

        profit = get_profit() - base_profit
        print(f"\r📊 Profit: {profit:.2f}/{FIXED_PROFIT}", end="")

        if profit >= FIXED_PROFIT:
            print()
            log("🎯 TARGET HIT")
            close_all()
            return

        # 🔥 STRICT SELL
        if last_action == "BUY" and bid <= SELL_PRICE:
            sell_volume += 0.02
            if force_order("SELL", sell_volume, SELL_PRICE):
                last_action = "SELL"

        # 🔥 STRICT BUY
        elif last_action == "SELL" and ask >= BUY_PRICE:
            buy_volume += 0.02
            if force_order("BUY", buy_volume, BUY_PRICE):
                last_action = "BUY"

        time.sleep(POLL_INTERVAL)

# ---------------- RUN ---------------- #
try:
    run()
finally:
    mt5.shutdown()