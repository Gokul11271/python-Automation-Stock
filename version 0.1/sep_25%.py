#!/usr/bin/env python3
import MetaTrader5 as mt5
import time
from datetime import datetime

# ------------------- Config ------------------- #
DEFAULT_SYMBOL = "XAUUSD_"   # <-- Default broker symbol
SYMBOL_KEYWORD = "XAUUSD"    # Fallback auto-detect
SLIPPAGE = 500
MAGIC = 12345
LOSS_TARGET = 300.0
PROFIT_TARGET = 300  # used in normal mode
order_history = []   # Track all orders

# ------------------- Init ------------------- #
if not mt5.initialize():
    print("❌ Initialize() failed, error code =", mt5.last_error())
    quit()
print("✅ MT5 Initialized")

# ---- Prefer default, else fallback ---- #
SYMBOL = DEFAULT_SYMBOL
if not mt5.symbol_info(SYMBOL):
    all_symbols = [s.name for s in mt5.symbols_get() if SYMBOL_KEYWORD in s.name]
    if not all_symbols:
        print(f"❌ Could not find any symbol containing '{SYMBOL_KEYWORD}'")
        mt5.shutdown()
        quit()
    SYMBOL = all_symbols[0]

print(f"✅ Using symbol: {SYMBOL}")

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select symbol {SYMBOL}")
    mt5.shutdown()
    quit()
print(f"✅ Symbol {SYMBOL} selected")

symbol_info = mt5.symbol_info(SYMBOL)
point = symbol_info.point
stop_level = symbol_info.trade_stops_level * point
freeze_level = getattr(symbol_info, "freeze_level", 0) * point

# Volume limits
vol_min = symbol_info.volume_min
vol_step = symbol_info.volume_step
vol_max = symbol_info.volume_max

def normalize_volume(vol):
    steps = round((vol - vol_min) / vol_step)
    normalized = vol_min + steps * vol_step
    return max(vol_min, min(normalized, vol_max))

# ------------------- Volume Generators ------------------- #
def volume_pattern():
    n = 1
    while True:
        vol = n * 0.02
        yield normalize_volume(vol)
        n = 1 if vol >= vol_max else n + 1

def formula25_generator(vol_min=0.02, vol_step=0.02):
    target_profit = 0.0
    vol = vol_min
    while True:
        target_profit += vol * 25
        yield (round(vol, 2), round(target_profit, 2))
        vol += vol_step

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
                "comment": "Equity TP close"
            }
            mt5.order_send(request)

    cancel_all_pending()
    print("✅ All positions and pending orders closed.")

    # --- Print Trade Summary ---
    if order_history:
        total_orders = len(order_history)
        total_volume = sum(o["volume"] for o in order_history)
        print("\n📊 Trade Summary:")
        print(f"   Total orders placed: {total_orders}")
        print(f"   Total volume traded: {total_volume}")
        for i, o in enumerate(order_history, 1):
            print(f"   {i}. {o['type']} @ {o['price']} vol={o['volume']} TP={o['tp']}")

# ------------------- Order Placement ------------------- #
def place_order(order_type, base_price, volume):
    cancel_all_pending()
    attempt = 0
    volume = normalize_volume(volume)
    buffer = 3 * point  # safety buffer

    while True:
        attempt += 1
        tick = mt5.symbol_info_tick(SYMBOL)
        if not tick:
            print("❌ No tick data, retrying...")
            time.sleep(1)
            continue

        ask, bid = tick.ask, tick.bid
        spread = ask - bid

        if order_type == "BUY":
            min_price = ask + stop_level + freeze_level + spread + buffer
            price = max(base_price, min_price)
            mt_type = mt5.ORDER_TYPE_BUY_STOP
        else:
            max_price = bid - stop_level - freeze_level - spread - buffer
            price = min(base_price, max_price)
            mt_type = mt5.ORDER_TYPE_SELL_STOP

        price = round(price, symbol_info.digits)

        # Final safety re-check
        if order_type == "BUY" and price <= ask + stop_level + freeze_level:
            print(f"⚠️ Adjusting BUY STOP price {price} → {min_price}")
            price = round(min_price, symbol_info.digits)
        if order_type == "SELL" and price >= bid - stop_level - freeze_level:
            print(f"⚠️ Adjusting SELL STOP price {price} → {max_price}")
            price = round(max_price, symbol_info.digits)

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": SYMBOL,
            "volume": volume,
            "type": mt_type,
            "price": price,
            "deviation": SLIPPAGE,
            "type_filling": mt5.ORDER_FILLING_RETURN,  # safer for pending
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
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ {order_type} STOP placed at {price} (vol={volume}, attempt {attempt})")
            # Save to order history
            order_history.append({
                "type": order_type,
                "volume": volume,
                "price": price,
                "tp": None  # TP not used in this strategy
            })
            return price
        else:
            print(f"⚠️ {order_type} STOP rejected (Retcode {result.retcode}), ask={ask}, bid={bid}, price={price}, stop_level={stop_level}, freeze_level={freeze_level}")
            time.sleep(1)

