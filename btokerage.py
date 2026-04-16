import MetaTrader5 as mt5

if not mt5.initialize():
    print("❌ MT5 init failed")
    quit()

info = mt5.symbol_info("XAUUSD")

print("Digits:", info.digits)
print("Point:", info.point)
print("Min Lot:", info.volume_min)
print("Lot Step:", info.volume_step)
print("Stop Level:", info.trade_stops_level)
print("Freeze Level:", info.trade_freeze_level)