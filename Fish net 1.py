import time
from datetime import datetime
from collections import deque

import MetaTrader5 as mt5
import pygame
import matplotlib.pyplot as plt

# =========================================================
# CONFIG
# =========================================================
SYMBOL = "XAUUSD"

MAGIC = 9090
SLIPPAGE = 50

BASE_LOT = 0.01
LOT_INCREMENT = 0.01

PROFIT_TARGET = 10

POLL_SECONDS = 0.1
PLOT_WINDOW = 120

# =========================================================
# SOUND
# =========================================================
pygame.init()
pygame.mixer.init()

try:
    trade_sound = pygame.mixer.Sound("tradewave.mp3")
    close_sound = pygame.mixer.Sound("closewave.mp3")

    print("✅ Sounds Loaded")

except Exception as e:

    print("❌ Sound Error:", e)

    trade_sound = None
    close_sound = None

# =========================================================
# MT5 INIT
# =========================================================
if not mt5.initialize():
    raise RuntimeError("❌ MT5 initialize failed")

if not mt5.symbol_select(SYMBOL, True):
    raise RuntimeError(f"❌ Failed selecting {SYMBOL}")

symbol_info = mt5.symbol_info(SYMBOL)

DIGITS = symbol_info.digits

# =========================================================
# INPUT
# =========================================================
GAP = float(input("Enter gap value: "))

# =========================================================
# HELPERS
# =========================================================
def now():
    return datetime.now().strftime("%H:%M:%S")


def log(*msg):
    print(f"[{now()}]", *msg)


def normalize(price):
    return round(price, DIGITS)


def volume_for_step(step):
    return round(BASE_LOT + ((step - 1) * LOT_INCREMENT), 2)


def get_tick():
    return mt5.symbol_info_tick(SYMBOL)


def my_positions():

    positions = mt5.positions_get(symbol=SYMBOL) or []

    return [p for p in positions if p.magic == MAGIC]


def my_orders():

    orders = mt5.orders_get(symbol=SYMBOL) or []

    return [o for o in orders if o.magic == MAGIC]


def get_latest_position():

    positions = my_positions()

    if not positions:
        return None

    positions.sort(key=lambda x: x.time)

    return positions[-1]

# =========================================================
# SEND ORDER
# =========================================================
def send_order(req):

    result = mt5.order_send(req)

    if result is None:
        return None

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return None

    return result

# =========================================================
# CANCEL ALL PENDING
# =========================================================
def cancel_pending():

    orders = my_orders()

    for o in orders:

        mt5.order_send({
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": o.ticket
        })

# =========================================================
# CLOSE ALL
# =========================================================
def close_all():

    log("🚨 Closing all")

    if close_sound:
        pygame.mixer.stop()
        close_sound.play()

    positions = my_positions()

    for p in positions:

        tick = get_tick()

        if tick is None:
            continue

        price = (
            tick.bid
            if p.type == mt5.POSITION_TYPE_BUY
            else tick.ask
        )

        close_type = (
            mt5.ORDER_TYPE_SELL
            if p.type == mt5.POSITION_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": p.volume,
            "type": close_type,
            "position": p.ticket,
            "price": price,
            "deviation": SLIPPAGE,
            "magic": MAGIC
        }

        send_order(req)

    cancel_pending()

    log("✅ Everything Closed")

# =========================================================
# MARKET BUY
# =========================================================
def market_buy(lot):

    tick = get_tick()

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY,
        "price": tick.ask,
        "deviation": SLIPPAGE,
        "magic": MAGIC
    }

    return send_order(req)

