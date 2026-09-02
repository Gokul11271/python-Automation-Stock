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
DEFAULT_TARGET_PERCENTAGE = 100.0  # Dynamic target percentage multiplier

PROFIT_SOUND_PATH = r"C:\Users\hp\Downloads\cash-register-purchase-87313.mp3"

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
    except Exception:
        pass

def play_close_sound():
    try:
        close_channel.play(close_sound)
    except Exception:
        pass

def play_profit_sound(file_path=PROFIT_SOUND_PATH, repeat=2, gap_sec=0.1):
    try:
        pygame.mixer.music.load(file_path)
        for _ in range(repeat):
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            time.sleep(gap_sec)
    except Exception as e:
        print(f"⚠️ Custom sound error: {e}")

# =========================================================
# ACTIVE POSITION METRICS & VOLUME-ONLY TARGET
# =========================================================
def get_active_positions(magic=None):
    """Returns only real executed market positions."""
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    if magic is not None:
        return [p for p in positions if p.magic == magic]
    return [p for p in positions if p.magic in (MAGIC_P1, MAGIC_P2)]

def total_profit():
    positions = get_active_positions()
    return sum(p.profit for p in positions)

def total_executed_volume():
    """Calculates the sum of executed position volumes."""
    positions = get_active_positions()
    return sum(p.volume for p in positions)

def get_target_money_threshold(target_pct):
    """
    Closing Principle:
    Target profit is strictly the accumulation of executed volumes multiplied by percentage.
    Formula: (Sum of Executed Volumes / 0.01) * (DEFAULT_TARGET_PERCENTAGE / 100)
    GAP is NOT used here.
    """
    exec_vol = total_executed_volume()
    if exec_vol <= 0:
        return 0.0
    
    vol_units = round(exec_vol / 0.01, 2)
    unit_target = target_pct / 100.0
    return round(vol_units * unit_target, 2)

# =========================================================
# MARKET ORDER
# =========================================================
def market_order(side, volume, magic):
    price = ask() if side == "BUY" else bid()

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": round(volume, 2),
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": "PATTERN_GRID"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"✅ MARKET {side} {volume:.2f} @ {price:.2f}")
        play_trade_sound()
        return price

    log(f"❌ MARKET ORDER FAILED: {result.comment}")
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
        "volume": round(volume, 2),
        "type": order_type,
        "price": round(price, 2),
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": "PATTERN_GRID"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"📌 {side} {volume:.2f} @ {price:.2f}")
        play_trade_sound()
        return True

    log(f"❌ Pending Failed {side} {volume:.2f} @ {price:.2f} -> {result.comment}")
    return False

# =========================================================
# CLOSE EVERYTHING
# =========================================================
def close_all():
    log("🚨 Closing Everything")

    # CLOSE EXECUTED POSITIONS
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for p in positions:
            if p.magic in (MAGIC_P1, MAGIC_P2):
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = bid() if p.type == mt5.POSITION_TYPE_BUY else ask()

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

    # REMOVE PENDING ORDERS
    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for o in orders:
            if o.magic in (MAGIC_P1, MAGIC_P2):
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": o.ticket
                })

    play_close_sound()
    play_profit_sound()
    log("✅ ALL CLOSED")

# =========================================================
# MAIN
# =========================================================
gap = float(input("Enter Gap: "))
profit_pct = DEFAULT_TARGET_PERCENTAGE

# =========================================================
# PATTERN 1: 1st Pick BUY STATIC (0.01)
# =========================================================
base_buy = market_order("BUY", 0.01, MAGIC_P1)

if base_buy is None:
    quit()

# =========================================================
# PATTERN 2: 1st Pending SELL STATIC (0.01)
# =========================================================
base_sell = round(base_buy + gap, 2)

place_pending("SELL", 0.01, base_sell, MAGIC_P2)

# =========================================================
# PATTERN 1: 1st Ladder SELL (0.02)
# =========================================================
place_pending("SELL", 0.02, round(base_buy - gap, 2), MAGIC_P1)

# =========================================================
# TRACKERS
# =========================================================
last_p1_positions = len(get_active_positions(MAGIC_P1))
last_p2_positions = len(get_active_positions(MAGIC_P2))

# NEXT VOLUMES
p1_volume = 0.03
p2_volume = 0.02

# =========================================================
# DYNAMIC LADDER PRICE LOGIC (SHIFTS BY GAP)
# =========================================================
p1_sell_price = round((base_buy - gap) - gap, 2)  # Pre-calced for 0.04 SELL
p2_buy_price = round(base_sell + gap, 2)           # Pre-calced for 0.02 BUY

# =========================================================
# LOOP
# =========================================================
while True:
    time.sleep(1)

    # =====================================================
    # TARGET PROFIT EVALUATION (Volume Accumulation Only)
    # =====================================================
    current_prof = total_profit()
    target_prof = get_target_money_threshold(profit_pct)
    exec_vol = total_executed_volume()

    if exec_vol > 0:
        log(f"Status: Executed Vol={exec_vol:.2f} | Current Profit=${current_prof:.2f} | Target=${target_prof:.2f}")

    if target_prof > 0 and current_prof >= target_prof:
        log(f"🎯 TARGET PROFIT HIT -> ${current_prof:.2f} >= ${target_prof:.2f} (Total Executed Vol: {exec_vol:.2f})")
        close_all()
        break

    # =====================================================
    # CURRENT EXECUTED POSITIONS
    # =====================================================
    current_p1_positions = len(get_active_positions(MAGIC_P1))
    current_p2_positions = len(get_active_positions(MAGIC_P2))

    # =====================================================
    # PATTERN 1
    # ODD  = BUY STATIC  (base_buy)
    # EVEN = SELL DOWN   (steps down by gap)
    # =====================================================
    if current_p1_positions > last_p1_positions:

        if int(round(p1_volume * 100)) % 2 == 1:
            side = "BUY"
            price = base_buy
        else:
            side = "SELL"
            price = p1_sell_price
            p1_sell_price = round(p1_sell_price - gap, 2)

        place_pending(side, round(p1_volume, 2), price, MAGIC_P1)
        p1_volume = round(p1_volume + 0.01, 2)
        last_p1_positions = current_p1_positions

    # =====================================================
    # PATTERN 2
    # EVEN = BUY UPWARD  (steps up by gap)
    # ODD  = SELL STATIC (base_sell)
    # =====================================================
    if current_p2_positions > last_p2_positions:

        if int(round(p2_volume * 100)) % 2 == 0:
            side = "BUY"
            price = p2_buy_price
            p2_buy_price = round(p2_buy_price + gap, 2)
        else:
            side = "SELL"
            price = base_sell

        place_pending(side, round(p2_volume, 2), price, MAGIC_P2)
        p2_volume = round(p2_volume + 0.01, 2)
        last_p2_positions = current_p2_positions