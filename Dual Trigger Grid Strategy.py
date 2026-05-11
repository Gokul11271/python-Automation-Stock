import MetaTrader5 as mt5
import time
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================
SYMBOL = "XAUUSD"

MAGIC_BUY  = 5001
MAGIC_SELL = 5002
SLIPPAGE = 100

PROFIT_TARGET = 5
LOSS_LIMIT = 1000

# =========================================================
# MT5 INIT
# =========================================================
if not mt5.initialize():
    print("❌ MT5 Initialization Failed")
    quit()

mt5.symbol_select(SYMBOL, True)

# =========================================================
# HELPERS
# =========================================================
def log(*msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}]", *msg)

def send(req):

    result = mt5.order_send(req)

    if result is None:
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:

        log(f"❌ Failed: {result.retcode}")

        return False

    return True

# =========================================================
# VOLUME GENERATOR
# =========================================================
#
# 0.01
# 0.02
# 0.03
# ...
#
# =========================================================
def volume_gen():

    v = 0.01

    while True:

        yield round(v, 2)

        v += 0.01

# =========================================================
# GET POSITIONS
# =========================================================
def get_positions(magic):

    positions = mt5.positions_get(symbol=SYMBOL) or []

    return [p for p in positions if p.magic == magic]

# =========================================================
# DUPLICATE CHECK
# =========================================================
#
# ALLOW:
# BUY  @ 4696
# SELL @ 4696
#
# BLOCK:
# BUY  @ 4696 twice
# SELL @ 4696 twice
#
# =========================================================
def level_exists(price, side, magic):

    orders = mt5.orders_get(symbol=SYMBOL) or []

    positions = mt5.positions_get(symbol=SYMBOL) or []

    # -------- PENDING -------- #
    for o in orders:

        if o.magic != magic:
            continue

        existing_side = (
            "BUY"
            if o.type in [
                mt5.ORDER_TYPE_BUY_STOP,
                mt5.ORDER_TYPE_BUY_LIMIT
            ]
            else "SELL"
        )

        if existing_side == side:

            if abs(o.price_open - price) < 0.01:
                return True

    # -------- POSITIONS -------- #
    for p in positions:

        if p.magic != magic:
            continue

        existing_side = (
            "BUY"
            if p.type == mt5.POSITION_TYPE_BUY
            else "SELL"
        )

        if existing_side == side:

            if abs(p.price_open - price) < 0.01:
                return True

    return False

# =========================================================
# MARKET ORDER
# =========================================================
#
# ONLY INITIAL ORDERS USE MARKET EXECUTION
#
# =========================================================
def market_order(side, volume, magic):

    tick = mt5.symbol_info_tick(SYMBOL)

    price = tick.ask if side == "BUY" else tick.bid

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": (
            mt5.ORDER_TYPE_BUY
            if side == "BUY"
            else mt5.ORDER_TYPE_SELL
        ),
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": "DUAL_CHAIN_GRID"
    }

    if send(req):

        log(f"✅ {side} {volume} @ {price} (M{magic})")

        return price

    return None

# =========================================================
# STRICT PENDING ORDER
# =========================================================
#
# NO MARKET OVERRIDE
# NO PRICE DEVIATION
#
# =========================================================
def place_exact(side, price, volume, magic):

    # -------- DUPLICATE BLOCK -------- #
    if level_exists(price, side, magic):
        return

    tick = mt5.symbol_info_tick(SYMBOL)

    # -------- BUY -------- #
    if side == "BUY":

        if price > tick.ask:
            order_type = mt5.ORDER_TYPE_BUY_STOP
        else:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT

    # -------- SELL -------- #
    else:

        if price < tick.bid:
            order_type = mt5.ORDER_TYPE_SELL_STOP
        else:
            order_type = mt5.ORDER_TYPE_SELL_LIMIT

    req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": "DUAL_CHAIN_GRID"
    }

    if send(req):

        log(f"📌 {side} {volume} @ {price} (M{magic})")

# =========================================================
# CLOSE EVERYTHING
# =========================================================
def close_all():

    log("🚨 Closing all...")

    # -------- CLOSE POSITIONS -------- #
    positions = mt5.positions_get(symbol=SYMBOL) or []

    for p in positions:

        tick = mt5.symbol_info_tick(SYMBOL)

        close_price = (
            tick.bid
            if p.type == mt5.POSITION_TYPE_BUY
            else tick.ask
        )

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": p.volume,
            "type": (
                mt5.ORDER_TYPE_SELL
                if p.type == mt5.POSITION_TYPE_BUY
                else mt5.ORDER_TYPE_BUY
            ),
            "position": p.ticket,
            "price": close_price,
            "deviation": SLIPPAGE,
            "magic": p.magic
        }

        send(req)

    # -------- REMOVE PENDING -------- #
    orders = mt5.orders_get(symbol=SYMBOL) or []

    for o in orders:

        mt5.order_send({
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": o.ticket
        })

        log(f"❌ Removed Pending {o.ticket}")

    log("💰 ALL CLOSED")

