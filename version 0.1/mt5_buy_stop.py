import MetaTrader5 as mt5
import time
from datetime import datetime

SYMBOL = "XAUUSD_"      # Your trading symbol
VOLUME = 0.01           # Lot size
BUY_TARGET = 3517.50    # Price to trigger BUY
SLIPPAGE = 50           # Max slippage

# Initialize connection
if not mt5.initialize():
    print("❌ Initialize() failed, error code =", mt5.last_error())
    quit()

print(f"✅ Connected to MetaTrader5 - Monitoring {SYMBOL}...")

# Ensure symbol is visible
if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select symbol {SYMBOL}")
    mt5.shutdown()
    quit()

while True:
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        time.sleep(0.1)
        continue

    ask_price = tick.ask
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Ask: {ask_price:.2f}")

    if ask_price >= BUY_TARGET:
        print(f"🎯 Target reached at {ask_price:.2f}! Sending market BUY order...")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": VOLUME,
            "type": mt5.ORDER_TYPE_BUY,
            "price": ask_price,
            "deviation": SLIPPAGE,
            "type_filling": mt5.ORDER_FILLING_FOK,  # Fill or Kill
            "type_time": mt5.ORDER_TIME_GTC,       # Good till cancelled
            "comment": "Python Market Buy",
            "magic": 123456
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ BUY order placed successfully at {ask_price:.2f}")
        else:
            print(f"❌ Order failed. Retcode={result.retcode}")
            print(result)
        break

    time.sleep(0.1)  # Check price every 100ms

mt5.shutdown()
