import time
from collections import deque
from datetime import datetime

import MetaTrader5 as mt5
import matplotlib.pyplot as plt
import pygame

# =========================================================
# CONFIG
# =========================================================
SYMBOL = "XAUUSD"
MAGIC = 9090
SLIPPAGE = 50

PROFIT_TARGET = 10.0
MAX_STEPS = 50

BASE_LOT_UNIT = 0.01

PLOT_WINDOW = 150
POLL_SECONDS = 1

# =========================================================
# SOUND INIT
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
# INIT MT5
# =========================================================
if not mt5.initialize():
    raise RuntimeError("❌ MT5 initialization failed")

if not mt5.symbol_select(SYMBOL, True):
    raise RuntimeError(f"❌ Failed to select symbol {SYMBOL}")

# =========================================================
# USER INPUT
# =========================================================
GAP = float(input("Enter gap value: "))

# =========================================================
# HELPERS
# =========================================================
def now():
    return datetime.now().strftime("%H:%M:%S")


def log(*msg):
    print(f"[{now()}]", *msg)


def volume_for_step(step):

    return round(step * BASE_LOT_UNIT, 2)


def get_tick():
    return mt5.symbol_info_tick(SYMBOL)


def my_positions():

    positions = mt5.positions_get(symbol=SYMBOL) or []

    return [p for p in positions if p.magic == MAGIC]


def my_orders():

    orders = mt5.orders_get(symbol=SYMBOL) or []

    return [o for o in orders if o.magic == MAGIC]

# =========================================================
# SEND ORDER
# =========================================================
def send_order(req):

    fill_types = [
        mt5.ORDER_FILLING_RETURN,
        mt5.ORDER_FILLING_IOC,
        mt5.ORDER_FILLING_FOK
    ]

    for fill in fill_types:

        req["type_filling"] = fill

        result = mt5.order_send(req)

        if result is None:
            continue

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return result

    return None

# =========================================================
# CANCEL PENDING
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

    log("🚨 Closing everything...")

    # ============================================
    # PLAY CLOSE SOUND
    # ============================================
    if close_sound:
        pygame.mixer.stop()
        close_sound.play()

    positions = my_positions()

    for p in positions:

        tick = get_tick()

        if tick is None:
            continue

        price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask

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

    log("✅ All positions closed")

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
def place_pending(order_type, price, lot):

    req = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": MAGIC,
        "type_time": mt5.ORDER_TIME_GTC
    }

    return send_order(req)

# =========================================================
# PLACE NEXT GRID
# =========================================================
def place_next_grid(base_price, current_step):

    cancel_pending()

    next_step = current_step + 1

    lot = volume_for_step(next_step)

    # =====================================================
    # EVEN STEP -> SELL MODE
    # =====================================================
    if next_step % 2 == 0:

        place_pending(
            mt5.ORDER_TYPE_SELL_LIMIT,
            base_price + GAP,
            lot
        )

        place_pending(
            mt5.ORDER_TYPE_SELL_STOP,
            base_price - GAP,
            lot
        )

        mode = "SELL"

    # =====================================================
    # ODD STEP -> BUY MODE
    # =====================================================
    else:

        place_pending(
            mt5.ORDER_TYPE_BUY_STOP,
            base_price + GAP,
            lot
        )

        place_pending(
            mt5.ORDER_TYPE_BUY_LIMIT,
            base_price - GAP,
            lot
        )

        mode = "BUY"

    return mode, next_step, lot

# =========================================================
# MATPLOTLIB
# =========================================================
plt.ion()

fig, ax = plt.subplots(figsize=(15, 8))

price_history = deque(maxlen=PLOT_WINDOW)

# =========================================================
# INITIAL BUY
# =========================================================
step_count = 1

initial_lot = volume_for_step(step_count)

log(f"🚀 Initial BUY lot={initial_lot}")

buy_result = market_buy(initial_lot)

if buy_result is None:
    raise RuntimeError("❌ Initial BUY failed")

# ============================================
# PLAY TRADE SOUND
# ============================================
if trade_sound:
    pygame.mixer.stop()
    trade_sound.play()

time.sleep(1)

tick = get_tick()

mode, next_step, lot = place_next_grid(tick.ask, step_count)

log(f"📌 First Grid -> {mode} lot={lot}")

# =========================================================
# IMPORTANT FIX
# =========================================================
positions = my_positions()

last_ticket_set = {p.ticket for p in positions}

# =========================================================
# BASE EQUITY
# =========================================================
account = mt5.account_info()

base_equity = account.equity