# =========================================================
# PLACE PENDING
# =========================================================
def place_pending(direction, target_price, lot):

    tick_size = 0.2
    shift = 0.0

    while True:

        tick = get_tick()

        if tick is None:
            time.sleep(0.1)
            continue

        ask = tick.ask
        bid = tick.bid

        # =================================================
        # SHIFT PRICE IF NEEDED
        # =================================================
        if direction == "BUY":

            adjusted_price = normalize(
                target_price + shift
            )

        else:

            adjusted_price = normalize(
                target_price - shift
            )

        # =================================================
        # BUY
        # =================================================
        if direction == "BUY":

            if adjusted_price > ask:
                order_type = mt5.ORDER_TYPE_BUY_STOP
            else:
                order_type = mt5.ORDER_TYPE_BUY_LIMIT

        # =================================================
        # SELL
        # =================================================
        else:

            if adjusted_price < bid:
                order_type = mt5.ORDER_TYPE_SELL_STOP
            else:
                order_type = mt5.ORDER_TYPE_SELL_LIMIT

        req = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": SYMBOL,
            "volume": lot,
            "type": order_type,
            "price": adjusted_price,
            "deviation": SLIPPAGE,
            "magic": MAGIC,
            "type_time": mt5.ORDER_TIME_GTC
        }

        result = mt5.order_send(req)

        # =================================================
        # SUCCESS
        # =================================================
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:

            log(
                f"✅ Pending {direction} "
                f"{adjusted_price} "
                f"lot={lot}"
            )

            return result

        # =================================================
        # SHIFT MORE
        # =================================================
        shift += tick_size

        log(
            f"⏳ Shift Retry "
            f"{direction} "
            f"{adjusted_price}"
        )

        time.sleep(0.2)

# =========================================================
# INITIAL GRID
# =========================================================
tick = get_tick()

INITIAL = round(tick.ask)

GRID_LOW = normalize(INITIAL - GAP)
GRID_MID_LOW = normalize(INITIAL)
GRID_MID_HIGH = normalize(INITIAL + GAP)
GRID_HIGH = normalize(INITIAL + (2 * GAP))

log("📌 GRID")
log(f"{GRID_LOW}")
log(f"{GRID_MID_LOW}")
log(f"{GRID_MID_HIGH}")
log(f"{GRID_HIGH}")

# =========================================================
# INITIAL BUY
# =========================================================
step = 1

initial_lot = volume_for_step(step)

log(f"🚀 Initial BUY lot={initial_lot}")

buy_result = market_buy(initial_lot)

if buy_result is None:
    raise RuntimeError("❌ Initial BUY failed")

if trade_sound:
    pygame.mixer.stop()
    trade_sound.play()

time.sleep(1)

# =========================================================
# FIRST GRID
# =========================================================
step += 1

lot = volume_for_step(step)

place_pending(
    "SELL",
    GRID_LOW,
    lot
)

place_pending(
    "SELL",
    GRID_MID_HIGH,
    lot
)

# =========================================================
# TRACK KNOWN TICKETS
# =========================================================
known_tickets = set()

for p in my_positions():
    known_tickets.add(p.ticket)

# =========================================================
# BASE EQUITY
# =========================================================
account = mt5.account_info()

base_equity = account.equity

# =========================================================
# MATPLOTLIB
# =========================================================
plt.ion()

fig, ax = plt.subplots(figsize=(5, 3))

price_history = deque(maxlen=PLOT_WINDOW)

