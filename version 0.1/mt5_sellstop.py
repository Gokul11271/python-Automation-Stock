import MetaTrader5 as mt5
import time
from datetime import datetime

SYMBOL = "XAUUSD_"
VOLUME = 0.01
TARGET_PRICE = 3483.00  # Desired target for pending SELL STOP
SLIPPAGE = 50

# Initialize connection
if not mt5.initialize():
    print("❌ Initialize() failed, error code =", mt5.last_error())
    quit()

print(f"✅ Connected to MetaTrader5 - Monitoring {SYMBOL}...")

# Ensure symbol is available
if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select symbol {SYMBOL}")
    mt5.shutdown()
    quit()

# Get symbol info for stop level
symbol_info = mt5.symbol_info(SYMBOL)
if symbol_info is None:
    print(f"❌ Symbol info not found for {SYMBOL}")
    mt5.shutdown()
    quit()

stop_level = symbol_info.trade_stops_level * symbol_info.point
tick = mt5.symbol_info_tick(SYMBOL)
current_bid = tick.bid

# Validate SELL STOP level
max_valid_price = current_bid - stop_level
if TARGET_PRICE >= max_valid_price:
    print(f"⚠️ Target price {TARGET_PRICE} is too close to current Bid {current_bid:.2f}")
    print(f"Adjusting to maximum valid price: {max_valid_price:.2f}")
    TARGET_PRICE = round(max_valid_price - symbol_info.point, 2)

print(f"📌 Placing SELL STOP pending order at {TARGET_PRICE}...")

# Create pending SELL STOP order request
request = {
    "action": mt5.TRADE_ACTION_PENDING,
    "symbol": SYMBOL,
    "volume": VOLUME,
    "type": mt5.ORDER_TYPE_SELL_STOP,
    "price": TARGET_PRICE,
    "deviation": SLIPPAGE,
    "type_filling": mt5.ORDER_FILLING_FOK,
    "type_time": mt5.ORDER_TIME_GTC,
    "comment": "Python Pending Sell",
    "magic": 123456
}

result = mt5.order_send(request)

if result.retcode == mt5.TRADE_RETCODE_DONE:
    print(f"✅ Pending SELL STOP placed successfully at {TARGET_PRICE}")
else:
    print(f"❌ Failed to place pending order. Retcode={result.retcode}")
    print(result)

mt5.shutdown()
