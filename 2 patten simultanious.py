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
OFFSET = 2   # distance between patterns

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

# -------- VOLUME -------- #
def volume_generator():
    v = 0.01
    while True:
        yield round(v, 2)
        v += 0.01

# -------- ORDER SEND -------- #
def send_order(req):
    for fill in [mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]:
        req["type_filling"] = fill
        result = mt5.order_send(req)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            return True
    return False

# -------- MARKET -------- #
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
        log(f"✅ {side} {volume} @ {price}")
        return price
    return None

# -------- STOP -------- #
def place_stop(side, price, volume):
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

# -------- CLOSE ALL -------- #
def close_all():
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

    log("💰 ALL CLOSED")

# -------- PATTERN ENGINE -------- #
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
    vol_gen = volume_generator()

    # FIRST PATTERN
    v1 = next(vol_gen)
    base1 = market_order("BUY", v1)

    # SECOND PATTERN (OFFSET)
    v2 = next(vol_gen)
    base2 = base1 - OFFSET * gap
    market_order("BUY", v2)

    state1 = {"base": base1, "step": 1}
    state2 = {"base": base2, "step": 1}

    place_stop("SELL", base1 - gap, next(vol_gen))
    place_stop("SELL", base2 - gap, next(vol_gen))

    base_equity = mt5.account_info().profit
    last_count = 2

    while True:
        time.sleep(1)

        profit = mt5.account_info().profit - base_equity

        if profit >= PROFIT_UNIT:
            log(f"🎯 PROFIT HIT {profit}")
            close_all()
            break

        positions = mt5.positions_get(symbol=SYMBOL) or []

        if len(positions) > last_count:

            for state in [state1, state2]:
                state["step"] += 1
                side, price = next_price(state["base"], state["step"], gap)
                vol = next(vol_gen)

                log(f"🔁 P{1 if state==state1 else 2} → {side} {vol} @ {price}")
                place_stop(side, price, vol)

            last_count = len(positions)

# -------- RUN -------- #
run()