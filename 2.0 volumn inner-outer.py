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
LOT_INCREMENT = 0.01  # Linear scaling: 0.01 -> 0.02 -> 0.03...

PROFIT_TARGET = 100

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
# VOLUME SEQUENCE TRACKING
# =========================================================
current_volume = 0.01  

def get_next_volume(vol):
    return round(vol + LOT_INCREMENT, 2)

# =========================================================
# CORE MT5 HELPERS
# =========================================================
def now():
    return datetime.now().strftime("%H:%M:%S")

def log(*msg):
    print(f"[{now()}]", *msg)

def normalize(price):
    return round(price, DIGITS)

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
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        return None
    return result

# =========================================================
# CLEANUP TOOLS
# =========================================================
def cancel_all_pending():
    orders = my_orders()
    for o in orders:
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})

def cancel_opposite_side_outer_pending(hit_level, mid_point):
    """Wipes out any active pending orders on the entire opposite hemisphere."""
    orders = my_orders()
    for o in orders:
        if hit_level == "LOW" and o.price_open > mid_point:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
            log(f"🧹 Closed upper opposite pending order at {o.price_open}")
        elif hit_level == "HIGH" and o.price_open < mid_point:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
            log(f"🧹 Closed lower opposite pending order at {o.price_open}")

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

        price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
        close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY

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

    cancel_all_pending()
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

        ask, bid = tick.ask, tick.bid
        adjusted_price = normalize(target_price + shift) if direction == "BUY" else normalize(target_price - shift)

        if direction == "BUY":
            order_type = mt5.ORDER_TYPE_BUY_STOP if adjusted_price > ask else mt5.ORDER_TYPE_BUY_LIMIT
        else:
            order_type = mt5.ORDER_TYPE_SELL_STOP if adjusted_price < bid else mt5.ORDER_TYPE_SELL_LIMIT

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
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            log(f"✅ Pending {direction} {adjusted_price} lot={lot}")
            return result

        shift += tick_size
        log(f"⏳ Shift Retry {direction} {adjusted_price}")
        time.sleep(0.2)

# =========================================================
# INPUT
# =========================================================
INNER_GAP = float(input("Enter Inner Gap : "))
OUTER_GAP = float(input("Enter Outer Gap : "))

# =========================================================
# INITIAL SETUP MATRIX
# =========================================================
tick = get_tick()
if tick is None:
    raise RuntimeError("No market price available")

GRID_MID_LOW = normalize(tick.ask) 
GRID_MID_HIGH = normalize(GRID_MID_LOW + INNER_GAP)
GRID_HIGH = normalize(GRID_MID_HIGH + OUTER_GAP)
GRID_LOW = normalize(GRID_MID_LOW - OUTER_GAP)

GRID_CENTER = (GRID_MID_HIGH + GRID_MID_LOW) / 2

log("📌 GRID LEVELS CALCULATED")
log(f"TOP (HIGH)       : {GRID_HIGH}")
log(f"OUTER HIGH       : {GRID_MID_HIGH}")
log(f"INNER FIRST BUY  : {GRID_MID_LOW}")
log(f"BOTTOM (LOW)     : {GRID_LOW}")

# =========================================================
# INITIALIZE STEP 1 (Three matching 0.01 volume tiers)
# =========================================================
log(f"🚀 Initial BUY lot={current_volume} triggered at Inner Level")

buy_result = market_buy(current_volume)
if buy_result is None:
    raise RuntimeError("❌ Initial BUY failed")

if trade_sound:
    pygame.mixer.stop()
    trade_sound.play()

time.sleep(1)

# Places initial protection layouts
place_pending("SELL", GRID_MID_HIGH, 0.01)         
place_pending("SELL", GRID_LOW, 0.02)              

# =========================================================
# BASE RUN STATE
# =========================================================
known_tickets = set()
for p in my_positions():
    known_tickets.add(p.ticket)

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
        price_history.append((tick.ask + tick.bid) / 2)

    latest_pos = get_latest_position()

    if latest_pos and latest_pos.ticket not in known_tickets:
        known_tickets.add(latest_pos.ticket)
        pos = latest_pos

        trade_type = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
        log(f"⚡ Triggered {trade_type} lot={pos.volume}")

        if trade_sound:
            pygame.mixer.stop()
            trade_sound.play()

        levels = {
            GRID_LOW: "LOW",
            GRID_MID_LOW: "MID_LOW",
            GRID_MID_HIGH: "MID_HIGH",
            GRID_HIGH: "HIGH"
        }
        nearest = min(levels.keys(), key=lambda x: abs(x - pos.price_open))
        level_name = levels[nearest]
        log(f"📍 Market Breached Level={level_name}")

        is_inner_level = level_name in ["MID_LOW", "MID_HIGH"]

        # -----------------------------------------------------------
        # RULE 1: INNER GRID HIT -> RETAIN LAYERS
        # -----------------------------------------------------------
        if is_inner_level:
            log(f"ℹ️ Inner level hit ({pos.volume}). Retaining all layers untouched.")
            
            lot_to_place = current_volume
            if abs(pos.volume - 0.01) < 0.0001 and len(my_positions()) <= 2:
                lot_to_place = 0.01
            
            if pos.type == mt5.POSITION_TYPE_SELL: 
                place_pending("BUY", GRID_HIGH, lot_to_place)
            else: 
                place_pending("SELL", GRID_LOW, lot_to_place)

        # -----------------------------------------------------------
        # RULE 2: OUTER GRID HIT -> REMOVE OPPOSITE PENALTY LAYERS
        # -----------------------------------------------------------
        else:
            log(f"🚨 Outer level hit ({pos.volume}). Clearing the whole opposite side.")
            
            # Wipes opposing structures cleanly using matched function call
            cancel_opposite_side_outer_pending(level_name, GRID_CENTER)
            
            if abs(pos.volume - 0.02) < 0.001 and current_volume == 0.01:
                current_volume = 0.02
            else:
                current_volume = get_next_volume(current_volume)
                
            log(f"🔄 Sequence Advanced: Next Volume Matrix Tier = {current_volume}")

            if pos.type == mt5.POSITION_TYPE_SELL: 
                place_pending("BUY", GRID_MID_LOW, current_volume)
                place_pending("SELL", GRID_MID_HIGH, current_volume)
            else: 
                place_pending("SELL", GRID_MID_HIGH, current_volume)
                place_pending("BUY", GRID_MID_LOW, current_volume)

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
        ax.plot(x, y, linewidth=1.5)
    for lvl in [GRID_LOW, GRID_MID_LOW, GRID_MID_HIGH, GRID_HIGH]:
        ax.hlines(lvl, 0, max(1, len(x)), linewidth=1)

    ax.set_title(f"Profit={current_profit:.2f} | Vol Tier={current_volume}", fontsize=8)
    ax.grid(True)
    plt.tight_layout()
    plt.pause(0.01)

plt.close()
pygame.quit()
mt5.shutdown()