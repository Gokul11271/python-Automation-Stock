import MetaTrader5 as mt5
import time
from datetime import datetime

# ------------------- Config ------------------- #
SYMBOL = "XAUUSD_"    # adjust to your broker symbol
SLIPPAGE = 500
MAGIC = 12345
LOSS_TARGET = 500.0       # equity loss stop (in $)
PROFIT_UNIT = 600          # profit per volume unit for TP calculation

# Progressive increment used when placing BUY after a SELL trigger
BUY_GAP = 1

# ------------------- Globals ------------------- #
order_log = []
base_buy_price = None     # anchor BUY price (float), decimal locked from this
fixed_decimal = None      # fractional part locked
base_int = None           # integer part of anchor
buy_step = 1              # progressive counter: first progressive BUY uses base_int + buy_step
next_pending_price = None

# ------------------- MT5 Init ------------------- #
if not mt5.initialize():
    print("❌ MT5 initialize failed:", mt5.last_error())
    raise SystemExit

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select symbol {SYMBOL}")
    mt5.shutdown()
    raise SystemExit

symbol_info = mt5.symbol_info(SYMBOL)
if symbol_info is None:
    print(f"❌ symbol_info for {SYMBOL} returned None")
    mt5.shutdown()
    raise SystemExit

point = symbol_info.point
stop_level = (symbol_info.trade_stops_level or 0) * point
digits = symbol_info.digits

vol_min = symbol_info.volume_min or 0.01
vol_step = symbol_info.volume_step or 0.01
vol_max = symbol_info.volume_max or 100.0

# ------------------- Helpers ------------------- #
def now():
    return datetime.now().strftime("%H:%M:%S")

def printl(*args, **kwargs):
    print(f"[{now()}]", *args, **kwargs)

def normalize_volume(vol: float) -> float:
    if vol <= vol_min:
        return vol_min
    steps = round((vol - vol_min) / vol_step)
    normalized = vol_min + steps * vol_step
    normalized = max(vol_min, min(normalized, vol_max))
    return float(round(normalized, 8))

# ------------------- Volume generator (simple) ------------------- #
def volume_pattern_generator():
    pattern = [0.01, 0.02, 0.03, 0.04, 0.05]
    for v in pattern:
        yield v
    while True:
        yield pattern[-1]

def account_equity_profit():
    ai = mt5.account_info()
    return ai.profit if ai else 0.0

# ------------------- Order helpers ------------------- #
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
    return removed

def place_pending_stop(order_side: str, base_price: float, volume: float):
    """
    Places a pending BUY_STOP or SELL_STOP while enforcing broker limits.
    Returns the placed price (rounded) or None.
    """
    cancel_all_pending()
    volume = normalize_volume(volume)
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        printl("❌ No tick available.")
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
        "comment": f"Pattern {order_side} STOP",
        "magic": MAGIC,
    }

    result = mt5.order_send(request)
    if result is None:
        printl("❌ order_send returned None")
        return None
    if getattr(result, "retcode", None) == mt5.TRADE_RETCODE_DONE:
        printl(f"✅ Placed {order_side} STOP at {price} vol={volume}")
        return price
    else:
        printl(f"⚠️ Failed to place {order_side} STOP (retcode={getattr(result,'retcode',mt5.last_error())})")
        return None