# =========================================================
# BUY PATTERN
# =========================================================
#
# BUY SIDE:
#
# 0.01 @ base
# 0.03 @ base+gap
# 0.05 @ base+2gap
#
# SELL SIDE:
#
# 0.02 @ base-gap
# 0.04 @ base
# 0.06 @ base+gap
#
# =========================================================
def next_buy_pattern(base, step, gap):

    # ODD → SELL
    if step % 2 == 1:

        level = step // 2

        price = base - gap + (level * gap)

        return "SELL", price

    # EVEN → BUY
    else:

        level = step // 2

        price = base + (level * gap)

        return "BUY", price

# =========================================================
# SELL PATTERN
# =========================================================
#
# SELL SIDE:
#
# 0.01 @ base
# 0.03 @ base-gap
# 0.05 @ base-2gap
#
# BUY SIDE:
#
# 0.02 @ base+gap
# 0.04 @ base
# 0.06 @ base-gap
#
# =========================================================
def next_sell_pattern(base, step, gap):

    # ODD → BUY
    if step % 2 == 1:

        level = step // 2

        price = base + gap - (level * gap)

        return "BUY", price

    # EVEN → SELL
    else:

        level = step // 2

        price = base - (level * gap)

        return "SELL", price

# =========================================================
# MAIN
# =========================================================
def run():

    gap = float(input("Enter gap: "))

    buy_vol_gen  = volume_gen()
    sell_vol_gen = volume_gen()

    # =====================================================
    # INITIAL EXECUTION
    # =====================================================
    base_buy = market_order(
        "BUY",
        next(buy_vol_gen),
        MAGIC_BUY
    )

    base_sell = market_order(
        "SELL",
        next(sell_vol_gen),
        MAGIC_SELL
    )

    if not base_buy or not base_sell:
        return

    log(f"📊 BUY BASE  : {base_buy}")
    log(f"📊 SELL BASE : {base_sell}")

    # =====================================================
    # INITIAL CHAIN ORDERS
    # =====================================================
    #
    # BUY PATTERN:
    # place only 0.02
    #
    # SELL PATTERN:
    # place only 0.02
    #
    # IMPORTANT:
    # 0.03 should come ONLY after 0.02 triggers
    #
    # =====================================================
    place_exact(
        "SELL",
        base_buy - gap,
        next(buy_vol_gen),
        MAGIC_BUY
    )

    place_exact(
        "BUY",
        base_sell + gap,
        next(sell_vol_gen),
        MAGIC_SELL
    )

    # -------- TRACKERS -------- #
    buy_step  = 1
    sell_step = 1

    last_buy_positions  = len(get_positions(MAGIC_BUY))
    last_sell_positions = len(get_positions(MAGIC_SELL))

    base_profit = mt5.account_info().profit

    # =====================================================
    # LOOP
    # =====================================================
    while True:

        time.sleep(1)

        profit = mt5.account_info().profit - base_profit

        # =================================================
        # EXIT
        # =================================================
        if profit >= PROFIT_TARGET:

            log(f"🎯 PROFIT HIT {round(profit, 2)}")

            close_all()

            break

        if profit <= -LOSS_LIMIT:

            log(f"❌ LOSS HIT {round(profit, 2)}")

            close_all()

            break

        # =================================================
        # BUY PATTERN
        # =================================================
        buy_positions = get_positions(MAGIC_BUY)

        # NEW EXECUTION DETECTED
        if len(buy_positions) > last_buy_positions:

            buy_step += 1

            side, price = next_buy_pattern(
                base_buy,
                buy_step,
                gap
            )

            volume = next(buy_vol_gen)

            log(
                f"🔁 BUY PATTERN → "
                f"{side} {volume} @ {price}"
            )

            place_exact(
                side,
                price,
                volume,
                MAGIC_BUY
            )

            last_buy_positions = len(buy_positions)

        # =================================================
        # SELL PATTERN
        # =================================================
        sell_positions = get_positions(MAGIC_SELL)

        # NEW EXECUTION DETECTED
        if len(sell_positions) > last_sell_positions:

            sell_step += 1

            side, price = next_sell_pattern(
                base_sell,
                sell_step,
                gap
            )

            volume = next(sell_vol_gen)

            log(
                f"🔁 SELL PATTERN → "
                f"{side} {volume} @ {price}"
            )

            place_exact(
                side,
                price,
                volume,
                MAGIC_SELL
            )

            last_sell_positions = len(sell_positions)

# =========================================================
# RUN
# =========================================================
run()