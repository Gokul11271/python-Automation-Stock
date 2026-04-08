#!/usr/bin/env python3
"""
Fixed & improved cyclic BUY/SELL STOP script for MetaTrader5.

Key fix: profit target used for TP-checking is taken from the *pending order that actually triggered*.
"""

import MetaTrader5 as mt5
import time
from datetime import datetime

# ------------------- Config ------------------- #
SYMBOL = "XAUUSD_"       # trading symbol (set to your broker's symbol name)
SLIPPAGE = 500           # allowed deviation in points
MAGIC = 12345            # magic number
LOSS_TARGET = 50.0       # equity loss stop (in $)
POLL_INTERVAL = 0.5      # seconds between main loop polls
DEFAULT_PROFIT_TARGET = 1.0  # default $ profit target if not using profit generator

# ------------------- MT5 Init ------------------- #
if not mt5.initialize():
    print("❌ Initialize() failed, error =", mt5.last_error())
    quit()

print("✅ MT5 Initialized")

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select symbol {SYMBOL}")
    mt5.shutdown()
    quit()

symbol_info = mt5.symbol_info(SYMBOL)
if symbol_info is None:
    print(f"❌ symbol_info for {SYMBOL} returned None")
    mt5.shutdown()
    quit()

point = symbol_info.point
stop_level = symbol_info.trade_stops_level * point if symbol_info.trade_stops_level is not None else 0
digits = symbol_info.digits

# Volume limits (ensure not None)
vol_min = symbol_info.volume_min or 0.01
vol_step = symbol_info.volume_step or 0.01
vol_max = symbol_info.volume_max or 100.0

# ------------------- Helpers ------------------- #
def now():
    return datetime.now().strftime("%H:%M:%S")

def normalize_volume(vol: float) -> float:
    if vol <= vol_min:
        return vol_min
    steps = round((vol - vol_min) / vol_step)
    normalized = vol_min + steps * vol_step
    normalized = max(vol_min, min(normalized, vol_max))
    return float(round(normalized, 8))

def printl(*args, **kwargs):
    print(f"[{now()}]", *args, **kwargs)

# ------------------- Generators ------------------- #
def formula25_generator(vol_min=0.01, vol_step=0.01):
    vol = vol_min
    while True:
        vol = normalize_volume(vol)
        profit = round(vol * 100.0, 2)
        yield vol, profit
        vol += vol_step

    """
    25% Formula Generator
    Target = Volume * 25
    Example: vol=0.015 → target=$0.375
    """
    a = 0
    while True:
        a += 1
        vol = normalize_volume(vol_min + a * vol_step)
        profit = round(vol * 25.0, 2)   
        yield vol, profit


def volume_pattern_gen(choice: str):
    step = vol_step
    n = 0
    while True:
        n += 1
        if choice == "ascending":
            vol = vol_min + (n - 1) * step
        elif choice == "even":
            vol = vol_min + (2 * n - 1) * step
        elif choice == "odd":
            vol = vol_min + (2 * n - 2) * step
        elif choice == "mega":
            vol = 0.10 + (n - 1) * step
        else:
            vol = vol_min + (n - 1) * step
        yield normalize_volume(vol)

def profit_pattern_gen(mode="default"):
    if mode == "even":
        profit = 1.5
        step = 2.0
        while True:
            yield round(profit, 2)
            profit += step
            step += 1.0
    elif mode == "mega":
        profit = 3.0
        while True:
            yield round(profit, 2)
            profit += 0.5
    else:
        base = 0.5
        step = 0.5
        while True:
            yield round(base, 2)
            base += step
            step += 0.5

# ------------------- Order / Position Helpers ------------------- #
def cancel_all_pending():
    orders = mt5.orders_get(symbol=SYMBOL)
    if not orders:
        return 0
    removed = 0
    for o in orders:
        try:
            req = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": int(o.ticket),
                "symbol": o.symbol,
                "magic": o.magic if hasattr(o, "magic") else MAGIC,
                "comment": "Cancel pending by script"
            }
            mt5.order_send(req)
            removed += 1
        except Exception as e:
            printl("Warning cancelling order:", e)
    if removed:
        printl(f"🗑️ Cleared {removed} pending orders.")
        acc_profit = account_equity_profit()
        trade_profit = acc_profit  # No baseline in this context
        triggered_count = len(mt5.positions_get(symbol=SYMBOL) or [])
        print(
            f"❤️ Trades={triggered_count} | Profit={trade_profit:.2f} "
            f"(Target=${'N/A'} 👾 Total=${acc_profit:.2f})",
            end="\r"
        )
    return removed
    
    
    
    
    print(f"❤️ Trades={triggered_count} | Profit={trade_profit:.2f} ")

def close_all_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        cancel_all_pending()
        printl("✅ No positions to close.")
        return

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
            "comment": "Close by script"
        }
        result = mt5.order_send(request)
        if result and getattr(result, "retcode", None) == mt5.TRADE_RETCODE_DONE:
            printl(f"✅ Closed position {pos.ticket} at {price}")
        else:
            printl(f"⚠️ Failed to close position {pos.ticket}, retcode={getattr(result,'retcode','N/A')}")

    cancel_all_pending()
    printl("✅ All positions and pending orders closed.")

