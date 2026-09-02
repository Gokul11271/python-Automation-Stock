import MetaTrader5 as mt5
import pygame
import time
from datetime import datetime

# =========================================================
# CONFIGURATION & DEFAULT VARIABLES
# =========================================================
SYMBOL = "XAUUSD"
MAGIC_P1 = 10001
SLIPPAGE = 100

DEFAULT_GAP = 2.0                    # Default gap size
DEFAULT_TARGET_PERCENTAGE = 80.0   # Dynamic profit percentage
MAX_LOSS_LIMIT = 500.0               # Max floating loss in USD (stops bot if hit)
MAX_LOT_CAP = 0.50                  # Volume cap (stays at 0.10 after step 10)

PROFIT_SOUND_PATH = r"C:\Users\hp\Downloads\cash-register-purchase-87313.mp3"

# =========================================================
# SOUND INITIALIZATION
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
# MT5 INITIALIZATION
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
# ACTIVE POSITION METRICS
# =========================================================
def get_active_positions(magic=MAGIC_P1):
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    return [p for p in positions if p.magic == magic]

def total_profit():
    positions = get_active_positions()
    return sum(p.profit for p in positions)

def total_executed_volume():
    positions = get_active_positions()
    return sum(p.volume for p in positions)

def get_target_money_threshold(target_pct):
    exec_vol = total_executed_volume()
    if exec_vol <= 0:
        return 0.0
    vol_units = round(exec_vol / 0.01, 2)
    unit_target = target_pct / 100.0
    return round(vol_units * unit_target, 2)

# =========================================================
# ORDER FUNCTIONS
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

def place_pending(side, volume, price, magic):
    current_ask = ask()
    current_bid = bid()

    if side == "BUY":
        order_type = mt5.ORDER_TYPE_BUY_STOP if price > current_ask else mt5.ORDER_TYPE_BUY_LIMIT
    else:
        order_type = mt5.ORDER_TYPE_SELL_STOP if price < current_bid else mt5.ORDER_TYPE_SELL_LIMIT

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

def close_all(is_profit=True):
    log("🚨 Closing Everything")

    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for p in positions:
            if p.magic == MAGIC_P1:
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

    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for o in orders:
            if o.magic == MAGIC_P1:
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": o.ticket
                })

    play_close_sound()
    if is_profit:
        play_profit_sound()
    log("✅ ALL CLOSED")

# =========================================================
# STRATEGY RUN CYCLE
# =========================================================
def run_strategy_cycle(gap, profit_pct, loss_limit):
    base_buy = market_order("BUY", 0.01, MAGIC_P1)
    if base_buy is None:
        return "FAILED"

    # Initial pending sell for Pattern 1
    place_pending("SELL", 0.02, round(base_buy - gap, 2), MAGIC_P1)

    last_p1_positions = len(get_active_positions(MAGIC_P1))
    
    current_step = 3
    p1_sell_price = round((base_buy - gap) - gap, 2)

    while True:
        time.sleep(1)

        current_prof = total_profit()
        target_prof = get_target_money_threshold(profit_pct)
        exec_vol = total_executed_volume()

        if exec_vol > 0:
            log(f"Status: Executed Vol={exec_vol:.2f} | Profit=${current_prof:.2f} | Target=${target_prof:.2f} | Max Loss=-${loss_limit:.2f}")

        # Target Profit Hit
        if target_prof > 0 and current_prof >= target_prof:
            log(f"🎯 TARGET PROFIT HIT -> ${current_prof:.2f} >= ${target_prof:.2f}")
            close_all(is_profit=True)
            return "PROFIT_HIT"

        # Max Loss Limit Hit
        if current_prof <= -abs(loss_limit):
            log(f"🛑 MAX LOSS LIMIT HIT -> ${current_prof:.2f} <= -${abs(loss_limit):.2f}")
            close_all(is_profit=False)
            return "LOSS_HIT"

        # Position tracking and next order placement
        current_p1_positions = len(get_active_positions(MAGIC_P1))

        if current_p1_positions > last_p1_positions:
            raw_vol = round(current_step * 0.01, 2)
            assigned_volume = min(raw_vol, MAX_LOT_CAP)

            # Odd = Buy Static | Even = Sell Downward
            if current_step % 2 == 1:
                side = "BUY"
                price = base_buy
            else:
                side = "SELL"
                price = p1_sell_price
                p1_sell_price = round(p1_sell_price - gap, 2)

            place_pending(side, assigned_volume, price, MAGIC_P1)
            
            current_step += 1
            last_p1_positions = current_p1_positions

# =========================================================
# MAIN EXECUTION CONTROLLER
# =========================================================
print("=== TRADING BOT CONTROLLER ===")
mode_input = input("Select Mode: [1] Manual (Run Once) | [2] Automation (Loop): ").strip()
is_automated = (mode_input == "2")

log(f"Starting in {'AUTOMATION' if is_automated else 'MANUAL'} mode...")

while True:
    result = run_strategy_cycle(DEFAULT_GAP, DEFAULT_TARGET_PERCENTAGE, MAX_LOSS_LIMIT)
    
    # Mode 1: Manual Mode (Always exits after 1 cycle)
    if not is_automated:
        log("Manual run complete. Shutting down bot...")
        break
    
    # Mode 2: Automation Mode Logic
    if result == "LOSS_HIT":
        log("🛑 BOT SHUT DOWN: Max loss threshold reached. Loop halted permanently to protect account.")
        break
    
    elif result == "PROFIT_HIT":
        log("🎯 Target profit reached! Restarting loop in 3 seconds...")
        time.sleep(3)
        
    elif result == "FAILED":
        log("Initial order execution failed. Retrying in 5 seconds...")
        time.sleep(5)