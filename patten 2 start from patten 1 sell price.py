import MetaTrader5 as mt5
import time
from datetime import datetime
import pygame

# =========================================================
# CONFIG
# =========================================================
SYMBOL = "XAUUSD"

MAGIC_BUY = 5001
MAGIC_SELL = 5002

SLIPPAGE = 100

PROFIT_TARGET = 20
LOSS_LIMIT = 1000

# =========================================================
# MT5 INIT
# =========================================================
if not mt5.initialize():
    print("❌ MT5 Initialization Failed")
    quit()

mt5.symbol_select(SYMBOL, True)

# =========================================================
# SOUND INIT
# =========================================================
pygame.init()
pygame.mixer.init()

try:

    trade_sound = pygame.mixer.Sound("tradewave.mp3")
    close_sound = pygame.mixer.Sound("closewave.mp3")

    trade_sound.set_volume(0.5)
    close_sound.set_volume(0.7)

    trade_channel = pygame.mixer.Channel(0)
    close_channel = pygame.mixer.Channel(1)

except Exception as e:

    print("❌ Sound Load Error:", e)

    trade_sound = None
    close_sound = None

# =========================================================
# LOG
# =========================================================
def log(*msg):

    print(f"[{datetime.now().strftime('%H:%M:%S')}]", *msg)

# =========================================================
# PLAY TRADE SOUND
# =========================================================
def play_trade_sound():

    try:
        if trade_sound:
            trade_channel.play(trade_sound)
    except:
        pass

# =========================================================
# PLAY CLOSE SOUND
# =========================================================
def play_close_sound():

    try:
        if close_sound:
            close_channel.play(close_sound)
    except:
        pass

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

    # -----------------------------------------------------
    # CHECK PENDING
    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # CHECK POSITIONS
    # -----------------------------------------------------
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
        "comment": "PATTERN_GRID"
    }

    if send(req):

        log(f"✅ {side} {volume} @ {round(price,2)} (M{magic})")

        play_trade_sound()

        return True

    return False

# =========================================================
# PLACE EXACT ORDER
# =========================================================
def place_exact(side, price, volume, magic):

    if level_exists(price, side, magic):
        return

    tick = mt5.symbol_info_tick(SYMBOL)

    # -----------------------------------------------------
    # BUY
    # -----------------------------------------------------
    if side == "BUY":

        if price > tick.ask:
            order_type = mt5.ORDER_TYPE_BUY_STOP
        else:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT

    # -----------------------------------------------------
    # SELL
    # -----------------------------------------------------
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
        "price": round(price, 2),
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": "PATTERN_GRID"
    }

    if send(req):

        log(f"📌 {side} {volume} @ {round(price,2)} (M{magic})")

        play_trade_sound()

# =========================================================
# CLOSE EVERYTHING
# =========================================================
def close_all():

    log("🚨 Closing All Orders")

    play_close_sound()

    # -----------------------------------------------------
    # CLOSE POSITIONS
    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # REMOVE PENDING
    # -----------------------------------------------------
    orders = mt5.orders_get(symbol=SYMBOL) or []

    for o in orders:

        mt5.order_send({
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": o.ticket
        })

        log(f"❌ Removed Pending {o.ticket}")

    log("💰 ALL CLOSED")

# =========================================================
# BUY ENGINE PATTERN
# =========================================================
def buy_pattern(base_price, gap, step):

    # -----------------------------------------------------
    # BUY SIDE
    # 0.01 4000
    # 0.03 4001
    # 0.05 4002
    # -----------------------------------------------------
    if step % 2 == 1:

        level = (step - 1) // 2

        side = "BUY"

        price = base_price + level

        volume = round(0.01 + (level * 0.02), 2)

    # -----------------------------------------------------
    # SELL SIDE
    # 0.02 3998
    # 0.04 3999
    # 0.06 4000
    # -----------------------------------------------------
    else:

        level = (step - 2) // 2

        side = "SELL"

        price = (base_price - gap) + level

        volume = round(0.02 + (level * 0.02), 2)

    return side, round(price, 2), volume

# =========================================================
# SELL ENGINE PATTERN
# =========================================================
def sell_pattern(base_price, gap, step):

    # -----------------------------------------------------
    # BUY SIDE
    # 0.02 3998
    # 0.04 3999
    # 0.06 4000
    # -----------------------------------------------------
    if step % 2 == 1:

        level = (step - 1) // 2

        side = "BUY"

        price = (base_price - gap) + level

        volume = round(0.02 + (level * 0.02), 2)

    # -----------------------------------------------------
    # SELL SIDE
    # 0.03 3996
    # 0.05 3997
    # 0.07 3998
    # -----------------------------------------------------
    else:

        level = (step - 2) // 2

        side = "SELL"

        price = (base_price - (gap * 2)) + level

        volume = round(0.03 + (level * 0.02), 2)

    return side, round(price, 2), volume

# =========================================================
# MAIN
# =========================================================
def run():

    gap = float(input("\nEnter hedge gap: "))

    # =====================================================
    # CENTER PRICE
    # =====================================================
    tick = mt5.symbol_info_tick(SYMBOL)

    center_price = round(
        (tick.ask + tick.bid) / 2,
        2
    )

    # =====================================================
    # INITIAL MARKET BUY
    # =====================================================
    buy_ok = market_order(
        "BUY",
        0.01,
        MAGIC_BUY
    )

    if not buy_ok:
        return

    base_buy = center_price
    base_sell = center_price

    log(f"📊 CENTER PRICE : {center_price}")

    # =====================================================
    # PATTERN 1 INITIAL SELL
    # =====================================================
    place_exact(
        "SELL",
        round(base_buy - gap, 2),
        0.02,
        MAGIC_BUY
    )

    # =====================================================
    # PATTERN 2 INITIAL BUY
    # =====================================================
    place_exact(
        "BUY",
        round(base_sell - gap, 2),
        0.02,
        MAGIC_SELL
    )

    # =====================================================
    # TRACKERS
    # =====================================================
    buy_step = 2
    sell_step = 1

    last_buy_positions = len(get_positions(MAGIC_BUY))
    last_sell_positions = len(get_positions(MAGIC_SELL))

    base_profit = mt5.account_info().profit

    # =====================================================
    # MAIN LOOP
    # =====================================================
    while True:

        time.sleep(1)

        profit = mt5.account_info().profit - base_profit

        # =================================================
        # PROFIT TARGET
        # =================================================
        if profit >= PROFIT_TARGET:

            log(f"🎯 PROFIT TARGET HIT {round(profit,2)}")

            close_all()

            break

        # =================================================
        # LOSS LIMIT
        # =================================================
        if profit <= -LOSS_LIMIT:

            log(f"❌ LOSS LIMIT HIT {round(profit,2)}")

            close_all()

            break

        # =================================================
        # BUY ENGINE
        # =================================================
        buy_positions = get_positions(MAGIC_BUY)

        if len(buy_positions) > last_buy_positions:

            buy_step += 1

            side, price, volume = buy_pattern(
                base_buy,
                gap,
                buy_step
            )

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

            side, price, volume = sell_pattern(
                base_sell,
                gap,
                sell_step
            )

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

# =========================================================
# CLEANUP
# =========================================================
pygame.quit()