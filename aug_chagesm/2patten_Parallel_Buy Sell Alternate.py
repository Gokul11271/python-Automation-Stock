import MetaTrader5 as mt5
import pygame
import time
from datetime import datetime

# =========================================================
# CONFIGURATION & MONITORED PARAMETERS
# =========================================================
SYMBOL = "XAUUSD"

MAGIC_P1 = 10001                      # Magic number for Pattern 1 (Downside Chain)
MAGIC_P2 = 10002                      # Magic number for Pattern 2 (Upside Chain)
SLIPPAGE = 100

# Dynamic Gap Settings (Configurable)
INNER_GAP = 3.0                       # Gap between 4150 Market Buy and 4148 / 4152 Levels
OUTER_GAP_1 = 3.0                     # Outer gap expansion (e.g., 4152 -> 4154)
OUTER_GAP_2 = 3.0                     # Second Outer gap expansion tier (e.g., 4154 -> 4156 / 4148 -> 4146)

DEFAULT_TARGET_PERCENTAGE = 50.0      # Profit target per 0.01 lot unit (50%)
MAX_LOSS_LIMIT = 1000.0               # Max floating loss safety limit in USD
MAX_LOT_CAP = 0.50                    # Safety maximum lot volume cap

# Sound File Paths
PROFIT_SOUND_PATH = r"C:\Users\hp\Downloads\cash-register-purchase-87313.mp3"
LOSS_SOUND_PATH = r"C:\Users\hp\OneDrive\Desktop\python script\loss_automationsound.mp3"

# =========================================================
# PATTERN SEQUENCE DEFINITIONS (Exact Gap Multipliers)
# =========================================================
# Format: (Side, Inner_Gap_Mult, Outer_Gap_1_Mult, Outer_Gap_2_Mult)

# Pattern 1 Sequence (Downside Chain - Base Market Entry at P0 = 4150.00)
P1_SEQUENCE = [
    ("SELL", -1.0,  0.0,  0.0),  # Step 2: P0 - IG             -> 4148.00 (SELL 0.02)
    ("BUY",   0.0,  0.0,  0.0),  # Step 3: P0                  -> 4150.00 (BUY 0.03)
    ("SELL", -1.0, -1.0,  0.0),  # Step 4: P0 - IG - OG1       -> 4146.00 (SELL 0.04)
    ("BUY",   0.0,  0.0,  0.0),  # Step 5: P0                  -> 4150.00 (BUY 0.05)
    ("SELL", -1.0,  0.0,  0.0),  # Step 6: P0 - IG             -> 4148.00 (SELL 0.06)
    ("BUY",   0.0,  0.0,  0.0),  # Step 7: P0                  -> 4150.00 (BUY 0.07)
]

