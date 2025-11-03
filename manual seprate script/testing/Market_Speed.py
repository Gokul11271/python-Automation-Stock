import MetaTrader5 as mt5
import time
from datetime import datetime

SYMBOL = "XAUUSD_"
REFRESH_RATE = 1
WINDOW = 10

if not mt5.initialize():
    print("MT5 init failed:", mt5.last_error())
    quit()

speeds = []
last_price = None
last_time = None

def draw_bar(speed):
    # normalize to 0-1 for display
    val = min(speed / 1.0, 1)   # adjust 1.0 to max expected speed
    bar_len = int(val * 50)
    return "█" * bar_len + "-" * (50 - bar_len)

print(f"Speedometer started for {SYMBOL}...\n")

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

            if avg_speed > 0.1:
                level = "HIGH"
            elif avg_speed > 0.05:
                level = "MEDIUM"
            else:
                level = "LOW"

            bar = draw_bar(avg_speed)
            print(f"{datetime.now().strftime('%H:%M:%S')} | {bar} | {avg_speed:.5f} | {level}")

    last_price = price
    last_time = t
    time.sleep(REFRESH_RATE)
