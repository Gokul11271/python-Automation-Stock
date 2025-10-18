import MetaTrader5 as mt5
import time
from datetime import datetime
import winsound   # for sound alerts (Windows only)

# ------------------- Config ------------------- #
SYMBOL = "XAUUSD_"       # Trading symbol
SLIPPAGE = 500
MAGIC = 12345
LOSS_TARGET = 50.0       # Default loss stop in $
PROFIT_TARGET_BASE = 0.5    # Starting profit target in $
PROFIT_INCREMENT = 1    # Profit increases +0.6 per order

# ------------------- Init ------------------- #
if not mt5.initialize():
    print("❌ Initialize() failed, error code =", mt5.last_error())
    quit()

print("✅ MT5 Initialized")

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select symbol {SYMBOL}")
    mt5.shutdown()
    quit()

print(f"✅ Symbol {SYMBOL} selected")

symbol_info = mt5.symbol_info(SYMBOL)
point = symbol_info.point
stop_level = symbol_info.trade_stops_level * point

# Volume limits
vol_min = symbol_info.volume_min
vol_step = symbol_info.volume_step
vol_max = symbol_info.volume_max

def normalize_volume(vol):
    """Ensure volume is within broker limits."""
    steps = round((vol - vol_min) / vol_step)
    normalized = vol_min + steps * vol_step
    return max(vol_min, min(normalized, vol_max))

# ------------------- Volume Pattern ------------------- #
def volume_pattern():
    """First order 0.01, then all following orders fixed at 0.02."""
    first = True
    while True:
        if first:
            yield normalize_volume(0.01)
            first = False
        else:
            yield normalize_volume(0.02)

# ------------------- Helpers ------------------- #
def cancel_all_pending():
    orders = mt5.orders_get(symbol=SYMBOL)
    if orders:
        for o in orders:
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        print(f"🗑️ Cleared {len(orders)} pending orders.")

def close_all_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for pos in positions:
            if pos.type == mt5.POSITION_TYPE_BUY:
                close_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(SYMBOL).bid
            else:
                close_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(SYMBOL).ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "deviation": SLIPPAGE,
                "magic": MAGIC,
                "comment": "Equity TP/SL close"
            }
            mt5.order_send(request)

    cancel_all_pending()
    print("✅ All positions and pending orders closed.")
    # 🔔 Play notification sound
    # winsound.Beep(1000, 500)  # frequency=1000Hz, duration=500ms
    # winsound.Beep(1200, 500)

def place_order(order_type, base_price, volume, profit_target):
    """Places an order and increments profit target after each order."""
    cancel_all_pending()
    attempt = 0
    volume = normalize_volume(volume)

    while True:
        attempt += 1
        tick = mt5.symbol_info_tick(SYMBOL)
        if not tick:
            print("❌ No tick data, retrying...")
            time.sleep(1)
            continue

        if order_type == "BUY":
            min_price = tick.ask + stop_level + (2 * point)
            price = max(base_price, min_price)
            mt_type = mt5.ORDER_TYPE_BUY_STOP
        else:
            max_price = tick.bid - stop_level - (2 * point)
            price = min(base_price, max_price)
            mt_type = mt5.ORDER_TYPE_SELL_STOP

        price = round(price, symbol_info.digits)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": SYMBOL,
            "volume": volume,
            "type": mt_type,
            "price": price,
            "deviation": SLIPPAGE,
            "type_filling": mt5.ORDER_FILLING_FOK,
            "type_time": mt5.ORDER_TIME_GTC,
            "comment": f"Cyclic {order_type} STOP",
            "magic": MAGIC,
        }

        result = mt5.order_send(request)
        if result is None:
            print(f"❌ order_send() returned None, last_error = {mt5.last_error()}, retrying...")
            time.sleep(1)
            continue

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {order_type} STOP placed at {price} "
                  f"(vol={volume}, attempt {attempt}, TP={profit_target}$)")
            return price
        else: 
            print(f"⚠️ {order_type} STOP rejected (Retcode {result.retcode}), retrying...")
            time.sleep(1)

# ------------------- Trading Cycle ------------------- #
def run_cycle(vol_gen, gap, profit_target):
    tick = mt5.symbol_info_tick(SYMBOL)
    base_ask = tick.ask
    options = [round(base_ask + i * point * 10, symbol_info.digits) for i in range(1, 3 + 1)]

    print("\n👉 Choose starting BUY STOP price:")
    for i, val in enumerate(options, 1):
        print(f"{i}. {val}")

    choice = input("Enter choice (1/2/3 or custom price): ").strip()
    if choice in ["1", "2", "3"]:
        buy_price = options[int(choice) - 1]
    else:
        buy_price = float(choice)

    current_volume = next(vol_gen)
    print(f"🚀 Starting cycle with BUY STOP at {buy_price}, gap={gap}, TP={profit_target}$, SL={LOSS_TARGET}$")
    active_price = place_order("BUY", buy_price, current_volume, profit_target)
    profit_target += PROFIT_INCREMENT   # increase TP after order
    last_order_type = "BUY"

    while True:
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions:
            pos = sorted(positions, key=lambda p: p.time)[-1]

            if last_order_type == "BUY" and pos.type == mt5.POSITION_TYPE_BUY:
                sell_price = round(active_price - gap, symbol_info.digits)
                current_volume = next(vol_gen)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔔 BUY triggered → SELL STOP {sell_price} (vol={current_volume})")
                active_price = place_order("SELL", sell_price, current_volume, profit_target)
                profit_target += PROFIT_INCREMENT
                last_order_type = "SELL"

            elif last_order_type == "SELL" and pos.type == mt5.POSITION_TYPE_SELL:
                buy_price = round(active_price + gap, symbol_info.digits)
                current_volume = next(vol_gen)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔔 SELL triggered → BUY STOP {buy_price} (vol={current_volume})")
                active_price = place_order("BUY", buy_price, current_volume, profit_target)
                profit_target += PROFIT_INCREMENT
                last_order_type = "BUY"

            # Profit/Loss check
            account = mt5.account_info()
            if account:
                if account.profit >= profit_target:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 Profit target hit: ${account.profit:.2f}")
                    close_all_positions()
                    return "profit", profit_target
                elif account.profit <= -LOSS_TARGET:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Loss limit hit: ${account.profit:.2f}")
                    close_all_positions()
                    return "loss", profit_target

        time.sleep(0.5)

# ------------------- Main ------------------- #
print("\n👉 Choose mode:")
print("1. Manual")
print("2. Auto")
mode_choice = input("Enter choice (m/a): ").strip()
mode = "manual" if mode_choice == "m" else "auto"

gap = float(input("Enter gap (distance between BUY and SELL): "))

vol_gen = volume_pattern()
profit_target = PROFIT_TARGET_BASE

try:
    if mode == "manual":
        run_cycle(vol_gen, gap, profit_target)
    else:  # AUTO mode
        while True:
            result, profit_target = run_cycle(vol_gen, gap, profit_target)
            print(f"🔄 Restarting cycle after {result.upper()} exit... (Next TP={profit_target}$)\n")
            time.sleep(2)

except KeyboardInterrupt:
    print("\n🛑 Script stopped by user.")
finally:
    mt5.shutdown()
