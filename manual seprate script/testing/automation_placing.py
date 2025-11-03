import MetaTrader5 as mt5
import time
from datetime import datetime

SYMBOL = "XAUUSD_"
REFRESH_RATE = 1
WINDOW = 10

# Trading parameters
MAX_SPEED = 0.10      # above this = pause trading
BUY_VOLUME = 0.01
SELL_VOLUME = 0.01

if not mt5.initialize():
    print("MT5 init failed:", mt5.last_error())
    quit()

speeds = []
last_price = None
last_time = None
trading_allowed = True

print(f"Auto-Trade Controller started for {SYMBOL}...\n")

def place_order(action, volume):
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        return False
    price = tick.ask if action == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": price,
        "deviation": 50,
        "magic": 12345,
        "comment": "speed_based_trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Order failed: {result.comment}")
        return False
    print(f"{datetime.now().strftime('%H:%M:%S')} | ✅ {action} placed at {price}")
    return True


while True:
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        print("No tick data")
        time.sleep(1)
        continue

    price = tick.bid
    t = tick.time

    if last_price and last_time:
        diff = abs(price - last_price)
        td = t - last_time
        if td > 0:
            speed = diff / td
            speeds.append(speed)
            if len(speeds) > WINDOW:
                speeds.pop(0)
            avg_speed = sum(speeds) / len(speeds)

            # ----- SPEED DECISION -----
            if avg_speed > MAX_SPEED:
                level = "HIGH"
                if trading_allowed:
                    print(f"{datetime.now().strftime('%H:%M:%S')} | ⚠️ High speed ({avg_speed:.4f}) → PAUSING trading")
                    trading_allowed = False
            else:
                level = "LOW/MEDIUM"
                if not trading_allowed:
                    print(f"{datetime.now().strftime('%H:%M:%S')} | ✅ Speed normal ({avg_speed:.4f}) → RESUMING trading")
                    trading_allowed = True

            print(f"{datetime.now().strftime('%H:%M:%S')} | Speed: {avg_speed:.4f} | Market: {level}")

            # ----- TRADING LOGIC -----
            if trading_allowed:
                # example: simple momentum signal
                if price > last_price:
                    place_order("BUY", BUY_VOLUME)
                elif price < last_price:
                    place_order("SELL", SELL_VOLUME)

    last_price = price
    last_time = t
    time.sleep(REFRESH_RATE)
