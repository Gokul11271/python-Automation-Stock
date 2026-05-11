import MetaTrader5 as mt5
import time
from datetime import datetime


# =========================================================
# CONFIG
# =========================================================
SYMBOL = "XAUUSD"

MAGIC_BUY = 5001
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
# LOG
# =========================================================
def log(*msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}]", *msg)

# =========================================================
# SEND ORDER
# =========================================================
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
def level_exists(price, side, magic):

    orders = mt5.orders_get(symbol=SYMBOL) or []

    positions = mt5.positions_get(symbol=SYMBOL) or []

    # -------- ORDERS -------- #
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
        "comment": "NEW_GRID_PATTERN"
    }

    if send(req):

        log(f"✅ {side} {volume} @ {price} (M{magic})")

        return price

    return None

# =========================================================
# PLACE EXACT PENDING
# =========================================================
def place_exact(side, price, volume, magic):

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
        "comment": "NEW_GRID_PATTERN"
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

    # -------- REMOVE ORDERS -------- #
    orders = mt5.orders_get(symbol=SYMBOL) or []

    for o in orders:

        mt5.order_send({
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": o.ticket
        })

        log(f"❌ Removed Pending {o.ticket}")

    log("💰 ALL CLOSED")

# =========================================================
# BUY ENGINE
# =========================================================
#
# BUYS increment by +1
#
# BUY  4000
# BUY  4001
# BUY  4002
#
# SELL hedge always gap below
#
# SELL 3998
# SELL 3999
# SELL 4000
#
# =========================================================
def next_buy_pattern(base, step, gap):

    level = step // 2

    # -------- ODD = SELL -------- #
    if step % 2 == 1:

        buy_price = base + level

        price = buy_price - gap

        return "SELL", round(price, 2)

    # -------- EVEN = BUY -------- #
    else:

        price = base + level

        return "BUY", round(price, 2)

# =========================================================
# SELL ENGINE
# =========================================================
#
# SELLS decrement by -1
#
# SELL 4000
# SELL 3999
# SELL 3998
#
# BUY hedge always gap above
#
# BUY 4002
# BUY 4001
# BUY 4000
#
# =========================================================
def next_sell_pattern(base, step, gap):

    level = step // 2

    # -------- ODD = BUY -------- #
    if step % 2 == 1:

        sell_price = base - level

        price = sell_price + gap

        return "BUY", round(price, 2)

    # -------- EVEN = SELL -------- #
    else:

        price = base - level

        return "SELL", round(price, 2)

# =========================================================
# MAIN
# =========================================================
def run():

    gap = float(input("Enter hedge gap: "))

    buy_vol_gen = volume_gen()
    sell_vol_gen = volume_gen()

    # =====================================================
    # INITIAL ORDERS
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
    # INITIAL HEDGE ORDERS
    # =====================================================
    place_exact(
        "SELL",
        round(base_buy - gap, 2),
        next(buy_vol_gen),
        MAGIC_BUY
    )

    place_exact(
        "BUY",
        round(base_sell + gap, 2),
        next(sell_vol_gen),
        MAGIC_SELL
    )

    # =====================================================
    # TRACKERS
    # =====================================================
    buy_step = 1
    sell_step = 1

    last_buy_positions = len(get_positions(MAGIC_BUY))
    last_sell_positions = len(get_positions(MAGIC_SELL))

    base_profit = mt5.account_info().profit

    # =====================================================
    # LOOP
    # =====================================================
    while True:

        time.sleep(1)

        profit = mt5.account_info().profit - base_profit

        # =================================================
        # PROFIT EXIT
        # =================================================
        if profit >= PROFIT_TARGET:

            log(f"🎯 PROFIT HIT {round(profit, 2)}")

            close_all()

            break

        # =================================================
        # LOSS EXIT
        # =================================================
        if profit <= -LOSS_LIMIT:

            log(f"❌ LOSS HIT {round(profit, 2)}")

            close_all()

            break

        # =================================================
        # BUY ENGINE
        # =================================================
        buy_positions = get_positions(MAGIC_BUY)

        if len(buy_positions) > last_buy_positions:

            buy_step += 1

            side, price = next_buy_pattern(
                base_buy,
                buy_step,
                gap
            )

            volume = next(buy_vol_gen)

            log(
                f"🔁 BUY ENGINE → "
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
        # SELL ENGINE
        # =================================================
        sell_positions = get_positions(MAGIC_SELL)

        if len(sell_positions) > last_sell_positions:

            sell_step += 1

            side, price = next_sell_pattern(
                base_sell,
                sell_step,
                gap
            )

            volume = next(sell_vol_gen)

            log(
                f"🔁 SELL ENGINE → "
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