import MetaTrader5 as mt5

print("🔄 Initializing MetaTrader 5...")

# Initialize connection
if not mt5.initialize():
    print("❌ Initialize() failed, error =", mt5.last_error())
    quit()
print("✅ MT5 connection successful!\n")

# ------------------- Detect Symbol ------------------- #
def detect_symbol():
    """
    Automatically detects a tradeable symbol.
    - Tries to get the first Market Watch symbol
    - Prints details about it
    """
    symbols = mt5.symbols_get()
    if not symbols or len(symbols) == 0:
        print("❌ No symbols found in Market Watch.")
        return None

    # Pick the first available symbol
    symbol = symbols[0].name
    print(f"🔍 Auto-detected symbol: {symbol}")
    return symbol

# Detect and display details
symbol = detect_symbol()
if symbol is None:
    mt5.shutdown()
    quit()

# Select the detected symbol
if not mt5.symbol_select(symbol, True):
    print(f"❌ Failed to select symbol: {symbol}")
    mt5.shutdown()
    quit()

# Get symbol info
symbol_info = mt5.symbol_info(symbol)
if symbol_info is None:
    print(f"❌ Could not retrieve info for symbol: {symbol}")
    mt5.shutdown()
    quit()

# Print detailed info
print("\n📊 Symbol Information:")
print(f"Name: {symbol_info.name}")
print(f"Digits: {symbol_info.digits}")
print(f"Point Size: {symbol_info.point}")
print(f"Trade Mode: {symbol_info.trade_mode}")
print(f"Spread: {symbol_info.spread}")
print(f"Volume Min: {symbol_info.volume_min}")
print(f"Volume Max: {symbol_info.volume_max}")
print(f"Volume Step: {symbol_info.volume_step}")
print(f"Trade Contract Size: {symbol_info.trade_contract_size}")
print(f"Trade Stops Level: {symbol_info.trade_stops_level}")
print(f"Trade Freeze Level: {symbol_info.trade_freeze_level}")
print(f"Session Volume: {symbol_info.volume}")

# ------------------- Optional: Show All Symbols ------------------- #
print("\n📜 Market Watch Symbols:")
for s in mt5.symbols_get():
    print("-", s.name,end="")

# Shutdown connection
mt5.shutdown()
print("\n✅ MT5 connection closed.")