# =========================================================
# MAIN LOOP
# =========================================================
while True:

    time.sleep(POLL_SECONDS)

    tick = get_tick()

    if tick is not None:

        mid_price = (tick.ask + tick.bid) / 2

        price_history.append(mid_price)

    # =====================================================
    # DETECT NEW POSITION
    # =====================================================
    latest_pos = get_latest_position()

    if latest_pos and latest_pos.ticket not in known_tickets:

        # =================================================
        # CANCEL OLD PENDING
        # =================================================
        cancel_pending()

        known_tickets.add(latest_pos.ticket)

        pos = latest_pos

        trade_type = (
            "BUY"
            if pos.type == mt5.POSITION_TYPE_BUY
            else "SELL"
        )

        log(
            f"⚡ Triggered "
            f"{trade_type} "
            f"lot={pos.volume}"
        )

        if trade_sound:
            pygame.mixer.stop()
            trade_sound.play()

        # =================================================
        # NEXT LOT
        # =================================================
        step += 1

        lot = volume_for_step(step)

        # =================================================
        # FIND NEAREST LEVEL
        # =================================================
        levels = {
            GRID_LOW: "LOW",
            GRID_MID_LOW: "MID_LOW",
            GRID_MID_HIGH: "MID_HIGH",
            GRID_HIGH: "HIGH"
        }

        nearest = min(
            levels.keys(),
            key=lambda x: abs(x - pos.price_open)
        )

        level_name = levels[nearest]

        log(f"📍 Level={level_name}")

        # =================================================
        # SELL TRIGGERED
        # =================================================
        if pos.type == mt5.POSITION_TYPE_SELL:

            # =============================================
            # LOW EDGE
            # ONLY ONE BUY
            # =============================================
            if level_name == "LOW":

                place_pending(
                    "BUY",
                    GRID_MID_LOW,
                    lot
                )

            # =============================================
            # MID_HIGH
            # TWO BUY
            # =============================================
            elif level_name == "MID_HIGH":

                place_pending(
                    "BUY",
                    GRID_MID_LOW,
                    lot
                )

                place_pending(
                    "BUY",
                    GRID_HIGH,
                    lot
                )

        # =================================================
        # BUY TRIGGERED
        # =================================================
        else:

            # =============================================
            # MID_LOW
            # TWO SELL
            # =============================================
            if level_name == "MID_LOW":

                place_pending(
                    "SELL",
                    GRID_LOW,
                    lot
                )

                place_pending(
                    "SELL",
                    GRID_MID_HIGH,
                    lot
                )

            # =============================================
            # HIGH EDGE
            # ONLY ONE SELL
            # =============================================
            elif level_name == "HIGH":

                place_pending(
                    "SELL",
                    GRID_MID_HIGH,
                    lot
                )

    # =====================================================
    # PROFIT CHECK
    # =====================================================
    acc = mt5.account_info()

    current_profit = acc.equity - base_equity

    if current_profit >= PROFIT_TARGET:

        log(f"🎯 PROFIT HIT {current_profit:.2f}")

        close_all()

        break

    # =====================================================
    # VISUALIZATION
    # =====================================================
    ax.clear()

    x = list(range(len(price_history)))

    y = list(price_history)

    if y:

        ax.plot(
            x,
            y,
            linewidth=1.5
        )

        ax.scatter(
            [x[-1]],
            [y[-1]],
            s=25
        )

    # =====================================================
    # GRID LINES
    # =====================================================
    for lvl in [
        GRID_LOW,
        GRID_MID_LOW,
        GRID_MID_HIGH,
        GRID_HIGH
    ]:

        ax.hlines(
            lvl,
            0,
            max(1, len(x)),
            linewidth=1
        )

    # =====================================================
    # OPEN POSITIONS
    # =====================================================
    positions = my_positions()

    for p in positions:

        marker = "^" if p.type == mt5.POSITION_TYPE_BUY else "v"

        ax.scatter(
            [x[-1]],
            [p.price_open],
            marker=marker,
            s=70
        )

        ax.text(
            x[-1],
            p.price_open,
            f"{p.volume:.2f}",
            fontsize=8
        )

    # =====================================================
    # PENDING ORDERS
    # =====================================================
    orders = my_orders()

    for o in orders:

        ax.scatter(
            [x[-1]],
            [o.price_open],
            marker="x",
            s=70
        )

        ax.text(
            x[-1],
            o.price_open,
            f"{o.volume_initial:.2f}",
            fontsize=8
        )

    ax.set_title(
        f"Step={step} | Profit={current_profit:.2f}",
        fontsize=9
    )

    ax.grid(True)

    plt.tight_layout()

    plt.pause(0.01)

# =========================================================
# CLEANUP
# =========================================================
plt.close()

pygame.quit()
mt5.shutdown()

print("✅ BOT FINISHED")