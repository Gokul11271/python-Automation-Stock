"""								
	B		B		B		B	
volume = 0.01	4000	0.03	4001	0.05	4002	0.07	4003	
volume = 0.02	3999	0.04	4000	0.06	4001	0.08	4002	
	S		S		S		S	  
"""


import MetaTrader5 as mt5
import time
from datetime import datetime

# -------- CONFIG -------- #
SYMBOL = "XAUUSD"
MAGIC = 3003
SLIPPAGE = 100
PROFIT_UNIT = 3
LOSS_TARGET = 1000
MAX_RETRIES = 3

# -------- INIT -------- #
if not mt5.initialize():
    print("❌ MT5 Init Failed")
    quit()

mt5.symbol_select(SYMBOL, True)

# -------- HELPERS -------- #
def now():
    return datetime.now().strftime("%H:%M:%S")

def log(*msg):
    print(f"[{now()}]", *msg)

# -------- VOLUME PATTERN -------- #
def volume_generator(start=0.01, step=0.01):
    current = start
    while True:
        yield round(current, 2)
        current += step
# -------- STRONG ORDER SEND -------- #
def send_order(req):
    for fill in [mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]:
        req["type_filling"] = fill

        for attempt in range(1, MAX_RETRIES + 1):
            result = mt5.order_send(req)

            if result is None:
                log(f"❌ No response (attempt {attempt})")
                time.sleep(0.3)
                continue

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                return True

            if result.retcode == 10030:
                break

            log(f"❌ Failed retcode={result.retcode}")
            time.sleep(0.3)

    log("🚨 Order failed completely")
    return False

# -------- MARKET ORDER -------- #
def market_order(side, volume):
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if side == "BUY" else tick.bid

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": MAGIC
    }

    if send_order(req):
        log(f"✅ MARKET {side} {volume} @ {price}")
        return price

    return None

# -------- CANCEL PENDING -------- #
def cancel_pending():
    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for o in orders:
            mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": o.ticket
            })

# -------- PLACE STOP -------- #
def place_stop(side, price, volume):
    cancel_pending()

    tick = mt5.symbol_info_tick(SYMBOL)

    if side == "BUY":
        if tick.ask >= price:
            return market_order("BUY", volume)
        order_type = mt5.ORDER_TYPE_BUY_STOP
    else:
        if tick.bid <= price:
            return market_order("SELL", volume)
        order_type = mt5.ORDER_TYPE_SELL_STOP

    req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": MAGIC
    }

    if send_order(req):
        log(f"📌 {side} STOP {volume} @ {price}")
        return price

    return None

# -------- CLOSE ALL -------- #
def close_all():
    log("🚨 Closing all...")

    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for p in positions:
            tick = mt5.symbol_info_tick(SYMBOL)
            price = tick.bid if p.type == 0 else tick.ask

            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": p.volume,
                "type": mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY,
                "position": p.ticket,
                "price": price,
                "deviation": SLIPPAGE,
                "magic": MAGIC
            }

            send_order(req)

    cancel_pending()
    log("💰 ALL CLOSED")

# -------- MAIN -------- #
def run():
    gap = float(input("Enter gap: "))
    vol_gen = volume_generator()

    # STEP 0 → FIRST BUY
    first_vol = next(vol_gen)  # 0.01
    entry_price = market_order("BUY", first_vol)

    if not entry_price:
        return

    # 🔥 LOCK BASE PRICE
    base_price = entry_price
    step = 0

    base_equity = mt5.account_info().profit

    log(f"🎯 Target Profit: {PROFIT_UNIT}")
    log(f"📊 Base Locked: {base_price}")

    # STEP 1 → FIRST SELL
    step += 1
    next_vol = next(vol_gen)  # 0.02
    first_sell_price = base_price - gap
    place_stop("SELL", first_sell_price, next_vol)

    last_count = 1

    while True:
        time.sleep(1)

        acc = mt5.account_info()
        profit = acc.profit - base_equity

        if profit >= PROFIT_UNIT:
            log(f"🎯 PROFIT HIT {profit}")
            close_all()
            break

        if profit <= -LOSS_TARGET:
            log(f"❌ LOSS HIT {profit}")
            close_all()
            break

        positions = mt5.positions_get(symbol=SYMBOL) or []
        current_count = len(positions)

        if current_count > last_count:
            step += 1

            next_vol = next(vol_gen)

            if step % 2 == 1:
                # SELL SIDE
                level = step // 2
                next_side = "SELL"
                next_price = base_price - gap + (level * gap)

            else:
                # BUY SIDE
                level = step // 2
                next_side = "BUY"
                next_price = base_price + (level * gap)

            log(f"🔁 Pattern → {next_side} {next_vol} @ {next_price}")
            place_stop(next_side, next_price, next_vol)

            last_count = current_count

# -------- RUN -------- #
run()