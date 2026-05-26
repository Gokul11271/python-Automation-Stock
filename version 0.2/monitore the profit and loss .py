import MetaTrader5 as mt5
import time

# =========================
# SETTINGS
# =========================

SYMBOL = "XAUUSD"

PROFIT_TARGET = 50    # Close all XAUUSD trades at +$50
LOSS_LIMIT = -20      # Close all XAUUSD trades at -$20

CHECK_INTERVAL = 2    # seconds

# =========================
# CONNECT TO MT5
# =========================

if not mt5.initialize():
    print("MT5 initialization failed")
    quit()

print("Connected to MT5")

# =========================
# CLOSE POSITION FUNCTION
# =========================

def close_position(position):

    symbol = position.symbol
    volume = position.volume
    ticket = position.ticket

    tick = mt5.symbol_info_tick(symbol)

    if position.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": 1000,
        "comment": "Auto Close XAUUSD",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"Closed XAUUSD position: {ticket}")
    else:
        print(f"Failed to close {ticket}: {result.retcode}")

# =========================
# MAIN LOOP
# =========================

while True:

    positions = mt5.positions_get(symbol=SYMBOL)

    if positions is None or len(positions) == 0:
        print("No XAUUSD positions open")
        time.sleep(CHECK_INTERVAL)
        continue

    total_profit = sum(pos.profit for pos in positions)

    print(f"XAUUSD Total Profit/Loss: {total_profit}")

    # PROFIT TARGET HIT
    if total_profit >= PROFIT_TARGET:

        print("Profit target reached. Closing all XAUUSD positions...")

        for pos in positions:
            close_position(pos)

        break

    # LOSS LIMIT HIT
    elif total_profit <= LOSS_LIMIT:

        print("Loss limit reached. Closing all XAUUSD positions...")

        for pos in positions:
            close_position(pos)

        break

    time.sleep(CHECK_INTERVAL)

mt5.shutdown()