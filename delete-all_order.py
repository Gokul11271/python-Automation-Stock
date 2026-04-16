import MetaTrader5 as mt5
import time

# -------- CONFIG -------- #
SYMBOL = "XAUUSD"   # or None → to close ALL symbols
SLIPPAGE = 20

# -------- INIT -------- #
if not mt5.initialize():
    print("❌ MT5 Init Failed")
    quit()

print("✅ MT5 Connected")

# -------- CLOSE POSITIONS -------- #
def close_all_positions():
    positions = mt5.positions_get()

    if not positions:
        print("ℹ️ No open positions")
        return

    for pos in positions:
        symbol = pos.symbol

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            continue

        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": SLIPPAGE,
            "comment": "Close All Script"
        }

        result = mt5.order_send(request)

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Closed {symbol} | Ticket {pos.ticket}")
        else:
            print(f"⚠️ Failed to close {pos.ticket}, retrying...")
            time.sleep(1)

# -------- DELETE PENDING -------- #
def delete_all_pending():
    orders = mt5.orders_get()

    if not orders:
        print("ℹ️ No pending orders")
        return

    for order in orders:
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": order.ticket
        }

        result = mt5.order_send(request)

        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"🗑️ Deleted pending order {order.ticket}")
        else:
            print(f"⚠️ Failed to delete {order.ticket}")

# -------- RUN -------- #
print("\n🚨 CLOSING EVERYTHING...\n")

close_all_positions()
delete_all_pending()

print("\n✅ ALL ORDERS CLOSED")

mt5.shutdown()