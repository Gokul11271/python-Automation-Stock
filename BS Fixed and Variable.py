import MetaTrader5 as mt5
import pygame
import time
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================
SYMBOL = "XAUUSD"

MAGIC_P1 = 10001
MAGIC_P2 = 10002

SLIPPAGE = 100
TARGET_PROFIT = 500

# =========================================================
# SOUND INIT
# =========================================================
pygame.init()
pygame.mixer.init()

try:

    trade_sound = pygame.mixer.Sound("tradewave.mp3")
    close_sound = pygame.mixer.Sound("closewave.mp3")

    trade_channel = pygame.mixer.Channel(0)
    close_channel = pygame.mixer.Channel(1)

    trade_sound.set_volume(1.0)
    close_sound.set_volume(1.0)

    print("✅ Sounds Loaded")

except Exception as e:

    print("❌ Sound Load Failed")
    print(e)
    quit()

# =========================================================
# MT5 INIT
# =========================================================
if not mt5.initialize():

    print("❌ MT5 Init Failed")
    quit()

mt5.symbol_select(SYMBOL, True)

# =========================================================
# HELPERS
# =========================================================
def now():
    return datetime.now().strftime("%H:%M:%S")

def log(msg):
    print(f"[{now()}] {msg}")

def ask():
    return mt5.symbol_info_tick(SYMBOL).ask

def bid():
    return mt5.symbol_info_tick(SYMBOL).bid

# =========================================================
# SOUND FUNCTIONS
# =========================================================
def play_trade_sound():

    try:
        trade_channel.play(trade_sound)
    except:
        pass

def play_close_sound():

    try:
        close_channel.play(close_sound)
    except:
        pass

# =========================================================
# POSITION COUNT
# =========================================================
def position_count(magic):

    positions = mt5.positions_get(symbol=SYMBOL)

    if positions is None:
        return 0

    return len([p for p in positions if p.magic == magic])

# =========================================================
# TOTAL PROFIT
# =========================================================
def total_profit():

    positions = mt5.positions_get(symbol=SYMBOL)

    if positions is None:
        return 0

    return sum(p.profit for p in positions)

# =========================================================
# MARKET ORDER
# =========================================================
def market_order(side, volume, magic):

    price = ask() if side == "BUY" else bid()

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": "PATTERN_GRID"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:

        log(f"✅ MARKET {side} {volume} @ {price}")

        play_trade_sound()

        return price

    log("❌ MARKET ORDER FAILED")

    return None

# =========================================================
# PENDING ORDER
# =========================================================
def place_pending(side, volume, price, magic):

    current_ask = ask()
    current_bid = bid()

    # BUY
    if side == "BUY":

        if price > current_ask:
            order_type = mt5.ORDER_TYPE_BUY_STOP
        else:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT

    # SELL
    else:

        if price < current_bid:
            order_type = mt5.ORDER_TYPE_SELL_STOP
        else:
            order_type = mt5.ORDER_TYPE_SELL_LIMIT

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": "PATTERN_GRID"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:

        log(f"📌 {side} {volume} @ {price}")

        play_trade_sound()

        return True

    log(f"❌ Pending Failed {side} {volume}")

    return False

# =========================================================
# CLOSE EVERYTHING
# =========================================================
def close_all():

    log("🚨 Closing Everything")

    # CLOSE POSITIONS
    positions = mt5.positions_get(symbol=SYMBOL)

    if positions:

        for p in positions:

            if p.type == mt5.POSITION_TYPE_BUY:

                close_type = mt5.ORDER_TYPE_SELL
                price = bid()

            else:

                close_type = mt5.ORDER_TYPE_BUY
                price = ask()

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "position": p.ticket,
                "volume": p.volume,
                "type": close_type,
                "price": price,
                "deviation": SLIPPAGE
            }

            mt5.order_send(request)

    # REMOVE PENDING
    orders = mt5.orders_get(symbol=SYMBOL)

    if orders:

        for o in orders:

            mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": o.ticket
            })

    play_close_sound()

    log("✅ ALL CLOSED")

# =========================================================
# MAIN
# =========================================================
gap = float(input("Enter Gap: "))

# =========================================================
# PATTERN 1
# BUY STATIC
# SELL DOWNWARD
# =========================================================
base_buy = market_order(
    "BUY",
    0.01,
    MAGIC_P1
)

if base_buy is None:
    quit()

# =========================================================
# PATTERN 2
# SELL STATIC
# BUY UPWARD
# =========================================================
base_sell = base_buy + gap

# =========================================================
# INITIAL ORDERS
# =========================================================

# Pattern 2 initial SELL
place_pending(
    "SELL",
    0.01,
    base_sell,
    MAGIC_P2
)

# Pattern 1 initial SELL
place_pending(
    "SELL",
    0.02,
    base_buy - gap,
    MAGIC_P1
)

# =========================================================
# TRACKERS
# =========================================================
last_p1_positions = position_count(MAGIC_P1)
last_p2_positions = position_count(MAGIC_P2)

# NEXT VOLUMES
p1_volume = 0.03
p2_volume = 0.02

# =========================================================
# PRICE LOGIC
# =========================================================

# Pattern 1
# 0.02 = base-gap
# 0.04 = previous-1
# 0.06 = previous-1

p1_sell_price = (base_buy - gap) - 1

# Pattern 2
# 0.02 = base+gap
# 0.04 = previous+1
# 0.06 = previous+1

p2_buy_price = base_sell + gap

# =========================================================
# LOOP
# =========================================================
while True:

    time.sleep(1)

    # =====================================================
    # TARGET HIT
    # =====================================================
    if total_profit() >= TARGET_PROFIT:

        log("🎯 TARGET HIT")

        close_all()

        break

    # =====================================================
    # CURRENT POSITIONS
    # =====================================================
    current_p1_positions = position_count(MAGIC_P1)
    current_p2_positions = position_count(MAGIC_P2)

    # =====================================================
    # PATTERN 1
    # BUY STATIC
    # SELL DOWN
    # =====================================================
    if current_p1_positions > last_p1_positions:

        # ODD = BUY STATIC
        if int(p1_volume * 100) % 2 == 1:

            side = "BUY"

            price = base_buy

        # EVEN = SELL DOWNWARD
        else:

            side = "SELL"

            price = p1_sell_price

            # continue -1
            p1_sell_price -= 1

        place_pending(
            side,
            round(p1_volume, 2),
            price,
            MAGIC_P1
        )

        p1_volume += 0.01

        last_p1_positions = current_p1_positions

    # =====================================================
    # PATTERN 2
    # SELL STATIC
    # BUY UP
    # =====================================================
    if current_p2_positions > last_p2_positions:

        # EVEN = BUY UPWARD
        if int(p2_volume * 100) % 2 == 0:

            side = "BUY"

            price = p2_buy_price

            # continue +1
            p2_buy_price += 1

        # ODD = SELL STATIC
        else:

            side = "SELL"

            price = base_sell

        place_pending(
            side,
            round(p2_volume, 2),
            price,
            MAGIC_P2
        )

        p2_volume += 0.01

        last_p2_positions = current_p2_positions