import MetaTrader5 as mt5
import pygame
import time
from datetime import datetime

# =========================================================
# CONFIGURATION & DEFAULT VARIABLES
# =========================================================
SYMBOL = "XAUUSD"

MAGIC_P1 = 10001
MAGIC_P2 = 10002
SLIPPAGE = 100

# Grid Parameters
DEFAULT_GAP = 3.0                   # Starting gap in USD/Points
GAP_INCREMENT = 3.0                 # Gap expansion per sell step
MAX_GAP_CAP = 6.0                  # Maximum distance cap between levels

# Profit & Risk Limits
DEFAULT_TARGET_PERCENTAGE = 50      # Dynamic target profit percentage
STATIC_TARGET_PROFIT = 500.0         # Fallback fixed target in USD
MAX_LOSS_LIMIT = 1000.0             # Max floating loss limit in USD (bot stops if hit)
MAX_LOT_CAP = 0.50                  # Maximum lot size allowed per order

# Audio File Paths
PROFIT_SOUND_PATH = r"C:\Users\hp\Downloads\cash-register-purchase-87313.mp3"
LOSS_SOUND_PATH = r"C:\Users\hp\OneDrive\Desktop\python script\loss_automationsound.mp3"

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

    print("✅ System Sounds Loaded")
except Exception as e:
    print(f"⚠️ System Sound Load Failed: {e}")

# =========================================================
# MT5 INITIALIZATION
# =========================================================
if not mt5.initialize():
    print("❌ MT5 Initialization Failed")
    quit()

mt5.symbol_select(SYMBOL, True)

# =========================================================
# HELPER FUNCTIONS
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
# AUDIO PLAYBACK FUNCTIONS
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

def play_mp3_sound(file_path, repeat=2, gap_sec=0.1, label="🔊 Sound"):
    try:
        print(f"{label} (×{repeat})")
        pygame.mixer.music.load(file_path)
        for _ in range(repeat):
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            time.sleep(gap_sec)
    except Exception as e:
        print(f"⚠️ Custom sound audio error: {e}")

# =========================================================
# POSITION & VOLUME METRICS
# =========================================================
def get_active_positions(magic=None):
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    if magic is None:
        return [p for p in positions if p.magic in (MAGIC_P1, MAGIC_P2)]
    return [p for p in positions if p.magic == magic]

def position_count(magic):
    return len(get_active_positions(magic))

def total_profit():
    positions = get_active_positions()
    return sum(p.profit for p in positions)

def total_executed_volume():
    positions = get_active_positions()
    return sum(p.volume for p in positions)

def get_target_money_threshold(target_pct):
    exec_vol = total_executed_volume()
    if exec_vol <= 0:
        return STATIC_TARGET_PROFIT
    vol_units = round(exec_vol / 0.01, 2)
    unit_target = target_pct / 100.0
    dynamic_target = round(vol_units * unit_target, 2)
    return max(dynamic_target, STATIC_TARGET_PROFIT)

# =========================================================
# TRADE EXECUTION FUNCTIONS
# =========================================================
def market_order(side, volume, magic):
    price = ask() if side == "BUY" else bid()
    capped_volume = min(round(volume, 2), MAX_LOT_CAP)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": capped_volume,
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": f"PATTERN_GRID_P{1 if magic==MAGIC_P1 else 2}"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"✅ MARKET {side} {capped_volume:.2f} @ {price:.2f} (Magic: {magic})")
        play_trade_sound()
        return price

    log(f"❌ MARKET ORDER FAILED: {result.comment}")
    return None

def place_pending(side, volume, price, magic):
    current_ask = ask()
    current_bid = bid()
    capped_volume = min(round(volume, 2), MAX_LOT_CAP)

    if side == "BUY":
        order_type = mt5.ORDER_TYPE_BUY_STOP if price > current_ask else mt5.ORDER_TYPE_BUY_LIMIT
    else:
        order_type = mt5.ORDER_TYPE_SELL_STOP if price < current_bid else mt5.ORDER_TYPE_SELL_LIMIT

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": capped_volume,
        "type": order_type,
        "price": round(price, 2),
        "deviation": SLIPPAGE,
        "magic": magic,
        "comment": f"PATTERN_GRID_P{1 if magic==MAGIC_P1 else 2}"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"📌 PENDING {side} {capped_volume:.2f} @ {price:.2f} (Magic: {magic})")
        play_trade_sound()
        return result.order

    log(f"❌ Pending Failed {side} {capped_volume:.2f} @ {price:.2f} -> {result.comment}")
    return None

def close_all(is_profit=True):
    log("🚨 Closing All Positions & Removing Pending Orders...")

    # Close Open Positions
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
                    "deviation": SLIPPAGE,
                    "magic": p.magic
                }
                mt5.order_send(request)

    # Cancel Pending Orders
    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for o in orders:
            if o.magic in (MAGIC_P1, MAGIC_P2):
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": o.ticket
                })

    play_close_sound()
    if is_profit:
        play_mp3_sound(PROFIT_SOUND_PATH, repeat=2, label="💰 Profit Target Hit Sound")
    else:
        play_mp3_sound(LOSS_SOUND_PATH, repeat=2, label="🛑 Max Loss Limit Sound")
    
    log("✅ ALL POSITIONS & ORDERS CLOSED")