# =========================================================
# MAIN LOOP
# =========================================================
while True:

    time.sleep(POLL_SECONDS)

    tick = get_tick()

    if tick is None:
        continue

    mid_price = (tick.ask + tick.bid) / 2

    price_history.append(mid_price)

    # =====================================================
    # DETECT NEW POSITION
    # =====================================================
    positions = my_positions()

    current_ticket_set = {p.ticket for p in positions}

    new_tickets = current_ticket_set - last_ticket_set

    if new_tickets:

        new_positions = [
            p for p in positions
            if p.ticket in new_tickets
        ]

        new_positions.sort(key=lambda x: x.time)

        for new_pos in new_positions:

            step_count += 1

            trade_type = (
                "BUY"
                if new_pos.type == mt5.POSITION_TYPE_BUY
                else "SELL"
            )

            log(
                f"⚡ Triggered -> "
                f"{trade_type} | "
                f"Step={step_count} | "
                f"Volume={new_pos.volume}"
            )

            # ============================================
            # PLAY TRADE SOUND
            # ============================================
            if trade_sound:
                pygame.mixer.stop()
                trade_sound.play()

            # =============================================
            # MAX STEP SAFETY
            # =============================================
            if step_count >= MAX_STEPS:

                log("⚠️ MAX STEPS reached")

                close_all()

                plt.close()

                quit()

            # =============================================
            # PLACE NEXT GRID
            # =============================================
            mode, next_step, lot = place_next_grid(
                new_pos.price_open,
                step_count
            )

            log(
                f"🔁 New Grid -> "
                f"{mode} | "
                f"Lot={lot}"
            )

        last_ticket_set = current_ticket_set

    # =====================================================
    # PROFIT CHECK
    # =====================================================
    acc = mt5.account_info()

    current_profit = acc.equity - base_equity

    if current_profit >= PROFIT_TARGET:

        log(f"🎯 Profit Hit = {current_profit:.2f}")

        close_all()

        plt.close()

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
            linewidth=2,
            label="Price"
        )

        ax.scatter(
            [x[-1]],
            [y[-1]],
            s=80,
            label="Current"
        )

    orders = my_orders()

    for o in orders:

        if o.type == mt5.ORDER_TYPE_BUY_LIMIT:
            color = "green"
            style = "--"
            label = "BUY LIMIT"

        elif o.type == mt5.ORDER_TYPE_BUY_STOP:
            color = "green"
            style = ":"
            label = "BUY STOP"

        elif o.type == mt5.ORDER_TYPE_SELL_LIMIT:
            color = "red"
            style = "--"
            label = "SELL LIMIT"

        elif o.type == mt5.ORDER_TYPE_SELL_STOP:
            color = "red"
            style = ":"
            label = "SELL STOP"

        else:
            color = "gray"
            style = "-."
            label = "OTHER"

        ax.hlines(
            o.price_open,
            0,
            max(1, len(x)),
            colors=color,
            linestyles=style,
            linewidth=2
        )

        ax.text(
            max(1, len(x)),
            o.price_open,
            f"{label} {o.volume_initial:.2f}",
            color=color
        )

    for p in positions:

        if p.type == mt5.POSITION_TYPE_BUY:

            color = "green"
            marker = "^"
            txt = "BUY"

        else:

            color = "red"
            marker = "v"
            txt = "SELL"

        ax.scatter(
            [x[-1]],
            [p.price_open],
            color=color,
            marker=marker,
            s=120
        )

        ax.text(
            x[-1],
            p.price_open,
            f"{txt} {p.volume}",
            color=color
        )

    all_prices = []

    all_prices.extend(y)

    all_prices.extend([o.price_open for o in orders])

    all_prices.extend([p.price_open for p in positions])

    if all_prices:

        ymin = min(all_prices)
        ymax = max(all_prices)

        margin = max((ymax - ymin) * 0.15, GAP * 2)

        ax.set_ylim(
            ymin - margin,
            ymax + margin
        )

    ax.set_title(
        f"{SYMBOL} | "
        f"Step={step_count} | "
        f"Profit={current_profit:.2f}"
    )

    ax.set_xlabel("Ticks")
    ax.set_ylabel("Price")

    ax.grid(True)

    ax.legend()

    ax.text(
        0.01,
        0.98,
        (
            "PATTERN:\n"
            "BUY 0.01 -> SELL 0.02 -> BUY 0.03 -> SELL 0.04 ..."
        ),
        transform=ax.transAxes,
        verticalalignment="top",
        bbox=dict(
            boxstyle="round",
            facecolor="white",
            alpha=0.8
        )
    )

    plt.pause(0.01)

# =========================================================
# CLEANUP
# =========================================================
pygame.quit()
mt5.shutdown()

print("✅ Bot Finished")