# ------------------- Trading Cycle ------------------- #
def run_cycle(vol_gen, gap, use_25=False):
    tick = mt5.symbol_info_tick(SYMBOL)
    base_ask = tick.ask
    options = [round(base_ask + i * point * 10, symbol_info.digits) for i in range(1, 4)]

    print("\n👉 Choose starting BUY STOP price:")
    for i, val in enumerate(options, 1):
        print(f"{i}. {val}")

    choice = input("Enter choice (1/2/3 or custom price): ").strip()
    buy_price = options[int(choice) - 1] if choice in ["1", "2", "3"] else float(choice)

    if use_25:
        current_volume, expected_profit = next(vol_gen)
        print("📊 25% Formula Mode: Expected Profit =", expected_profit)
    else:
        current_volume = next(vol_gen)
        expected_profit = PROFIT_TARGET

    print(f"🚀 Starting cycle with BUY STOP at {buy_price}, gap = {gap}, TP={expected_profit}$, SL={LOSS_TARGET}$")
    active_price = place_order("BUY", buy_price, current_volume)
    last_order_type = "BUY"

    while True:
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions:
            pos = sorted(positions, key=lambda p: p.time)[-1]

            if last_order_type == "BUY" and pos.type == mt5.POSITION_TYPE_BUY:
                sell_price = round(active_price - gap, symbol_info.digits)
                current_volume = next(vol_gen)[0] if use_25 else next(vol_gen)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔔 BUY triggered → SELL STOP {sell_price} (vol={current_volume})")
                active_price = place_order("SELL", sell_price, current_volume)
                last_order_type = "SELL"

            elif last_order_type == "SELL" and pos.type == mt5.POSITION_TYPE_SELL:
                buy_price = round(active_price + gap, symbol_info.digits)
                current_volume = next(vol_gen)[0] if use_25 else next(vol_gen)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔔 SELL triggered → BUY STOP {buy_price} (vol={current_volume})")
                active_price = place_order("BUY", buy_price, current_volume)
                last_order_type = "BUY"

            account = mt5.account_info()
            if account:
                if account.profit >= expected_profit:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 Profit target hit: ${account.profit:.2f}")
                    close_all_positions()
                    return "profit"
                elif account.profit <= -LOSS_TARGET:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Loss limit hit: ${account.profit:.2f}")
                    close_all_positions()
                    return "loss"

        time.sleep(0.5)

# ------------------- Main ------------------- #
mode = input("\nChoose mode (manual/auto): ").strip().lower()

print("\n👉 Choose profit mode:")
print("1. Default fixed profit")
print("2. 25% formula (volume × 25)")
profit_choice = input("Enter choice (1/2): ").strip()
use_25 = (profit_choice == "2")

gap = float(input("Enter gap (distance between BUY and SELL): "))
vol_gen = formula25_generator() if use_25 else volume_pattern()

try:
    if mode == "manual":
        run_cycle(vol_gen, gap, use_25)
    else:
        while True:
            result = run_cycle(vol_gen, gap, use_25)
            print(f"🔄 Restarting cycle after {result.upper()} exit...\n")
            time.sleep(2)

except KeyboardInterrupt:
    print("\n🛑 Script stopped by user.")
finally:
    mt5.shutdown()
