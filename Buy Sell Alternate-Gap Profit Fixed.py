import MetaTrader5 as mt5
import time

# -------- CONFIG -------- #
SYMBOL = "XAUUSD"
LOT = 0.01
GAP = 1.0
MAGIC = 2002
SLIPPAGE = 10

# -------- INIT -------- #
if not mt5.initialize():
    print("❌ MT5 Init Failed")
    quit()

mt5.symbol_select(SYMBOL, True)

# -------- HELPERS -------- #
def get_tick():
    return mt5.symbol_info_tick(SYMBOL)

def place_market(order_type):
    tick = get_tick()
    price = tick.ask if order_type == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": MAGIC,
        "comment": "Initial Market"
    }

    mt5.order_send(request)
    print(f"✅ MARKET {order_type} @ {price}")
    return price

def place_pending(order_type, price):
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": mt5.ORDER_TYPE_BUY_STOP if order_type == "BUY" else mt5.ORDER_TYPE_SELL_STOP,
        "price": price,
        "deviation": SLIPPAGE,
        "magic": MAGIC,
        "comment": "Triggered Pending"
    }

    mt5.order_send(request)
    print(f"📌 PENDING {order_type} @ {price}")

# -------- MAIN -------- #
def run():
    print("🚀 TRIGGER BASED BOT STARTED")

    # Initial orders
    buy_price = place_market("BUY")
    sell_price = buy_price - GAP

    place_market("SELL")

    last_positions = set()

    while True:
        time.sleep(1)

        positions = mt5.positions_get(symbol=SYMBOL)
        if not positions:
            continue

        current_tickets = set(p.ticket for p in positions)

        # Detect NEW trigger
        new_trades = current_tickets - last_positions

        for pos in positions:
            if pos.ticket in new_trades:
                if pos.type == mt5.POSITION_TYPE_BUY:
                    next_price = pos.price_open - GAP
                    place_pending("SELL", next_price)

                elif pos.type == mt5.POSITION_TYPE_SELL:
                    next_price = pos.price_open + GAP
                    place_pending("BUY", next_price)

        last_positions = current_tickets

# -------- RUN -------- #
run()