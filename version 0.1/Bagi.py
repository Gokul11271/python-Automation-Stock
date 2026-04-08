#!/usr/bin/env python3
"""
25% Formula cycle trading script
"""

import MetaTrader5 as mt5
import time
from datetime import datetime

# ------------------- Config ------------------- #
SYMBOL = "XAUUSD"
SLIPPAGE = 500
MAGIC = 12345
LOSS_TARGET = 600.0
POLL_INTERVAL = 0.5
order_log = []

# ------------------- MT5 Init ------------------- #
if not mt5.initialize():
    print("❌ MT5 Init failed:", mt5.last_error())
    quit()

if not mt5.symbol_select(SYMBOL, True):
    print("❌ Cannot select symbol"); mt5.shutdown(); quit()

symbol_info = mt5.symbol_info(SYMBOL)
if symbol_info is None:
    print("❌ symbol_info returned None"); mt5.shutdown(); quit()

point = symbol_info.point
digits = symbol_info.digits

# ------------------- Helpers ------------------- #
def now(): return datetime.now().strftime("%H:%M:%S")
def printl(*a): print(f"[{now()}]", *a)

def normalize_volume(vol):
    vol_min = symbol_info.volume_min or 0.01
    vol_max = symbol_info.volume_max or 100.0
    vol_step = symbol_info.volume_step or 0.01
    steps = round((vol - vol_min) / vol_step)
    normalized = vol_min + steps * vol_step
    return max(vol_min, min(normalized, vol_max))

def account_profit():
    ai = mt5.account_info()
    return ai.profit if ai else 0.0

# ------------------- Formula25 Generator ------------------- #
def formula25_generator(vol_min=0.01, vol_step=0.01):
    target_profit = 0.0
    vol = vol_min
    while True:
        target_profit += vol * 75
        yield (round(vol, 2), round(target_profit, 2))
        vol += vol_step

# ------------------- Order Placement ------------------- #
def place_pending(order_side, base_price, volume):
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        printl("❌ No tick data")
        return None
    if order_side == "BUY":
        mt_type = mt5.ORDER_TYPE_BUY_STOP
        price = round(max(base_price, tick.ask + 2*point), digits)
    else:
        mt_type = mt5.ORDER_TYPE_SELL_STOP
        price = round(min(base_price, tick.bid - 2*point), digits)

    volume = normalize_volume(volume)
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": volume,
        "type": mt_type,
        "price": price,
        "deviation": SLIPPAGE,
        "type_filling": mt5.ORDER_FILLING_FOK,
        "type_time": mt5.ORDER_TIME_GTC,
        "comment": f"{order_side} STOP",
        "magic": MAGIC,
    }

    attempt = 0
    while True:
        attempt += 1
        result = mt5.order_send(request)
        if result and getattr(result, "retcode", None) == mt5.TRADE_RETCODE_DONE:
            printl(f"✅ {order_side} STOP placed @ {price} vol={volume} (attempt {attempt})")
            order_log.append({"ticket": getattr(result,'order',None), "type": order_side, "volume": volume, "tp": None})
            return price
        else:
            err = getattr(result, "retcode", mt5.last_error())
            printl(f"⚠️ Failed {order_side} STOP (retcode={err}), retrying...")
            time.sleep(1)

# ------------------- Close All ------------------- #
def close_all_positions():
    positions = mt5.positions_get(symbol=SYMBOL) or []
    for pos in positions:
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(SYMBOL).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info_tick(SYMBOL).ask
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": pos.volume, "type": close_type, "position": pos.ticket, "price": price, "deviation": SLIPPAGE, "magic": MAGIC, "comment":"Close by script"}
        mt5.order_send(req)
    printl("✅ All positions closed.")

# ------------------- Trading Cycle ------------------- #
def run_cycle(gap):
    vol_gen = formula25_generator()
    tick = mt5.symbol_info_tick(SYMBOL)
    buy_price = round(tick.ask + gap, digits)
    vol, expected_profit = next(vol_gen)
    printl(f"🚀 Starting BUY STOP {buy_price}, vol={vol}, expected TP=${expected_profit}")
    active_price = place_pending("BUY", buy_price, vol)
    baseline_equity = None
    last_order_type = "BUY"

    while True:
        acc_profit = account_profit()
        if baseline_equity is None:
            baseline_equity = acc_profit
            time.sleep(POLL_INTERVAL)
            continue

        trade_profit = acc_profit - baseline_equity
        print(f"Profit={trade_profit:.2f} (Target=${expected_profit})", end="\r")

        if trade_profit >= expected_profit:
            printl(f"\n🎯 TP hit {trade_profit:.2f}")
            close_all_positions()
            return
        if trade_profit <= -LOSS_TARGET:
            printl(f"\n❌ SL hit {trade_profit:.2f}")
            close_all_positions()
            return

        positions = mt5.positions_get(symbol=SYMBOL) or []
        if positions:
            pos = positions[-1]
            if pos.type == mt5.POSITION_TYPE_BUY and last_order_type=="BUY":
                vol, expected_profit = next(vol_gen)
                sell_price = round(active_price - gap, digits)
                printl(f"🔔 BUY triggered → placing SELL STOP {sell_price}, vol={vol}")
                active_price = place_pending("SELL", sell_price, vol)
                last_order_type = "SELL"
            elif pos.type == mt5.POSITION_TYPE_SELL and last_order_type=="SELL":
                vol, expected_profit = next(vol_gen)
                buy_price_next = round(active_price + gap, digits)
                printl(f"🔔 SELL triggered → placing BUY STOP {buy_price_next}, vol={vol}")
                active_price = place_pending("BUY", buy_price_next, vol)
                last_order_type = "BUY"

        time.sleep(POLL_INTERVAL)

# ------------------- Main ------------------- #
if __name__ == "__main__":
    try:
        gap = float(input("Enter gap (price distance): "))
        run_cycle(gap)
    except KeyboardInterrupt:
        printl("🛑 Script stopped by user.")
    finally:
        mt5.shutdown()
        printl("MT5 connection closed.")