def account_equity_profit():
    ai = mt5.account_info()
    if ai:
        return ai.profit
    return 0.0

def place_pending_stop(order_side: str, base_price: float, volume: float):
    cancel_all_pending()
    volume = normalize_volume(volume)

    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        printl("❌ No tick available to place order.")
        return None

    if order_side == "BUY":
        mt_type = mt5.ORDER_TYPE_BUY_STOP
        min_price = tick.ask + stop_level + (2 * point)
        price = max(base_price, min_price)
    else:
        mt_type = mt5.ORDER_TYPE_SELL_STOP
        max_price = tick.bid - stop_level - (2 * point)
        price = min(base_price, max_price)

    price = round(price, digits)

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": volume,
        "type": mt_type,
        "price": price,
        "deviation": SLIPPAGE,
        "type_filling": mt5.ORDER_FILLING_FOK,
        "type_time": mt5.ORDER_TIME_GTC,
        "comment": f"Cyclic {order_side} STOP",
        "magic": MAGIC,
    }

    result = mt5.order_send(request)
    if result is None:
        printl("❌ order_send() returned None, last_error =", mt5.last_error())
        return None

    # Many brokers return retcodes differently for pending placement; log and return price
    printl(f"✅ {order_side} STOP placed at {price} vol={volume} (retcode={getattr(result,'retcode','N/A')})")
    return price

# ------------------- Trading Cycle (FULL) ------------------- #
def run_cycle(vol_gen, profit_gen, gap, mode25=False):
    """
    Main trading cycle:
    - Places alternating BUY/SELL STOP orders
    - Profit target used is always the one stored with the pending that triggered
    """
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        printl("❌ No tick data available. Cannot run cycle.")
        return "error"

    base_ask = tick.ask
    options = [round(base_ask + i * point * 10, digits) for i in range(1, 4)]

    print("\n👉 Choose starting BUY STOP price:")
    for i, val in enumerate(options, 1):
        print(f"{i}. {val}")
    choice = input("Enter choice (1/2/3 or custom price): ").strip()
    if choice in ["1", "2", "3"]:
        buy_price = options[int(choice) - 1]
    else:
        try:
            buy_price = float(choice)
        except ValueError:
            printl("Invalid price entered. Aborting cycle.")
            return "error"

    # --- Prepare initial pending and store its expected profit (last_pending_expected) ---
    if mode25:
        vol, expected_profit = next(vol_gen)          # formula25 yields (vol,profit)
    else:
        vol = next(vol_gen)
        expected_profit = next(profit_gen) if profit_gen else DEFAULT_PROFIT_TARGET

    printl(f"Starting vol={vol}, expected TP=${expected_profit}")

    printl(f"🚀 Starting cycle with BUY STOP at {buy_price}, gap={gap}, SL=${LOSS_TARGET}")
    active_price = place_pending_stop("BUY", buy_price, vol)
    if not active_price:
        printl("❌ Failed to place initial BUY STOP. Aborting cycle.")
        return "error"

    # last_pending_expected stores the TP we expect for the pending order we just placed
    last_pending_expected = expected_profit
    # This is the profit target of the *currently active triggered trade*. Will be set when a pending triggers.
    profit_target = None

    last_order_type = "BUY"
    last_positions = mt5.positions_get(symbol=SYMBOL) or []
    last_pos_count = len(last_positions)

    baseline_equity = None
    triggered_count = 0

    while True:
        acc_profit = account_equity_profit()

        # Wait until first trade is triggered
        positions = mt5.positions_get(symbol=SYMBOL)
        if not positions:
            # no open positions yet; show waiting and continue
            print("⏳ Waiting for first trade to trigger...", end="\r")
            time.sleep(POLL_INTERVAL)
            continue

        # If baseline not set, set it at the moment the first position exists
        if baseline_equity is None:
            baseline_equity = acc_profit
            printl(f"📌 Baseline equity set at: {baseline_equity:.2f}")
            time.sleep(POLL_INTERVAL)
            continue

        # If there is no active profit_target (i.e., pending triggered but we didn't assign), do so:
        # We detect triggers by comparing positions count vs last_pos_count below.
        # But if profit_target is None and we already have positions, set profit_target to last_pending_expected
        if profit_target is None and last_pending_expected is not None:
            profit_target = last_pending_expected
            printl(f"📌 Profit target for current triggered trade set to: ${profit_target}")

        # show relative trade profit using baseline
        trade_profit = acc_profit - baseline_equity
        print(
            f"❤️ Trades={triggered_count} | Profit={trade_profit:.2f} "
            f"(Target=${profit_target if profit_target is not None else 'N/A'} 👾 Total=${acc_profit:.2f})",
            end="\r"
        )

        # Check TP/SL only if profit_target is known
        if profit_target is not None:
            if trade_profit >= profit_target:
                printl(f"\n🎯 TP hit: {trade_profit:.2f} >= target {profit_target:.2f}")
                close_all_positions()
                return "profit"
            if trade_profit <= -LOSS_TARGET:
                printl(f"\n❌ SL hit: {trade_profit:.2f} <= -{LOSS_TARGET}")
                close_all_positions()
                return "loss"

        # Detect new triggered positions (pending -> market)
        current_positions = mt5.positions_get(symbol=SYMBOL) or []
        curr_count = len(current_positions)

        if curr_count > last_pos_count:
            # find new positions by ticket difference
            new_positions = [p for p in current_positions if p.ticket not in [lp.ticket for lp in last_positions]]
            for pos in new_positions:
                triggered_count += 1

                # The position that just opened corresponds to the last pending we placed.
                # So use last_pending_expected as the TP for THIS triggered trade.
                profit_target = last_pending_expected
                printl(f"\n🔔 Trigger #{triggered_count}: position opened (ticket={pos.ticket}, vol={pos.volume}). Using TP=${profit_target}")

                # Now compute & place the OPPOSITE pending for the next leg.
                # For the next pending, fetch next vol and expected_profit (and update last_pending_expected)
                if mode25:
                    next_vol, next_expected_profit = next(vol_gen)
                else:
                    next_vol = next(vol_gen)
                    next_expected_profit = next(profit_gen) if profit_gen else profit_target

                # Decide opposite side and price
                if pos.type == mt5.POSITION_TYPE_BUY and last_order_type == "BUY":
                    sell_price = round(active_price - gap, digits)
                    printl(f"🔔 BUY triggered → placing SELL STOP {sell_price} vol={next_vol}, next TP=${next_expected_profit}")
                    active_price = place_pending_stop("SELL", sell_price, next_vol)
                    last_order_type = "SELL"
                elif pos.type == mt5.POSITION_TYPE_SELL and last_order_type == "SELL":
                    buy_price_next = round(active_price + gap, digits)
                    printl(f"🔔 SELL triggered → placing BUY STOP {buy_price_next} vol={next_vol}, next TP=${next_expected_profit}")
                    active_price = place_pending_stop("BUY", buy_price_next, next_vol)
                    last_order_type = "BUY"
                else:
                    # Unexpected state - place the opposite of last_order_type to continue the cycle
                    if last_order_type == "BUY":
                        sell_price = round(active_price - gap, digits)
                        active_price = place_pending_stop("SELL", sell_price, next_vol)
                        last_order_type = "SELL"
                    else:
                        buy_price_next = round(active_price + gap, digits)
                        active_price = place_pending_stop("BUY", buy_price_next, next_vol)
                        last_order_type = "BUY"

                # Update last_pending_expected to the TP associated with the pending we just placed
                last_pending_expected = next_expected_profit

            # update trackers
            last_pos_count = curr_count
            last_positions = current_positions

        time.sleep(POLL_INTERVAL)

