import MetaTrader5 as mt5
import time
from datetime import datetime

SYMBOL = "XAUUSD_"
VOLUME = 0.01
START_PRICE = 3485.00  # Initial target price
SLIPPAGE = 50
INCREMENT = 1.00        # Price increment for each next order

# Initialize MT5 connection
if not mt5.initialize():
    print("❌ Initialize() failed, error code =", mt5.last_error())
    quit()

print(f"✅ Connected to MetaTrader5 - Monitoring {SYMBOL}...")

# Ensure symbol is available
if not mt5.symbol_select(SYMBOL, True):
    print(f"❌ Failed to select symbol {SYMBOL}")
    mt5.shutdown()
    quit()

# Get symbol info
symbol_info = mt5.symbol_info(SYMBOL)
if symbol_info is None:
    print(f"❌ Symbol info not found for {SYMBOL}")
    mt5.shutdown()
    quit()

stop_level = symbol_info.trade_stops_level * symbol_info.point

price = START_PRICE
order_number = 1
pending_orders = []

try:
    while True:
        tick = mt5.symbol_info_tick(SYMBOL)
        current_ask = tick.ask
        min_valid_price = current_ask + stop_level

        # Adjust price if too close to current market
        if price <= min_valid_price:
            price = round(min_valid_price + symbol_info.point, 2)

        # Check if last pending order is still active
        last_order_active = False
        if pending_orders:
            # Get the status of the last pending order
            orders = mt5.orders_get(ticket=pending_orders[-1])
            if orders and len(orders) > 0:
                last_order_active = True
            else:
                pending_orders.pop()  # Remove triggered or canceled order

        # Place new order only if previous is still pending
        if not last_order_active:
            print(f"📌 Placing BUY STOP pending order {order_number} at {price}...")

            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": SYMBOL,
                "volume": VOLUME,
                "type": mt5.ORDER_TYPE_BUY_STOP,
                "price": price,
                "deviation": SLIPPAGE,
                "type_filling": mt5.ORDER_FILLING_FOK,
                "type_time": mt5.ORDER_TIME_GTC,
                "comment": f"Python Pending Buy {order_number}",
                "magic": 123456
            }

            result = mt5.order_send(request)

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"✅ Order {order_number} placed successfully at {price}")
                pending_orders.append(result.order)  # Track pending order
                order_number += 1
                price = round(price + INCREMENT, 2)  # Increment for next order
            else:
                print(f"❌ Failed to place order {order_number}. Retcode={result.retcode}")
                print(result)
        
        time.sleep(1)  # Short delay before next check

except KeyboardInterrupt:
    print("\n🛑 Script stopped by user. Shutting down...")

finally:
    mt5.shutdown()
