import MetaTrader5 as mt5
import pygame
import time
from datetime import datetime

# =========================================================
# CONFIGURATION & MONITORED PARAMETERS
# =========================================================
SYMBOL = "XAUUSD"
MAGIC_P1 = 10001                      # Pattern Magic Number
SLIPPAGE = 100

# Pattern Grid Settings
DEFAULT_GAP = 6.0                     # Main Grid Gap (e.g., 2.0, 3.0, 6.0)
INNER_GAP = 3.0                       # Inner micro-step difference (e.g., 0.5, 1.0, 3.0)
DEFAULT_TARGET_PERCENTAGE = 50.0      # Dynamic profit target percentage
MAX_LOSS_LIMIT = 1000.0               # Max floating loss in USD
MAX_LOT_CAP = 0.50                    # Safety volume cap

# Sound File Paths
PROFIT_SOUND_PATH = r"C:\Users\hp\Downloads\cash-register-purchase-87313.mp3"
LOSS_SOUND_PATH = r"C:\Users\hp\OneDrive\Desktop\python script\loss_automationsound.mp3"

# =========================================================
# PATTERN SEQUENCE DEFINITION (Gap & Inner Gap Multipliers)
# =========================================================
# Format: (Side, Main_Gap_Multiplier, Inner_Gap_Multiplier)
# Step 4 is set to (-2.0 * GAP) + (1.0 * INNER_GAP) so that the distance
# from Step 3 to Step 4 is ALWAYS exactly 1 DEFAULT_GAP regardless of user inputs.
PATTERN_SEQUENCE = [
    ("SELL", -1.0,  0.0),  # Step 2: Base - GAP
    ("BUY",  -1.0,  1.0),  # Step 3: Base - GAP + INNER_GAP
    ("SELL", -2.0,  1.0),  # Step 4: Base - (2 * GAP) + INNER_GAP (1 GAP below Step 3)
    ("BUY",  -1.0,  1.0),  # Step 5: Base - GAP + INNER_GAP
    ("SELL", -1.0,  0.0),  # Step 6: Base - GAP
    ("BUY",   0.0,  0.0),  # Step 7: Base Price
]

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

    print("✅ System Sound Effects Loaded")
except Exception as e:
    print(f"⚠️ UI Sound Load Warning: {e}")
    trade_sound = None
    close_sound = None

# =========================================================
# MT5 INITIALIZATION
# =========================================================
if not mt5.initialize():
    print("❌ MT5 Initialization Failed")
    quit()

mt5.symbol_select(SYMBOL, True)

# =========================================================
# HELPERS & UTILITIES
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
        if trade_sound:
            trade_channel.play(trade_sound)
    except Exception:
        pass

def play_close_sound():
    try:
        if close_sound:
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
        print(f"⚠️ MP3 Audio Error ({file_path}): {e}")

# =========================================================
# POSITION & VOLUME CALCULATIONS
# =========================================================
def get_active_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MAGIC_P1]

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

def get_pattern_order(order_num, base_price, gap=DEFAULT_GAP, inner_gap=INNER_GAP):
    """Calculates order side, volume, and target price using GAP and INNER_GAP."""
    lot_size = min(round(order_num * 0.01, 2), MAX_LOT_CAP)
    seq_idx = (order_num - 2) % len(PATTERN_SEQUENCE)
    side, main_mult, inner_mult = PATTERN_SEQUENCE[seq_idx]
    
    offset = (main_mult * gap) + (inner_mult * inner_gap)
    target_price = round(base_price + offset, 2)
    
    return side, lot_size, target_price

def has_position_of_volume(target_volumes):
    """Checks if any active position matches a specific lot volume."""
    positions = get_active_positions()
    active_vols = {round(p.volume, 2) for p in positions}
    return any(v in active_vols for v in target_volumes)

# =========================================================
# ORDER EXECUTION & PENDING MANAGEMENT
# =========================================================
def cancel_all_pending_orders():
    """Cancels all active pending orders for this strategy."""
    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for o in orders:
            if o.magic == MAGIC_P1:
                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": o.ticket
                }
                res = mt5.order_send(request)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    log(f"✂️ Cancelled pending order #{o.ticket}")

def market_order(side, volume):
    price = ask() if side == "BUY" else bid()
    capped_volume = min(round(volume, 2), MAX_LOT_CAP)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": capped_volume,
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": MAGIC_P1,
        "comment": "STEP_PATTERN_GRID"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"✅ MARKET {side} {capped_volume:.2f} @ {price:.2f}")
        play_trade_sound()
        return price

    log(f"❌ MARKET ORDER FAILED: {result.comment}")
    return None

def place_pending(side, volume, price):
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
        "magic": MAGIC_P1,
        "comment": "STEP_PATTERN_GRID"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"📌 PENDING {side} {capped_volume:.2f} @ {price:.2f}")
        play_trade_sound()
        return result.order

    log(f"❌ Pending Failed {side} {capped_volume:.2f} @ {price:.2f} -> {result.comment}")
    return None

def close_all(is_profit=True):
    log("🚨 EMERGENCY / TARGET TRIGGERED: Closing All Positions & Orders...")

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
                    "deviation": SLIPPAGE,
                    "magic": p.magic
                }
                mt5.order_send(request)

    cancel_all_pending_orders()

    play_close_sound()
    if is_profit:
        play_mp3_sound(PROFIT_SOUND_PATH, repeat=2, label="💰 PROFIT TARGET REACHED")
    else:
        play_mp3_sound(LOSS_SOUND_PATH, repeat=2, label="🛑 MAX LOSS LIMIT REACHED")

    log("✅ ALL POSITIONS AND PENDING ORDERS CLEARED")

