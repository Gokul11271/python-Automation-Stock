# Filename: mt5_price_monitor.py

import MetaTrader5 as mt5
import time
import subprocess

# ---------------- USER SETTINGS ----------------
symbol = "XAUUSD_"       # Your trading symbol in MT5
buy_target = 3482.50     # Example Buy (Ask) target
ahk_exe = r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"   # correct exe
ahk_script = r"C:\Users\hp\OneDrive\Desktop\PlaceOrder.ahk"

# Path to your script
check_interval = 0.2     # Seconds between price checks
# ------------------------------------------------

# Initialize MT5
if not mt5.initialize():
    print("MT5 initialization failed")
    quit()

print(f"Monitoring {symbol} for Buy ≥ {buy_target}")

while True:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        time.sleep(check_interval)
        continue

    buy_price = tick.ask  # Buy (Ask) price
    print(f"Buy (Ask): {buy_price:.2f}")

    # --- Check Buy Target ---
   
    if buy_price >= buy_target:
        print(f"BUY target reached: {buy_price:.2f}. Triggering AHK..........................................")
        subprocess.Popen([ahk_exe, ahk_script, str(buy_price)])  # Pass price to AHK script
        break

mt5.shutdown()