# Pattern 2 Sequence (Upside Chain - Initial Pending at P0 + OG1 = 4152.00)
P2_SEQUENCE = [
    ("SELL",  0.0,  1.0,  0.0),  # Step 1: P0 + OG1            -> 4152.00 (SELL 0.01)
    ("BUY",   1.0,  1.0,  0.0),  # Step 2: P0 + OG1 + IG       -> 4154.00 (BUY 0.02)
    ("SELL",  0.0,  1.0,  0.0),  # Step 3: P0 + OG1            -> 4152.00 (SELL 0.03)
    ("BUY",   1.0,  1.0,  1.0),  # Step 4: P0 + OG1 + IG + OG2 -> 4156.00 (BUY 0.04)
    ("SELL",  0.0,  1.0,  0.0),  # Step 5: P0 + OG1            -> 4152.00 (SELL 0.05)
    ("BUY",   1.0,  1.0,  0.0),  # Step 6: P0 + OG1 + IG       -> 4154.00 (BUY 0.06)
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
    print(f"\n[{now()}] {msg}")

def status_log(msg):
    print(f"\r[{now()}] {msg}   ", end="", flush=True)

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
        print(f"\n{label} (×{repeat})")
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
    return [p for p in positions if p.magic in (MAGIC_P1, MAGIC_P2)]

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

def get_p1_order(step_num, base_price, inner_gap=INNER_GAP, og1=OUTER_GAP_1, og2=OUTER_GAP_2):
    """Calculates side, lot size, and target price for Pattern 1 (Step 2 onwards)."""
    lot_size = min(round(step_num * 0.01, 2), MAX_LOT_CAP)
    idx = (step_num - 2) % len(P1_SEQUENCE)
    side, ig_m, og1_m, og2_m = P1_SEQUENCE[idx]
    offset = (ig_m * inner_gap) + (og1_m * og1) + (og2_m * og2)
    target_price = round(base_price + offset, 2)
    return side, lot_size, target_price

def get_p2_order(step_num, base_price, inner_gap=INNER_GAP, og1=OUTER_GAP_1, og2=OUTER_GAP_2):
    """Calculates side, lot size, and target price for Pattern 2 (Step 1 onwards)."""
    lot_size = min(round(step_num * 0.01, 2), MAX_LOT_CAP)
    idx = (step_num - 1) % len(P2_SEQUENCE)
    side, ig_m, og1_m, og2_m = P2_SEQUENCE[idx]
    offset = (ig_m * inner_gap) + (og1_m * og1) + (og2_m * og2)
    target_price = round(base_price + offset, 2)
    return side, lot_size, target_price

# =========================================================
# ORDER EXECUTION & PENDING MANAGEMENT
# =========================================================
def cancel_all_pending_orders():
    """Cancels all active pending orders for both Pattern 1 and Pattern 2."""
    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for o in orders:
            if o.magic in (MAGIC_P1, MAGIC_P2):
                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": o.ticket
                }
                res = mt5.order_send(request)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    log(f"✂️ Cancelled pending order #{o.ticket}")

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
        "comment": "DUAL_PATTERN_GRID"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"✅ MARKET {side} {capped_volume:.2f} @ {price:.2f} (Magic #{magic})")
        play_trade_sound()
        return price, result.order

    log(f"❌ MARKET ORDER FAILED: {result.comment}")
    return None, None

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
        "comment": "DUAL_PATTERN_GRID"
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log(f"📌 PENDING {side} {capped_volume:.2f} @ {price:.2f} (Magic #{magic}, Order #{result.order})")
        play_trade_sound()
        return result.order

    log(f"❌ Pending Failed {side} {capped_volume:.2f} @ {price:.2f} -> {result.comment}")
    return None

def close_all(is_profit=True):
    log("🚨 EMERGENCY / TARGET TRIGGERED: Closing All Positions & Orders...")

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

    cancel_all_pending_orders()

    play_close_sound()
    if is_profit:
        play_mp3_sound(PROFIT_SOUND_PATH, repeat=2, label="💰 PROFIT TARGET REACHED")
    else:
        play_mp3_sound(LOSS_SOUND_PATH, repeat=2, label="🛑 MAX LOSS LIMIT REACHED")

    log("✅ ALL POSITIONS AND PENDING ORDERS CLEARED")

