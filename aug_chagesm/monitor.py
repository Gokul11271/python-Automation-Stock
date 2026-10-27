import MetaTrader5 as mt5
import pygame
import time
from datetime import datetime

# =========================================================
# CONFIGURATION & MONITORED PARAMETERS
# =========================================================
SYMBOL = "XAUUSD"
SLIPPAGE = 100

# Risk & Profit Rules
DEFAULT_TARGET_PERCENTAGE = 100.0      # Dynamic profit target percentage
MAX_LOSS_LIMIT = 1000.0               # Max floating loss in USD (closes all & halts monitor if hit)

# Trade Monitoring Scope
# Set to True to monitor ALL manual trades (magic = 0) and EA trades on SYMBOL
MONITOR_ALL_TRADES = True
SPECIFIC_MAGIC = 10001                # Used if MONITOR_ALL_TRADES is set to False

# Sound File Paths
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

    print("✅ System Sound Effects Loaded")
except Exception as e:
    print(f"⚠️ UI Sound Load Warning (Continuing without short chimes): {e}")
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
    if MONITOR_ALL_TRADES:
        return list(positions)
    return [p for p in positions if p.magic == SPECIFIC_MAGIC]

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
# CLOSE ALL POSITIONS & PENDING ORDERS
# =========================================================
def close_all(is_profit=True):
    log("🚨 EMERGENCY / TARGET TRIGGERED: Closing All Positions & Orders...")

    # Close Open Positions
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for p in positions:
            if MONITOR_ALL_TRADES or p.magic == SPECIFIC_MAGIC:
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
                result = mt5.order_send(request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    log(f"✅ Closed Position #{p.ticket} ({p.volume} lots)")
                else:
                    log(f"❌ Failed to close #{p.ticket}: {result.comment}")

    # Remove Pending Orders
    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for o in orders:
            if MONITOR_ALL_TRADES or o.magic == SPECIFIC_MAGIC:
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": o.ticket
                })
                log(f"📌 Cancelled Pending Order #{o.ticket}")

    play_close_sound()
    if is_profit:
        play_mp3_sound(PROFIT_SOUND_PATH, repeat=2, label="💰 PROFIT TARGET REACHED")
    else:
        play_mp3_sound(LOSS_SOUND_PATH, repeat=2, label="🛑 MAX LOSS LIMIT REACHED")

    log("✅ ALL POSITIONS AND PENDING ORDERS CLEARED")

# =========================================================
# MANUAL TRADE MONITORING LOOP
# =========================================================
def start_manual_monitor():
    log("==================================================")
    log(f"🛡️ MANUAL TRADE GUARD STARTED FOR {SYMBOL}")
    log(f"🎯 Dynamic Target: {DEFAULT_TARGET_PERCENTAGE}% of Lot Volume")
    log(f"🛑 Max Floating Loss Limit: -${MAX_LOSS_LIMIT:.2f}")
    log("Open trades manually in MT5. The script will monitor PnL and auto-close on target/loss hit.")
    log("==================================================")

    last_position_count = len(get_active_positions())

    while True:
        time.sleep(1)

        active_positions = get_active_positions()
        current_count = len(active_positions)
        current_prof = total_profit()
        exec_vol = total_executed_volume()
        target_prof = get_target_money_threshold(DEFAULT_TARGET_PERCENTAGE)

        # Detect newly placed manual trades
        if current_count > last_position_count:
            log(f"🔔 Manual Trade Detected! Total Active Trades: {current_count}")
            play_trade_sound()
            last_position_count = current_count
        elif current_count < last_position_count:
            last_position_count = current_count

        # Status Update Console Display
        if current_count > 0:
            log(f"Active Trades={current_count} | Total Volume={exec_vol:.2f} lots | Floating Profit=${current_prof:.2f} | Target=${target_prof:.2f} | Max Loss Cut=-${MAX_LOSS_LIMIT:.2f}")

            # 1. Target Profit Cut Check
            if target_prof > 0 and current_prof >= target_prof:
                log(f"🎯 TARGET PROFIT HIT -> Current: ${current_prof:.2f} >= Target: ${target_prof:.2f}")
                close_all(is_profit=True)
                last_position_count = 0

            # 2. Max Loss Safeguard Check
            elif current_prof <= -abs(MAX_LOSS_LIMIT):
                log(f"🛑 MAX LOSS LIMIT HIT -> Current: ${current_prof:.2f} <= Limit: -${abs(MAX_LOSS_LIMIT):.2f}")
                close_all(is_profit=False)
                last_position_count = 0

# =========================================================
# SCRIPT ENTRY
# =========================================================
if __name__ == "__main__":
    try:
        start_manual_monitor()
    except KeyboardInterrupt:
        log("👋 Manual Guard Monitor Stopped by User.")
    except Exception as e:
        log(f"❌ Critical Exception: {e}")