#!/usr/bin/env python3
"""
Ascending volume cycle trading script
"""

import MetaTrader5 as mt5
import time
from datetime import datetime

SYMBOL = "XAUUSD_"     # set your broker symbol
SLIPPAGE = 500
MAGIC = 12345
LOSS_TARGET = 50.0
POLL_INTERVAL = 0.5
DEFAULT_PROFIT_TARGET = 1.0

order_log = []

# --- Init ---
if not mt5.initialize():
    print("❌ MT5 Init failed:", mt5.last_error()); quit()
if not mt5.symbol_select(SYMBOL, True):
    print("❌ Cannot select symbol"); mt5.shutdown(); quit()
point = mt5.symbol_info(SYMBOL).point
digits = mt5.symbol_info(SYMBOL).digits

# --- Helpers ---
def now(): return datetime.now().strftime("%H:%M:%S")
def printl(*a): print(f"[{now()}]", *a)

def volume_pattern_gen():
    vol = 0.02
    step = 0.02
    while True:
        yield round(vol, 2)
        vol += step

def profit_pattern_gen():
    base, step = 0.5, 0.5
    while True:
        yield round(base, 2)
        base += step
        step += 0.5

def place_pending(order_side, base_price, volume):
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick: return None
    if order_side == "BUY":
        req_type = mt5.ORDER_TYPE_BUY_STOP
        price = round(max(base_price, tick.ask + 2*point), digits)
    else:
        req_type = mt5.ORDER_TYPE_SELL_STOP
        price = round(min(base_price, tick.bid - 2*point), digits)
    req = {
        "action": mt5.TRADE_ACTION_PENDING, "symbol": SYMBOL, "volume": volume,
        "type": req_type, "price": price, "deviation": SLIPPAGE,
        "type_filling": mt5.ORDER_FILLING_FOK, "type_time": mt5.ORDER_TIME_GTC,
        "comment": f"{order_side} STOP", "magic": MAGIC,
    }
    r = mt5.order_send(req)
    if r and r.retcode == mt5.TRADE_RETCODE_DONE:
        printl(f"✅ {order_side} STOP placed @ {price} vol={volume}")
        return price
    else:
        printl(f"⚠️ Order failed, retcode={getattr(r,'retcode',None)}")
        return None

def account_profit(): return mt5.account_info().profit

# --- Core Cycle ---
def run_cycle(gap):
    vol_gen = volume_pattern_gen()
    profit_gen = profit_pattern_gen()
    tick = mt5.symbol_info_tick(SYMBOL)
    buy_price = round(tick.ask + gap, digits)
    vol = next(vol_gen)
    expected_profit = next(profit_gen)
    printl(f"🚀 Start cycle: BUY STOP {buy_price}, vol={vol}, TP={expected_profit}")
    active_price = place_pending("BUY", buy_price, vol)
    last_type = "BUY"; baseline = None
    while True:
        acc_p = account_profit()
        if baseline is None:
            baseline = acc_p; continue
        trade_profit = acc_p - baseline
        if trade_profit >= expected_profit:
            printl(f"🎯 TP hit {trade_profit:.2f}"); break
        if trade_profit <= -LOSS_TARGET:
            printl(f"❌ SL hit {trade_profit:.2f}"); break
        time.sleep(POLL_INTERVAL)

# --- Main ---
if __name__ == "__main__":
    try:
        gap = float(input("Enter gap (price distance): "))
        run_cycle(gap)
    except KeyboardInterrupt:
        printl("Stopped by user.")
    finally:
        mt5.shutdown()
