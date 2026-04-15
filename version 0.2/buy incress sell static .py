#!/usr/bin/env python3
import MetaTrader5 as mt5
import time
from datetime import datetime

# ---------------- CONFIG ---------------- #
SYMBOL = "XAUUSD"
SLIPPAGE = 500
MAGIC = 12345
POLL_INTERVAL = 0.5

FIXED_PROFIT = 5.0   # 🎯 TARGET PROFIT

GAP_POINTS = 100
START_VOLUME = 0.01
VOLUME_STEP = 0.01

# 🔥 GLOBAL STATIC SELL PRICE
SELL_FIXED_PRICE = None

# ---------------- INIT ---------------- #
if not mt5.initialize():
    print("❌ MT5 init failed:", mt5.last_error())
    quit()

print("✅ MT5 Connected")

mt5.symbol_select(SYMBOL, True)
symbol = mt5.symbol_info(SYMBOL)
point = symbol.point
digits = symbol.digits

# ---------------- HELPERS ---------------- #
def now():
    return datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(f"[{now()}] {msg}")

def get_profit():
    acc = mt5.account_info()
    return acc.profit if acc else 0.0

# ---------------- PRICE ---------------- #
def get_buy_price(step):
    tick = mt5.symbol_info_tick(SYMBOL)
    return round(tick.ask + (step * GAP_POINTS * point), digits)

def get_sell_price():
    global SELL_FIXED_PRICE

    tick = mt5.symbol_info_tick(SYMBOL)
    symbol = mt5.symbol_info(SYMBOL)

    stop_level = symbol.trade_stops_level * symbol.point

    # 🔒 FIX SELL PRICE ONLY ONCE
    if SELL_FIXED_PRICE is None:
        SELL_FIXED_PRICE = round(
            tick.bid - stop_level - 20 * point,
            digits
        )
        log(f"🔒 SELL PRICE FIXED → {SELL_FIXED_PRICE}")

    return SELL_FIXED_PRICE

# ---------------- ROBUST ORDER ---------------- #
def place_order(order_type, price, volume):
    attempt = 0

    while True:  # 🔥 NEVER STOP
        attempt += 1

        tick = mt5.symbol_info_tick(SYMBOL)
        symbol = mt5.symbol_info(SYMBOL)

        if not tick or not symbol:
            log("⚠️ No market data → retrying...")
            time.sleep(1)
            continue

        stop_level = symbol.trade_stops_level * symbol.point

        # 🔥 AUTO FIX PRICE
        if order_type == "BUY":
            order_mt5 = mt5.ORDER_TYPE_BUY_STOP
            price = max(price, tick.ask + stop_level + 10 * point)
        else:
            order_mt5 = mt5.ORDER_TYPE_SELL_STOP
            price = min(price, tick.bid - stop_level - 10 * point)

        price = float(int(round(price)))

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": SYMBOL,
            "volume": volume,
            "type": order_mt5,
            "price": price,
            "deviation": SLIPPAGE,
            "magic": MAGIC,
            "comment": "Chain Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result is None:
            log(f"⚠️ Attempt {attempt}: None → {mt5.last_error()}")
            time.sleep(1)
            continue

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"✅ {order_type} placed @ {price} vol={volume} (attempt {attempt})")
            return True

        log(f"⚠️ Attempt {attempt}: retcode={result.retcode} → retrying...")
        time.sleep(1)

# ---------------- CLOSE ---------------- #
def close_all():
    global SELL_FIXED_PRICE, BUY_BASE_PRICE

    # -------- CLOSE POSITIONS -------- #
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for pos in positions:
            if pos.type == mt5.POSITION_TYPE_BUY:
                order_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(SYMBOL).bid
            else:
                order_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(SYMBOL).ask

            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": pos.volume,
                "type": order_type,
                "position": pos.ticket,
                "price": price,
                "deviation": SLIPPAGE,
                "magic": MAGIC,
            })

    # -------- REMOVE PENDING ORDERS -------- #
    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for order in orders:
            mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order.ticket,
                "symbol": SYMBOL,
                "magic": MAGIC,
                "comment": "Remove pending",
            })

    # 🔄 RESET LOGIC VARIABLES
    SELL_FIXED_PRICE = None
    BUY_BASE_PRICE = None

    log("💰 ALL POSITIONS + PENDING ORDERS CLOSED")
# ---------------- WAIT ---------------- #
def wait_for_trigger_or_profit(base_profit):
    last_count = len(mt5.positions_get(symbol=SYMBOL) or [])

    while True:
        profit = get_profit() - base_profit
        print(f"\r📊 Profit: {profit:.2f} / {FIXED_PROFIT}", end="")

        # 🎯 PROFIT HIT
        if profit >= FIXED_PROFIT:
            print()
            log("🎯 TARGET HIT → CLOSING ALL")
            close_all()
            return "profit"

        positions = mt5.positions_get(symbol=SYMBOL) or []
        if len(positions) > last_count:
            return "triggered"

        time.sleep(POLL_INTERVAL)

# ---------------- MAIN BOT ---------------- #
def run_bot():
    log("🚀 STARTING CONTINUOUS CHAIN BOT")

    base_profit = get_profit()
    volume = START_VOLUME
    step = 1
    last_type = "BUY"

    # 🔥 FIRST ORDER
    place_order("BUY", get_buy_price(step), volume)

    while True:

        result = wait_for_trigger_or_profit(base_profit)

        if result == "profit":
            log("🛑 BOT STOPPED AFTER PROFIT")
            return

        volume += VOLUME_STEP

        # 🔄 SWITCH SIDE
        if last_type == "BUY":
            price = get_sell_price()
            log(f"\n📌 SELL → {price} vol={volume}")
            place_order("SELL", price, volume)
            last_type = "SELL"

        else:
            step += 1
            price = get_buy_price(step)
            log(f"\n📌 BUY step={step} → {price} vol={volume}")
            place_order("BUY", price, volume)
            last_type = "BUY"

# ---------------- RUN ---------------- #
try:
    run_bot()
except KeyboardInterrupt:
    log("🛑 Stopped manually")
finally:
    mt5.shutdown()
    log("🔌 MT5 Disconnected")