# ------------------- Main / UI ------------------- #
def main():
    try:
        print("\n👉 Choose mode:")
        print("m. Manual (one run)")
        print("a. Auto (repeat runs)")
        mode_choice = input("Enter choice (m/a): ").strip()
        mode = "manual" if mode_choice.lower() == "m" else "auto"

        print("\n👉 Choose volume/profit pattern:")
        print("1. Ascending (0.01, 0.02, 0.03 …)")
        print("2. Even only (0.02, 0.04, 0.06 …)")
        print("3. Odd only (0.01, 0.03, 0.05 …)")
        print("4. Mega (0.11→3, 0.12→3.5 …)")
        print("5. 25% Formula (Target = Volume × 25 $)")
        vol_choice = input("Enter choice (1/2/3/4/5): ").strip()

        mode25 = False
        if vol_choice == "1":
            vol_gen = volume_pattern_gen("ascending")
            profit_gen = profit_pattern_gen("default")
        elif vol_choice == "2":
            vol_gen = volume_pattern_gen("even")
            profit_gen = profit_pattern_gen("even")
        elif vol_choice == "3":
            vol_gen = volume_pattern_gen("odd")
            profit_gen = profit_pattern_gen("default")
        elif vol_choice == "4":
            vol_gen = volume_pattern_gen("mega")
            profit_gen = profit_pattern_gen("mega")
        elif vol_choice == "5":
            vol_gen = formula25_generator()
            profit_gen = None
            mode25 = True
        else:
            printl("Invalid choice; defaulting to ascending.")
            vol_gen = volume_pattern_gen("ascending")
            profit_gen = profit_pattern_gen("default")

        gap = None
        while gap is None:
            try:
                gap = float(input("Enter gap (distance between BUY and SELL in price units): ").strip())
            except ValueError:
                printl("Please input a numeric gap value.")

        if mode == "manual":
            run_cycle(vol_gen, profit_gen, gap, mode25)
        else:
            while True:
                result = run_cycle(vol_gen, profit_gen, gap, mode25)
                printl(f"🔄 Restarting cycle after {result.upper()} exit...\n")
                time.sleep(2)

    except KeyboardInterrupt:
        printl("🛑 Script stopped by user.")
    except Exception as e:
        printl("Unhandled exception:", e)
    finally:
        mt5.shutdown()
        printl("MT5 connection closed.")

if __name__ == "__main__":
    main()