# ------------------- Pattern cycle ------------------- #
def run_pattern(vol_gen):
    global base_buy_price, fixed_decimal, base_int, buy_step, next_pending_price

    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        printl("❌ No tick data available.")
        return

    # Anchor base from market (lock fractional)
    base_buy_price = round(tick.ask, digits)
    base_int = int(base_buy_price)
    fixed_decimal = base_buy_price - base_int
    printl(f"🔒 Anchor base_buy_price = {base_buy_price} (int={base_int}, frac={fixed_decimal:.{digits}f})")

    # Place initial static SELL at base_int + fixed_decimal
    initial_sell = base_int + fixed_decimal
    vol0 = next(vol_gen)
    placed = place_pending_stop("SELL", initial_sell, vol0)
    if not placed:
        printl("❌ Could not place initial SELL STOP. Exiting.")
        return
    next_pending_price = placed
    printl(f"🔁 Initial SELL placed at {placed}. Waiting for triggers...")

    last_positions = mt5.positions_get(symbol=SYMBOL) or []
    last_count = len(last_positions)
    baseline_profit = account_equity_profit()
    cumulative_tp = vol0 * PROFIT_UNIT
    printl(f"📌 Baseline profit = {baseline_profit:.2f} | initial TP target = {cumulative_tp:.2f}")

    while True:
        ai = mt5.account_info()
        if ai:
            print(f"\rProfit: {ai.profit:+.2f} | Next buy_step: {buy_step}", end="", flush=True)

        positions = mt5.positions_get(symbol=SYMBOL) or []
        cur_count = len(positions)

        if cur_count > last_count:
            # find new positions
            existing = set([p.ticket for p in last_positions])
            new_positions = [p for p in positions if p.ticket not in existing]

            for pos in new_positions:
                pos_type = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"
                open_price = getattr(pos, "price_open", None)
                printl(f"\n🔔 Triggered {pos_type} at {open_price} (ticket {pos.ticket})")

                # log
                pattern_display = (base_int + buy_step) if pos.type == mt5.POSITION_TYPE_BUY else base_int
                order_log.append({
                    "ticket": pos.ticket,
                    "type": pos_type,
                    "volume": pos.volume,
                    "pattern_price": pattern_display,
                    "open_price": open_price
                })

                # update TP target using next volume
                next_vol = next(vol_gen)
                cumulative_tp += next_vol * PROFIT_UNIT

                # PATTERN: if SELL triggered -> next is progressive BUY
                if pos.type == mt5.POSITION_TYPE_SELL:
                    candidate_integer = base_int + buy_step
                    candidate_price = candidate_integer + fixed_decimal

                    # ensure broker min for BUY
                    tick_now = mt5.symbol_info_tick(SYMBOL)
                    if not tick_now:
                        printl("❌ No tick available while computing BUY candidate.")
                        return "error"
                    min_allowed = tick_now.ask + stop_level + (2 * point)
                    if candidate_price < min_allowed:
                        candidate_price = min_allowed

                    next_side = "BUY"
                    next_price = round(candidate_price, digits)
                    printl(f"➡ After SELL -> placing BUY at {next_price} (int={candidate_integer}, step={buy_step})")

                    # increment for next progressive BUY
                    buy_step += BUY_GAP

                else:
                    # BUY triggered -> next is static SELL at anchor
                    candidate_price = base_int + fixed_decimal
                    next_side = "SELL"
                    next_price = round(candidate_price, digits)
                    printl(f"➡ After BUY -> placing SELL at {next_price} (static anchor)")

                placed = place_pending_stop(next_side, next_price, next_vol)
                next_pending_price = placed

            last_count = cur_count
            last_positions = positions

        # equity TP/SL safety (simple)
        total_profit = account_equity_profit() - baseline_profit
        if total_profit >= cumulative_tp:
            printl(f"\n🎯 Cumulative TP reached (profit {total_profit:.2f} >= {cumulative_tp:.2f}). Closing everything.")
            # close all positions and cancel pending
            positions_all = mt5.positions_get(symbol=SYMBOL) or []
            for p in positions_all:
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(SYMBOL).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(SYMBOL).ask
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": p.volume,
                    "type": close_type,
                    "position": p.ticket,
                    "price": price,
                    "deviation": SLIPPAGE,
                    "magic": MAGIC,
                    "comment": "Close on TP"
                }
                mt5.order_send(req)
            cancel_all_pending()
            return "profit"

        if total_profit <= -LOSS_TARGET:
            printl(f"\n❌ SL hit (profit {total_profit:.2f} <= -{LOSS_TARGET}). Closing everything.")
            positions_all = mt5.positions_get(symbol=SYMBOL) or []
            for p in positions_all:
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(SYMBOL).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(SYMBOL).ask
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": p.volume,
                    "type": close_type,
                    "position": p.ticket,
                    "price": price,
                    "deviation": SLIPPAGE,
                    "magic": MAGIC,
                    "comment": "Close on SL"
                }
                mt5.order_send(req)
            cancel_all_pending()
            return "loss"

        time.sleep(0.5)

# ------------------- Main ------------------- #
def main():
    try:
        vol_gen = volume_pattern_generator()
        printl("🚀 Starting pattern (Static SELL anchor / Progressive BUY).")
        run_pattern(vol_gen)
    except KeyboardInterrupt:
        printl("🛑 Stopped by user.")
    finally:
        mt5.shutdown()
        printl("MT5 connection closed.")

if __name__ == "__main__":
    main()