# =========================================================
# DUAL-PATTERN CYCLE LOGIC
# =========================================================
def run_dual_pattern_cycle(gap, gap_inc, max_gap, profit_pct, loss_limit):
    # Base Market Buy (Pattern 1 Initialization)
    base_buy = market_order("BUY", 0.01, MAGIC_P1)
    if base_buy is None:
        return "FAILED"

    base_sell = base_buy + gap

    # Pattern 2 Initial Sell
    place_pending("SELL", 0.01, base_sell, MAGIC_P2)

    # Pattern 1 Initial Sell (Gap downward)
    place_pending("SELL", 0.02, base_buy - gap, MAGIC_P1)

    # Trackers
    last_p1_positions = position_count(MAGIC_P1)
    last_p2_positions = position_count(MAGIC_P2)

    p1_volume = 0.03
    p2_volume = 0.02

    p1_sell_level = 2
    p2_buy_level = 1

    current_p1_gap = gap
    current_p2_gap = gap

    while True:
        time.sleep(1)

        current_prof = total_profit()
        target_prof = get_target_money_threshold(profit_pct)
        exec_vol = total_executed_volume()

        if exec_vol > 0:
            log(f"Status: Vol={exec_vol:.2f} | Profit=${current_prof:.2f} | Target=${target_prof:.2f} | Loss Limit=-${loss_limit:.2f}")

        # 1. Target Profit Protection
        if target_prof > 0 and current_prof >= target_prof:
            log(f"🎯 TARGET PROFIT HIT -> ${current_prof:.2f} >= ${target_prof:.2f}")
            close_all(is_profit=True)
            return "PROFIT_HIT"

        # 2. Max Loss Limit Protection
        if current_prof <= -abs(loss_limit):
            log(f"🛑 MAX LOSS LIMIT HIT -> ${current_prof:.2f} <= -${abs(loss_limit):.2f}")
            close_all(is_profit=False)
            return "LOSS_HIT"

        # Position Checks
        current_p1_positions = position_count(MAGIC_P1)
        current_p2_positions = position_count(MAGIC_P2)

        # -----------------------------------------------------
        # PATTERN 1 TRIGGER
        # -----------------------------------------------------
        if current_p1_positions > last_p1_positions:
            # Odd Volume Step = Buy Fixed
            if int(round(p1_volume * 100)) % 2 == 1:
                side = "BUY"
                price = base_buy
            # Even Volume Step = Sell Downward with Gap Expansion
            else:
                side = "SELL"
                current_p1_gap = min(round(current_p1_gap + gap_inc, 2), max_gap)
                price = base_buy - current_p1_gap
                p1_sell_level += 1

            place_pending(side, p1_volume, price, MAGIC_P1)
            p1_volume += 0.01
            last_p1_positions = current_p1_positions

        # -----------------------------------------------------
        # PATTERN 2 TRIGGER
        # -----------------------------------------------------
        if current_p2_positions > last_p2_positions:
            # Even Volume Step = Buy Upward with Gap Expansion
            if int(round(p2_volume * 100)) % 2 == 0:
                side = "BUY"
                current_p2_gap = min(round(current_p2_gap + gap_inc, 2), max_gap)
                price = base_sell + current_p2_gap
                p2_buy_level += 1
            # Odd Volume Step = Sell Fixed
            else:
                side = "SELL"
                price = base_sell

            place_pending(side, p2_volume, price, MAGIC_P2)
            p2_volume += 0.01
            last_p2_positions = current_p2_positions

# =========================================================
# MAIN EXECUTION CONTROLLER
# =========================================================
if __name__ == "__main__":
    print("=== DUAL-PATTERN TRADING BOT CONTROLLER ===")
    user_gap = input(f"Enter Starting Gap (Press Enter for Default {DEFAULT_GAP}): ").strip()
    starting_gap = float(user_gap) if user_gap else DEFAULT_GAP

    mode_input = input("Select Mode: [1] Manual (Run Once) | [2] Automation (Loop): ").strip()
    is_automated = (mode_input == "2")

    log(f"Starting in {'AUTOMATION' if is_automated else 'MANUAL'} mode with Gap = {starting_gap}...")

    while True:
        result = run_dual_pattern_cycle(
            gap=starting_gap,
            gap_inc=GAP_INCREMENT,
            max_gap=MAX_GAP_CAP,
            profit_pct=DEFAULT_TARGET_PERCENTAGE,
            loss_limit=MAX_LOSS_LIMIT
        )

        # Mode 1: Manual Mode
        if not is_automated:
            log("Manual cycle complete. Shutting down bot...")
            break

        # Mode 2: Automation Logic
        if result == "LOSS_HIT":
            log("🛑 BOT HALTED: Max loss threshold reached. Automation stopped permanently.")
            break
        elif result == "PROFIT_HIT":
            log("🎯 Target profit reached! Restarting dual-pattern cycle in 3 seconds...")
            time.sleep(3)
        elif result == "FAILED":
            log("Order execution failed. Retrying cycle in 5 seconds...")
            time.sleep(5)