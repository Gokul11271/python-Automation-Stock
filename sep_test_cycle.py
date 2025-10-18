#!/usr/bin/env python3
import MetaTrader5 as mt5
import time
from datetime import datetime

# ------------------- Config ------------------- #
SYMBOL_KEYWORD = "XAUUSD_"   # what we want (will auto-match suffix)
SLIPPAGE = 500
MAGIC = 12345
LOSS_TARGET = 300.0
PROFIT_TARGET = 300  # used in normal mode

# ------------------- Init ------------------- #
if not mt5.initialize():
    print("❌ Initialize() failed, error code =", mt5.last_error())
    quit()
print("✅ MT5 Initialized")

# ---- Auto-detect correct symbol ---- #
all_symbols = [s.name for s in mt5.symbols_get() if SYMBOL_KEYWORD in s.name]
if not all_symbols:
    print(f"❌ Could not find any symbol containing '{SYMBOL_KEYWORD}'")
    mt5.shutdown()
    quit()

SYMBOL = all_symbols[0]  # pick the first match
print(f"✅ Using detected symbol: {SYMBOL}")

if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select symbol {SYMBOL}")
    mt5.shutdown()
    quit()
print(f"✅ Symbol {SYMBOL} selected")

# ------------------- Preflight Checks ------------------- #
account_info = mt5.account_info()
terminal_info = mt5.terminal_info()
print("\n=== Preflight Checks ===")
print("Account:", account_info.login if account_info else "N/A")
print("Account trade allowed:", account_info.trade_allowed if account_info else "N/A")
print("Terminal connected:", terminal_info.connected if terminal_info else "N/A")
print("Terminal trade allowed:", terminal_info.trade_allowed if terminal_info else "N/A")

if not account_info or not account_info.trade_allowed or not terminal_info.trade_allowed:
    print("❌ Trading disabled (AutoTrading off or broker restrictions). Enable it in MT5 and retry.")
    mt5.shutdown()
    quit()

# ------------------- Test Market Order ------------------- #
symbol_info = mt5.symbol_info(SYMBOL)
if not symbol_info:
    print("❌ Could not fetch symbol info")
    mt5.shutdown()
    quit()

tick = mt5.symbol_info_tick(SYMBOL)
if not tick:
    print("❌ No tick data for", SYMBOL)
    mt5.shutdown()
    quit()

test_volume = symbol_info.volume_min
test_price = tick.ask

print(f"\n📌 Sending test BUY market order {test_volume} lots at {test_price} ...")
request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": SYMBOL,
    "volume": test_volume,
    "type": mt5.ORDER_TYPE_BUY,
    "price": test_price,
    "deviation": SLIPPAGE,
    "magic": MAGIC,
    "comment": "Test BUY",
    "type_filling": mt5.ORDER_FILLING_FOK,
}
result = mt5.order_send(request)

if result.retcode == mt5.TRADE_RETCODE_DONE:
    print(f"✅ Test BUY order placed successfully! Order={result.order}, Deal={result.deal}")

else:
    print(f"⚠️ Test BUY failed. Retcode={result.retcode}, details={result._asdict()}")
    print("❌ Market test failed, fix AutoTrading/account permissions first.")

mt5.shutdown()
