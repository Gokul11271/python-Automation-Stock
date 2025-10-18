#!/usr/bin/env python3
"""
25% Formula Script (Safe + Prediction) - with automatic lot normalization

- Asks only for GAP
- Reads broker symbol rules (min/max/step) and normalizes volumes
- Uses MA trend + ATR volatility filter to reduce losses
- Places pending orders with proper rounding
- Closes all when any TP is reached and prints a summary
"""

import MetaTrader5 as mt5
import time
from datetime import datetime

import sys

# ------------------- Config ------------------- #
SYMBOL = "XAUUSD_"      # change to your broker symbol if needed
MAGIC = 123456
SL_PIPS = 300.0         # Stop loss distance (in price units)
MAX_ROWS = 20           # Max formula rows
ATR_PERIOD = 14
VOLATILITY_THRESHOLD = 5.0   # ATR limit to pause trading
MAX_PENDING = 50        # safe guard for pending orders

# ------------------- Globals set at connect ------------------- #
sym_info = None
POINT = None
DIGITS = None
VOL_MIN = None
VOL_MAX = None
VOL_STEP = None

# ------------------- Helpers ------------------- #
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def printl(*args, **kwargs):
    print(f"[{now()}]", *args, **kwargs)

# ------------------- MT5 Connect & Symbol info ------------------- #
def connect_mt5():
    global sym_info, POINT, DIGITS, VOL_MIN, VOL_MAX, VOL_STEP
    if not mt5.initialize():
        print("❌ MT5 Initialization failed:", mt5.last_error())
        sys.exit(1)
    if not mt5.symbol_select(SYMBOL, True):
        print(f"❌ Failed to select symbol {SYMBOL}")
        mt5.shutdown()
        sys.exit(1)
    sym_info = mt5.symbol_info(SYMBOL)
    if sym_info is None:
        print(f"❌ symbol_info returned None for {SYMBOL}")
        mt5.shutdown()
        sys.exit(1)

    POINT = sym_info.point
    DIGITS = int(sym_info.digits)
    VOL_MIN = float(sym_info.volume_min or 0.01)
    VOL_STEP = float(sym_info.volume_step or 0.01)
    VOL_MAX = float(sym_info.volume_max or 100.0)

    printl("✅ MT5 Connected")
    printl(f"Symbol rules -> min:{VOL_MIN} step:{VOL_STEP} max:{VOL_MAX} digits:{DIGITS} point:{POINT}")

# ------------------- Volume normalization ------------------- #
def normalize_volume(vol: float) -> float:
    """Clamp and round volume to broker allowed step/min/max."""
    # avoid floating round issues: convert to steps
    if VOL_STEP == 0:
        return round(max(VOL_MIN, min(vol, VOL_MAX)), 8)
    # ensure within bounds
    vol = max(VOL_MIN, min(vol, VOL_MAX))
    # number of steps from min
    steps = round((vol - VOL_MIN) / VOL_STEP)
    normalized = VOL_MIN + steps * VOL_STEP
    # final clamp
    normalized = max(VOL_MIN, min(normalized, VOL_MAX))
    # round to reasonable precision
    return float(round(normalized, 8))

# ------------------- Formula Generator (uses normalized volumes) ------------------- #
def generate_formula_table():
    """Generate the 25% formula table with normalized volumes."""
    table = []
    cumulative = 0.0
    for i in range(1, MAX_ROWS + 1):
        raw_vol = 0.02 * i
        vol = normalize_volume(raw_vol)
        # if normalization collapses repeated volumes (e.g., broker min is larger) still include but prevent infinite loop
        if vol > VOL_MAX:
            break
        cumulative += i
        target = cumulative * 0.5
        entry = {
            "row": i,
            "raw_volume": round(raw_vol, 4),
            "volume": vol,
            "tp_value": round(target * 0.25, 4)  # price offset in script's units (we will treat as price increment)
        }
        table.append(entry)
        # Safety: stop if next raw volume would exceed VOL_MAX after normalization
        if normalize_volume(0.02 * (i + 1)) > VOL_MAX:
            break
    return table

# ------------------- Market Prediction ------------------- #
def get_ma(symbol, period, timeframe=mt5.TIMEFRAME_M15, count=300):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) < period:
        return None
    closes = rates['close']
    return sum(closes[-period:]) / period

