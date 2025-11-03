import MetaTrader5 as mt5

# Initialize connection
if not mt5.initialize():
    print("Failed to initialize MetaTrader5:", mt5.last_error())
    quit()

# Login to your account (optional if already logged in in MT5 terminal)
# Replace with your account details if needed:
# account = 12345678
# password = "your_password"
# server = "YourBroker-Server"
# mt5.login(account, password, server)

# Get account information
account_info = mt5.account_info()

if account_info is None:
    print("Failed to get account info:", mt5.last_error())
else:
    print("=== Account Info ===")
    print(f"Login ID      : {account_info.login}")
    print(f"Balance       : {account_info.balance}")
    print(f"Equity        : {account_info.equity}")
    print(f"Free Margin   : {account_info.margin_free}")
    print(f"Margin Level  : {account_info.margin_level}")
    print(f"Currency      : {account_info.currency}")
    print(f"Leverage      : {account_info.leverage}")
    simulated_balance = account_info.balance + 1000  # Add hypothetical profit
print(f"Simulated Balance: {simulated_balance}")


# Shutdown connection
mt5.shutdown()
