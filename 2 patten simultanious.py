'''	B		B		B		B	
volume = 0.01	4000	0.03	4001	0.05	4002	0.07	4003	
volume = 0.02	3999	0.04	4000	0.06	4001	0.08	4002	
	S		S		S		S	  
								
	B		B		B		B	
volume = 0.01	3998	0.03	3999	0.05	4000	0.07	4001	
volume = 0.02	3997	0.04	3998	0.06	3999	0.08	4000	
	S		S		S		S	
								
'''

import MetaTrader5 as mt5
import time
from datetime import datetime

# -------- CONFIG -------- #
SYMBOL = "XAUUSD"
MAGIC_1 = 3001
MAGIC_2 = 3002
SLIPPAGE = 100
PROFIT_UNIT = 3
LOSS_TARGET = 1000
OFFSET = 2

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

def count_positions(magic):
    positions = mt5.positions_get(symbol=SYMBOL) or []
    return len([p for p in positions if p.magic == magic])

# -------- VOLUME -------- #
def volume_generator():
    v = 0.01
    while True:
        yield round(v, 2)
        v += 0.01

# -------- ORDER -------- #
def send_order(req):
    result = mt5.order_send(req)
    return result and result.retcode == mt5.TRADE_RETCODE_DONE

def market_order(side, volume, magic):
    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if side == "BUY" else tick.bid

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic
    }

    if send_order(req):
        log(f"✅ {side} {volume} @ {price} (M{magic})")
        return price
    return None

def place_stop(side, price, volume, magic):
    tick = mt5.symbol_info_tick(SYMBOL)

    if side == "BUY" and tick.ask >= price:
        return market_order("BUY", volume, magic)

    if side == "SELL" and tick.bid <= price:
        return market_order("SELL", volume, magic)

    order_type = mt5.ORDER_TYPE_BUY_STOP if side == "BUY" else mt5.ORDER_TYPE_SELL_STOP

    req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic
    }

    if send_order(req):
        log(f"📌 {side} STOP {volume} @ {price} (M{magic})")

def place_pending_only(side, price, volume, magic):
    tick = mt5.symbol_info_tick(SYMBOL)

    if side == "BUY":
        # 🔥 decide order type correctly
        if price < tick.ask:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT
        else:
            order_type = mt5.ORDER_TYPE_BUY_STOP
    else:
        if price > tick.bid:
            order_type = mt5.ORDER_TYPE_SELL_LIMIT
        else:
            order_type = mt5.ORDER_TYPE_SELL_STOP

    req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic
    }

    result = mt5.order_send(req)

    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"📌 INIT {side} {volume} @ {price} (M{magic})")
    else:
        log(f"❌ INIT FAILED {side} @ {price}")
# -------- CLOSE -------- #
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
                "magic": p.magic
            }
            send_order(req)

    log("💰 ALL CLOSED")

# -------- PRICE LOGIC -------- #
def next_price(base, step, gap):
    if step % 2 == 1:
        level = step // 2
        return "SELL", base - gap + (level * gap)
    else:
        level = step // 2
        return "BUY", base + (level * gap)

# -------- MAIN -------- #
def run():
    gap = float(input("Enter gap: "))

    vol1 = volume_generator()
    vol2 = volume_generator()

    # -------- PATTERN 1 -------- #
    base1 = market_order("BUY", next(vol1), MAGIC_1)

    # -------- PATTERN 2 -------- #
    base2 = base1 - OFFSET * gap

    log(f"📊 Base1: {base1}")
    log(f"📊 Base2: {base2}")

    place_pending_only("BUY", base2, next(vol2), MAGIC_2)

    # initial SELLs
    place_stop("SELL", base1 - gap, next(vol1), MAGIC_1)
    place_stop("SELL", base2 - gap, next(vol2), MAGIC_2)

    step1 = 1
    step2 = 1

    last_p1 = count_positions(MAGIC_1)
    last_p2 = count_positions(MAGIC_2)

    base_equity = mt5.account_info().profit

    while True:
        time.sleep(1)

        profit = mt5.account_info().profit - base_equity

        if profit >= PROFIT_UNIT:
            log(f"🎯 PROFIT HIT {profit}")
            close_all()
            break

        p1 = count_positions(MAGIC_1)
        p2 = count_positions(MAGIC_2)

        # Pattern 1 trigger
        if p1 > last_p1:
            step1 += 1
            side, price = next_price(base1, step1, gap)
            vol = next(vol1)

            log(f"🔁 P1 → {side} {vol} @ {price}")
            place_stop(side, price, vol, MAGIC_1)

            last_p1 = p1

        # Pattern 2 trigger
        if p2 > last_p2:
            step2 += 1
            side, price = next_price(base2, step2, gap)
            vol = next(vol2)

            log(f"🔁 P2 → {side} {vol} @ {price}")
            place_stop(side, price, vol, MAGIC_2)

            last_p2 = p2

# -------- RUN -------- #
run()