def get_atr(symbol, period=ATR_PERIOD, timeframe=mt5.TIMEFRAME_M15, count=300):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) < period + 1:
        return None
    highs = rates['high']
    lows = rates['low']
    closes = rates['close']
    trs = []
    for i in range(1, len(rates)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period

def market_prediction(symbol):
    ma50 = get_ma(symbol, 50)
    ma200 = get_ma(symbol, 200)
    atr = get_atr(symbol, ATR_PERIOD)

    if ma50 is None or ma200 is None or atr is None:
        printl("⚠️ Not enough data for prediction, using ALTERNATE mode")
        return "ALTERNATE"

    printl(f"📊 Market Analysis: MA50={ma50:.4f}, MA200={ma200:.4f}, ATR={atr:.4f}")

    if atr > VOLATILITY_THRESHOLD:
        printl(f"🚨 ATR too high ({atr:.4f}) → WAIT")
        return "WAIT"

    if ma50 > ma200:
        printl("📈 Uptrend detected → BUY-only")
        return "BUY"
    elif ma50 < ma200:
        printl("📉 Downtrend detected → SELL-only")
        return "SELL"
    else:
        printl("⚖ Sideways → ALTERNATE")
        return "ALTERNATE"

# ------------------- Trading Functions ------------------- #
def place_order(symbol, order_type, volume, price, sl, tp):
    """Place a pending order with normalized volume and proper rounding."""
    volume = normalize_volume(volume)
    if volume < VOL_MIN or volume > VOL_MAX:
        printl(f"⚠️ Skipping order: volume {volume} outside allowed range")
        return None

    # prevent too many pendings
    try:
        current_pendings = mt5.orders_get(symbol=SYMBOL) or []
    except Exception:
        current_pendings = []
    if len(current_pendings) >= MAX_PENDING:
        printl(f"⚠️ Too many pending orders ({len(current_pendings)}) -> skipping")
        return None

    # round price/SL/TP to symbol digits
    price = round(price, DIGITS)
    sl = round(sl, DIGITS)
    tp = round(tp, DIGITS)

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": MAGIC,
        "comment": "25% Formula Script",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    result = mt5.order_send(request)
    if result is None:
        printl("❌ order_send returned None")
        return None
    if getattr(result, "retcode", None) != mt5.TRADE_RETCODE_DONE:
        printl(f"❌ Order failed: {getattr(result, 'retcode', result)}")
    else:
        printl(f"✅ Order placed: type={order_type}, Vol={volume}, Entry={price}, TP={tp}, SL={sl}")
    return result

def get_open_positions():
    pos = mt5.positions_get(symbol=SYMBOL)
    return pos or []

def cancel_all_pending():
    orders = mt5.orders_get(symbol=SYMBOL) or []
    for o in orders:
        try:
            mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": int(o.ticket),
            })
        except Exception as e:
            printl("Warning cancelling pending:", e)

def close_all_orders():
    """Closes all open positions and removes pending orders."""
    positions = mt5.positions_get(symbol=SYMBOL) or []
    for pos in positions:
        try:
            if pos.type == mt5.POSITION_TYPE_BUY:
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": pos.volume,
                    "type": mt5.ORDER_TYPE_SELL,
                    "position": pos.ticket,
                    "price": mt5.symbol_info_tick(SYMBOL).bid,
                    "deviation": 20,
                    "magic": MAGIC,
                    "comment": "Close on TP"
                }
            else:
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": pos.volume,
                    "type": mt5.ORDER_TYPE_BUY,
                    "position": pos.ticket,
                    "price": mt5.symbol_info_tick(SYMBOL).ask,
                    "deviation": 20,
                    "magic": MAGIC,
                    "comment": "Close on TP"
                }
            res = mt5.order_send(req)
            if res is None or getattr(res, "retcode", None) != mt5.TRADE_RETCODE_DONE:
                printl(f"❌ Failed to close pos {pos.ticket} -> {getattr(res, 'retcode', res)}")
            else:
                printl(f"✅ Closed pos {pos.ticket} vol={pos.volume}")
        except Exception as e:
            printl("Exception closing position:", e)

    # remove pending orders after closing
    orders = mt5.orders_get(symbol=SYMBOL) or []
    for o in orders:
        try:
            mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": int(o.ticket),
            })
        except Exception as e:
            printl("Warning removing pending:", e)