# =========================================================
# STAGED PATTERN EXECUTION LOOP
# =========================================================
def run_pattern_cycle(gap, inner_gap, profit_pct, loss_limit):
    # Step 1: Base Market BUY Entry (0.01 Lots)
    base_price = market_order("BUY", 0.01)
    if base_price is None:
        return "FAILED"

    log(f"🎯 Base Entry (Step 1): {base_price:.2f} | GAP: ${gap:.2f} | INNER GAP: ${inner_gap:.2f}")

    # Step 2 & 3: Initial Pending Pair (0.02 Lots & 0.03 Lots)
    s2_side, s2_vol, s2_price = get_pattern_order(2, base_price, gap, inner_gap)
    place_pending(s2_side, s2_vol, s2_price)

    s3_side, s3_vol, s3_price = get_pattern_order(3, base_price, gap, inner_gap)
    place_pending(s3_side, s3_vol, s3_price)

    # State Machine Variables for Staged Order Deployment
    waiting_for_vols = [0.02, 0.03]  # Wait for initial pair trigger
    next_action = "PLACE_SINGLE"
    current_single_step = 4
    current_pair_start = 5

    while True:
        time.sleep(1)

        current_prof = total_profit()
        target_prof = get_target_money_threshold(profit_pct)
        exec_vol = total_executed_volume()

        if exec_vol > 0:
            log(f"Status: Active Vol={exec_vol:.2f} | Profit=${current_prof:.2f} | Target=${target_prof:.2f} | Max Loss=-${loss_limit:.2f}")

        # 1. Target Profit Check
        if target_prof > 0 and current_prof >= target_prof:
            log(f"🎯 TARGET PROFIT HIT -> ${current_prof:.2f} >= ${target_prof:.2f}")
            close_all(is_profit=True)
            return "PROFIT_HIT"

        # 2. Max Loss Safeguard Check
        if current_prof <= -abs(loss_limit):
            log(f"🛑 MAX LOSS TRIGGERED -> ${current_prof:.2f} <= -${abs(loss_limit):.2f}")
            close_all(is_profit=False)
            return "LOSS_HIT"

        # 3. Staged Order Controller Check
        if has_position_of_volume(waiting_for_vols):
            if next_action == "PLACE_SINGLE":
                # Place SINGLE order alone (Step 4 = 0.04, Step 7 = 0.07, etc.)
                step_num = current_single_step
                side, vol, price = get_pattern_order(step_num, base_price, gap, inner_gap)
                
                log(f"🔔 Trigger detected for Vol {waiting_for_vols}! Queueing SINGLE Step {step_num} ({side} {vol:.2f} @ {price:.2f})...")
                place_pending(side, vol, price)

                # Wait specifically for this single order to fill
                waiting_for_vols = [round(vol, 2)]
                next_action = "PLACE_PAIR"
                current_single_step += 3

            elif next_action == "PLACE_PAIR":
                # Place PAIR orders together (Steps 5 & 6 = 0.05 & 0.06, Steps 8 & 9 = 0.08 & 0.09, etc.)
                s1_num = current_pair_start
                s2_num = current_pair_start + 1

                side1, vol1, price1 = get_pattern_order(s1_num, base_price, gap, inner_gap)
                side2, vol2, price2 = get_pattern_order(s2_num, base_price, gap, inner_gap)

                log(f"🔔 Trigger detected for Vol {waiting_for_vols}! Queueing PAIR Steps {s1_num} & {s2_num}...")
                place_pending(side1, vol1, price1)
                place_pending(side2, vol2, price2)

                # Wait for either of these pair orders to fill
                waiting_for_vols = [round(vol1, 2), round(vol2, 2)]
                next_action = "PLACE_SINGLE"
                current_pair_start += 3

# =========================================================
# MAIN EXECUTION CONTROLLER
# =========================================================
if __name__ == "__main__":
    print("=== DUAL-GAP STAGED STEP-PATTERN GRID BOT ===")
    mode_input = input("Select Mode: [1] Manual (Run Once) | [2] Automation (Loop): ").strip()
    is_automated = (mode_input == "2")

    log(f"Starting in {'AUTOMATION' if is_automated else 'MANUAL'} mode | DEFAULT_GAP = {DEFAULT_GAP} | INNER_GAP = {INNER_GAP}...")

    while True:
        result = run_pattern_cycle(
            gap=DEFAULT_GAP,
            inner_gap=INNER_GAP,
            profit_pct=DEFAULT_TARGET_PERCENTAGE,
            loss_limit=MAX_LOSS_LIMIT
        )

        if not is_automated:
            log("Manual run complete. Shutting down bot...")
            break

        if result == "LOSS_HIT":
            log("🛑 BOT SHUT DOWN: Max loss limit hit. Loop halted permanently.")
            break
        elif result == "PROFIT_HIT":
            log("🎯 Target profit reached! Restarting pattern loop in 3 seconds...")
            time.sleep(3)
        elif result == "FAILED":
            log("Initial market order failed. Retrying in 5 seconds...")
            time.sleep(5)