# Filename: mt5_price_monitor.py

import MetaTrader5 as mt5
import time
import subprocess

# ---------------- USER SETTINGS ----------------
symbol = "XAUUSD_"       # <- Replace with the exact symbol from your broker
buy_target  = 3496.50    # Example Buy (Ask) target
sell_target = 3495.00    # Example Sell (Bid) target
ahk_script  = r"C:\Path\To\PlaceOrder.ahk"  # AHK script path
check_interval = 0.2     # Seconds between price checks
# ------------------------------------------------

# Initialize MT5
if not mt5.initialize():
    print("MT5 initialization failed")
    input("Press Enter to exit...")
    quit()

# --- Print all available symbols so you can confirm the correct one ---
print("Available symbols from your broker:")
symbols = mt5.symbols_get()
for s in symbols:
    print(" -", s.name)
print("\nUsing symbol:", symbol)
print(f"Monitoring {symbol} for Buy ≥ {buy_target} or Sell ≤ {sell_target}\n")

# --- Monitoring loop ---
while True:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"Symbol {symbol} not found! Check above list for correct name.")
        time.sleep(check_interval)
        continue

    buy_price = tick.ask  # Buy (Ask)
    sell_price = tick.bid # Sell (Bid)
    print(f"Buy (Ask): {buy_price:.2f} | Sell (Bid): {sell_price:.2f}")

    # --- Check Buy Target ---
    if buy_price >= buy_target:
        print(f"BUY target reached: {buy_price:.2f}. Triggering AHK...")
        subprocess.Popen(["autohotkey", ahk_script, "BUY", str(buy_price)])
        break

    # --- Check Sell Target ---
    if sell_price <= sell_target:
        print(f"SELL target reached: {sell_price:.2f}. Triggering AHK...")
        subprocess.Popen(["autohotkey", ahk_script, "SELL", str(sell_price)])
        break

    time.sleep(check_interval)

mt5.shutdown()

# Keep terminal open
input("Press Enter to exit...")