# ------------------- Main Logic ------------------- #
def main():
    printl("25% Formula Script (Safe + Prediction)")

    connect_mt5()

    # Get user gap
    try:
        GAP = float(input("Enter gap value (e.g., 0.3): ").strip())
    except Exception:
        printl("Invalid input, defaulting GAP=0.3")
        GAP = 0.3

    # Build formula table using broker rules
    formula = generate_formula_table()
    printl("📊 Formula table (first rows):")
    for row in formula[:min(12, len(formula))]:
        print(row)

    # Market prediction
    mode = market_prediction(SYMBOL)
    while mode == "WAIT":
        printl("Waiting for volatility to cool...")
        time.sleep(10)
        mode = market_prediction(SYMBOL)

    if mode == "ALTERNATE":
        printl("Using alternating BUY/SELL mode (sideways).")
    else:
        printl(f"Using mode: {mode}")

    # Starting tick price
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        printl("❌ No tick data available. Exiting.")
        mt5.shutdown()
        return
    start_price = tick.ask

    order_log = []
    current_side = "BUY"

    for row in formula:
        vol = row["volume"]
        tp_offset = row["tp_value"]

        # decide final side considering prediction mode
        side = current_side
        if mode == "BUY":
            side = "BUY"
        elif mode == "SELL":
            side = "SELL"

        if side == "BUY":
            entry_price = start_price + GAP
            sl = entry_price - SL_PIPS
            tp_price = entry_price + tp_offset
            result = place_order(SYMBOL, mt5.ORDER_TYPE_BUY_STOP, vol, entry_price, sl, tp_price)
            current_side = "SELL"
        else:
            entry_price = start_price - GAP
            sl = entry_price + SL_PIPS
            tp_price = entry_price - tp_offset
            result = place_order(SYMBOL, mt5.ORDER_TYPE_SELL_STOP, vol, entry_price, sl, tp_price)
            current_side = "BUY"

        if result and getattr(result, "retcode", None) == mt5.TRADE_RETCODE_DONE:
            # store TP as price to be monitored
            order_log.append({
                "row": row["row"],
                "side": side,
                "volume": vol,
                "tp_price": round(tp_price, DIGITS),
                "entry_price": round(entry_price, DIGITS)
            })
        time.sleep(0.5)

    printl("🚀 Orders placed (monitoring...). Press Ctrl+C to stop.")

    # Monitor: watch live tick and positions. If any position reaches its TP price, close all.
    try:
        while True:
            positions = get_open_positions()
            if not positions:
                # no positions open; check if any pending orders exist; if none -> finish
                pendings = mt5.orders_get(symbol=SYMBOL) or []
                if not pendings:
                    break
                # else continue waiting for triggers
                time.sleep(2)
                continue

            tick = mt5.symbol_info_tick(SYMBOL)
            if tick is None:
                time.sleep(1)
                continue

            tp_hit = False
            for pos in positions:
                # check pos.tp if present else use our stored tp_price
                pos_tp = getattr(pos, "tp", 0)
                # if pos.tp is 0 or None, fallback to order_log matching by volume/open price
                if pos_tp:
                    pos_tp_price = pos_tp
                else:
                    # approximate: find matching log entry by volume and side
                    matched = None
                    for o in order_log:
                        if abs(o["volume"] - pos.volume) < 1e-6 and o["side"] == ("BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"):
                            matched = o
                            break
                    pos_tp_price = matched["tp_price"] if matched else None

                if pos_tp_price is None:
                    continue

                if pos.type == mt5.POSITION_TYPE_BUY:
                    if tick.bid >= pos_tp_price:
                        printl(f"🎯 TP price reached for BUY pos {pos.ticket} (bid {tick.bid} >= tp {pos_tp_price})")
                        tp_hit = True
                        break
                else:
                    if tick.ask <= pos_tp_price:
                        printl(f"🎯 TP price reached for SELL pos {pos.ticket} (ask {tick.ask} <= tp {pos_tp_price})")
                        tp_hit = True
                        break

            if tp_hit:
                printl("🎯 TP hit detected → closing all positions and removing pendings")
                close_all_orders()
                break

            # optional: stop if equity or other safety triggers (not implemented here)
            time.sleep(1)

    except KeyboardInterrupt:
        printl("Interrupted by user. Closing open positions and removing pendings.")
        close_all_orders()

    # Summary table
    print("\n📊 Summary after run:")
    print(f"{'Row':<5}{'Side':<6}{'Volume':<8}{'Entry':<12}{'TP':<12}")
    print("-" * 50)
    for o in order_log:
        print(f"{o['row']:<5}{o['side']:<6}{o['volume']:<8}{o['entry_price']:<12}{o['tp_price']:<12}")
    print(f"\n✅ Total Orders Placed: {len(order_log)}")

    mt5.shutdown()

if __name__ == "__main__":
    main()