# =========================================================
# DUAL PATTERN EXECUTION CONTROLLER
# =========================================================
def run_pattern_cycle(inner_gap, og1, og2, profit_pct, loss_limit):
    # 1. INITIAL MARKET ENTRY (Pattern 1 Base Entry: BUY 0.01 at P0 = 4150.00)
    base_price, _ = market_order("BUY", 0.01, MAGIC_P1)
    if base_price is None:
        return "FAILED"

    log(f"🎯 Base Entry Price (P0): {base_price:.2f} | INNER_GAP: ${inner_gap:.2f} | OG1: ${og1:.2f} | OG2: ${og2:.2f}")

    # 2. INITIAL PENDING ORDERS (P1 Step 2 @ 4148.00 & P2 Step 1 @ 4152.00)
    p1_step = 2
    p2_step = 1

    log("📌 Placing Initial Pending Orders for Pattern 1 and Pattern 2...")

    # Pattern 1 Initial Pending (Step 2: SELL 0.02 @ P0 - IG = 4148.00)
    s1, v1, p1 = get_p1_order(p1_step, base_price, inner_gap, og1, og2)
    p1_ticket = place_pending(s1, v1, p1, MAGIC_P1)
    p1_step += 1

    # Pattern 2 Initial Pending (Step 1: SELL 0.01 @ P0 + OG1 = 4152.00)
    s2, v2, p2 = get_p2_order(p2_step, base_price, inner_gap, og1, og2)
    p2_ticket = place_pending(s2, v2, p2, MAGIC_P2)
    p2_step += 1

    last_logged_vol = None

    # 3. INDEPENDENT STAGED EXECUTION MONITORING
    while True:
        time.sleep(1)

        current_prof = total_profit()
        target_prof = get_target_money_threshold(profit_pct)
        exec_vol = total_executed_volume()

        # Dynamic Status Line: Updates in-place, breaks new line ONLY when lot volume changes
        if exec_vol > 0:
            if last_logged_vol is not None and exec_vol != last_logged_vol:
                print()  # Break line when volume level shifts
            
            last_logged_vol = exec_vol
            status_log(f"Status: Active Vol={exec_vol:.2f} | Profit=${current_prof:.2f} | Target=${target_prof:.2f} | Max Loss=-${loss_limit:.2f}")

        # Profit Target Check
        if target_prof > 0 and current_prof >= target_prof:
            log(f"🎯 TARGET PROFIT HIT -> ${current_prof:.2f} >= ${target_prof:.2f}")
            close_all(is_profit=True)
            return "PROFIT_HIT"

        # Max Loss Safeguard Check
        if current_prof <= -abs(loss_limit):
            log(f"🛑 MAX LOSS TRIGGERED -> ${current_prof:.2f} <= -${abs(loss_limit):.2f}")
            close_all(is_profit=False)
            return "LOSS_HIT"

        # Active position tickets set (handles ticket mapping)
        active_positions = get_active_positions()
        active_pos_tickets = {p.ticket for p in active_positions} | {getattr(p, 'identifier', p.ticket) for p in active_positions}

        # Pattern 1 Pending Order Trigger Check
        if p1_ticket and p1_ticket in active_pos_tickets:
            log(f"🔔 Pattern 1 Pending Order #{p1_ticket} Triggered! Queueing Step {p1_step}...")
            side, vol, price = get_p1_order(p1_step, base_price, inner_gap, og1, og2)
            p1_ticket = place_pending(side, vol, price, MAGIC_P1)
            p1_step += 1

        # Pattern 2 Pending Order Trigger Check
        if p2_ticket and p2_ticket in active_pos_tickets:
            log(f"🔔 Pattern 2 Pending Order #{p2_ticket} Triggered! Queueing Step {p2_step}...")
            side, vol, price = get_p2_order(p2_step, base_price, inner_gap, og1, og2)
            p2_ticket = place_pending(side, vol, price, MAGIC_P2)
            p2_step += 1

# =========================================================
# MAIN EXECUTION CONTROLLER
# =========================================================
if __name__ == "__main__":
    print("=== DUAL PATTERN (P1 & P2 DYNAMIC GAP GRID) BOT ===")
    mode_input = input("Select Mode: [1] Manual (Run Once) | [2] Automation (Loop): ").strip()
    is_automated = (mode_input == "2")

    log(f"Starting in {'AUTOMATION' if is_automated else 'MANUAL'} mode | INNER = {INNER_GAP} | OG1 = {OUTER_GAP_1} | OG2 = {OUTER_GAP_2}...")

    while True:
        result = run_pattern_cycle(
            inner_gap=INNER_GAP,
            og1=OUTER_GAP_1,
            og2=OUTER_GAP_2,
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