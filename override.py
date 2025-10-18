# #!/usr/bin/env python3
# """
# mt5_balance_manager.py

# Features:
# - Simulation mode (virtual balance you can overwrite) and LIVE mode (connects to MT5).
# - After each executed order it updates internal bookkeeping.
# - If you set OVERRIDE_BALANCE, the virtual balance will be set to that value (for simulation/testing).
# - Supports TARGET_BALANCE (close all when virtual/account balance reaches it) OR TARGET_PROFIT (close when cumulative profit reaches it).
# - Splits a target profit among existing positions (evenly or custom percentages).
# - Allows scheduling a time to close all positions.
# - Persistent state in state.json so virtual balance survives restarts.

# Limitations:
# - Cannot force the broker to change the real account balance.
# - Partial-closing is implemented by sending market orders with volumes matching requested closes. Be careful with minimum volumes and lot steps in your broker.

# Author: ChatGPT (GPT-5 Thinking mini)
# """

# import MetaTrader5 as mt5
# import time
# import json
# import os
# from datetime import datetime, time as dtime, timedelta
# from decimal import Decimal, ROUND_DOWN

# STATE_FILE = "mt5_balance_manager_state.json"

# # ------------------- CONFIG ------------------- #
# CONFIG = {
#     # Mode: set to False to run simulation/local virtual-balance only (safe for testing).
#     "LIVE": True,

#     # If LIVE=True, the script will attempt to initialize MT5 and operate on the connected account.
#     # If False, it only simulates behavior using a virtual balance kept in STATE_FILE.

#     # Virtual balance persistence and override (simulation)
#     "ENABLE_VIRTUAL_BALANCE": True,
#     "START_VIRTUAL_BALANCE": 25000.0,   # initial virtual balance (if state not found)
#     "OVERRIDE_BALANCE": 200,          # set to a number to forcibly overwrite virtual balance on start, e.g. 150 or 130 or 180

#     # Targets
#     "TARGET_BALANCE": None,            # e.g. 100.0 -> close all positions when virtual/account balance reaches this
#     "TARGET_PROFIT": 10.0,            # alternative: close when cumulative net profit across positions reaches this (absolute)
#     "SPLIT_MODE": "even",              # "even" or "custom"
#     "CUSTOM_SPLITS": None,             # e.g. [0.5, 0.3, 0.2] for uneven split (must sum to 1). Applies to the current open positions ordering.

#     # Automatic close settings
#     "CLOSE_TIME_UTC": None,            # e.g. "15:00" (24h) -> close all at this UTC time every day; set None to disable
#     "CHECK_INTERVAL": 5,               # seconds between checks

#     # Order settings
#     "DEVIATION": 20,                   # allowed slippage in points (converted to price units below)
#     "MAGIC": 123456,
#     "COMMENT": "mt5_balance_manager",

#     # Attempt/retry settings
#     "ORDER_RETRY_ATTEMPTS": 5,
#     "ORDER_RETRY_DELAY": 1.0,          # seconds between retries
# }
# # ------------------- End CONFIG ------------------- #

# # Small util functions
# def load_state():
#     if os.path.exists(STATE_FILE):
#         with open(STATE_FILE, "r") as f:
#             return json.load(f)
#     return {}

# def save_state(state):
#     with open(STATE_FILE, "w") as f:
#         json.dump(state, f, indent=2)

# def format_money(x):
#     return float(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_DOWN))

# # MT5 helpers
# def connect_mt5():
#     if not mt5.initialize():
#         raise RuntimeError("MT5 initialize() failed. Is terminal running and logged in?")
#     return True

# def shutdown_mt5():
#     try:
#         mt5.shutdown()
#     except Exception:
#         pass

# def get_account_info():
#     info = mt5.account_info()
#     if info is None:
#         raise RuntimeError("Could not get account info (are you connected?).")
#     return info

# def symbol_select(symbol):
#     si = mt5.symbol_info(symbol)
#     if si is None:
#         raise RuntimeError(f"Symbol {symbol} not found in Market Watch.")
#     if not si.visible:
#         mt5.symbol_select(symbol, True)
#     return mt5.symbol_info(symbol)

# def get_tick(symbol):
#     return mt5.symbol_info_tick(symbol)

# def positions_get(symbol=None):
#     if symbol:
#         return mt5.positions_get(symbol=symbol) or []
#     return mt5.positions_get() or []

# def send_order_with_retry(request, attempts=CONFIG["ORDER_RETRY_ATTEMPTS"], delay=CONFIG["ORDER_RETRY_DELAY"]):
#     for attempt in range(1, attempts+1):
#         result = mt5.order_send(request)
#         if result is None:
#             time.sleep(delay)
#             continue
#         if result.retcode == mt5.TRADE_RETCODE_DONE or result.retcode == 10009 or result.retcode == 10008:
#             return result
#         # For many MT5 builds, retcode 10009/10008 can be success depending on server; handle gracefully.
#         if result.retcode != mt5.TRADE_RETCODE_DONE:
#             # Attempt again for transient issues
#             time.sleep(delay)
#     # last attempt result returned
#     return result

# def place_market_order(symbol, volume, buy=True, deviation_points=None, magic=None, comment=None):
#     tick = get_tick(symbol)
#     if tick is None:
#         raise RuntimeError("Couldn't get tick for symbol " + symbol)
#     price = tick.ask if buy else tick.bid
#     order_type = mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL
#     deviation = (deviation_points or CONFIG["DEVIATION"])
#     request = {
#         "action": mt5.TRADE_ACTION_DEAL,
#         "symbol": symbol,
#         "volume": float(volume),
#         "type": order_type,
#         "price": price,
#         "deviation": int(deviation),
#         "magic": magic or CONFIG["MAGIC"],
#         "comment": comment or CONFIG["COMMENT"],
#         "type_filling": mt5.ORDER_FILLING_IOC,
#         "type_time": mt5.ORDER_TIME_GTC,
#     }
#     result = send_order_with_retry(request)
#     return result

# def close_position(position):
#     """
#     Close a single position by sending an opposite market order with equal volume.
#     position must be a object from mt5.positions_get() (it has fields: ticket, symbol, volume, type, etc.)
#     """
#     symbol = position.symbol
#     pos_volume = float(position.volume)
#     pos_type = int(position.type)  # 0=buy, 1=sell
#     # to close buy -> send sell; to close sell -> send buy
#     buy_close = (pos_type == 1)  # if position is sell, we buy to close
#     return place_market_order(symbol, pos_volume, buy=buy_close, magic=CONFIG["MAGIC"], comment=f"close_pos_{position.ticket}")

# def close_all_positions():
#     positions = positions_get()
#     results = []
#     for pos in positions:
#         res = close_position(pos)
#         results.append((pos.ticket, res))
#     return results

# # Business logic
# class BalanceManager:
#     def __init__(self, config):
#         self.config = config
#         self.state = load_state()
#         if "virtual_balance" not in self.state:
#             self.state["virtual_balance"] = config["START_VIRTUAL_BALANCE"]
#         # apply override if requested
#         if config["OVERRIDE_BALANCE"] is not None:
#             self.state["virtual_balance"] = float(config["OVERRIDE_BALANCE"])
#         save_state(self.state)

#     def get_virtual_balance(self):
#         return float(self.state.get("virtual_balance", self.config["START_VIRTUAL_BALANCE"]))

#     def set_virtual_balance(self, value):
#         self.state["virtual_balance"] = float(value)
#         save_state(self.state)

#     def add_to_virtual_balance(self, delta):
#         vb = self.get_virtual_balance()
#         vb += float(delta)
#         self.set_virtual_balance(vb)

#     def sync_from_account(self):
#         # When in LIVE, you can compute virtual_balance = actual balance + (optionally) override
#         if self.config["LIVE"]:
#             ai = get_account_info()
#             self.set_virtual_balance(float(ai.balance))
#             return float(ai.balance)
#         else:
#             return self.get_virtual_balance()

#     def compute_positions_profit(self):
#         """
#         Sum of profit (realized/unrealized) across current open positions.
#         Using mt5.positions_get() 'profit' field for each position.
#         """
#         if self.config["LIVE"]:
#             positions = positions_get()
#             total_profit = 0.0
#             for p in positions:
#                 total_profit += float(p.profit)
#             return total_profit
#         else:
#             # In simulation we keep a list of trades in the state and compute unrealized as given
#             # For simplicity, if we have stored trades, we sum stored 'current_profit' fields
#             trades = self.state.get("trades", [])
#             return sum([t.get("current_profit", 0.0) for t in trades])

#     def distribute_target_to_positions(self, target_amount, splits=None):
#         """
#         Compute how to split `target_amount` among existing positions.
#         Returns list of (position_ticket, target_profit_for_position) ordered the same way as positions_get()
#         Splits: if None and SPLIT_MODE == 'even' then split equally, or use CUSTOM_SPLITS list explicitly.
#         """
#         positions = positions_get()
#         n = len(positions)
#         if n == 0:
#             return []

#         if self.config["SPLIT_MODE"] == "custom" and (self.config["CUSTOM_SPLITS"]):
#             splits = self.config["CUSTOM_SPLITS"]
#             if len(splits) != n:
#                 # If mismatch, fall back to even
#                 splits = None

#         if splits is None:
#             share = target_amount / n
#             return [(p.ticket, float(format_money(share))) for p in positions]
#         else:
#             # normalize provided splits if they sum not exactly 1
#             ssum = sum(splits)
#             if abs(ssum - 1.0) > 1e-6:
#                 splits = [float(x)/ssum for x in splits]
#             result = []
#             for p, s in zip(positions, splits):
#                 result.append((p.ticket, float(format_money(target_amount * s))))
#             return result

#     def check_and_close_conditions(self):
#         """
#         Evaluate configured target conditions and close if satisfied.
#         """
#         # 1) scheduled close time
#         if self.config["CLOSE_TIME_UTC"]:
#             now = datetime.utcnow().time()
#             hhmm = self.config["CLOSE_TIME_UTC"].split(":")
#             close_t = dtime(int(hhmm[0]), int(hhmm[1]))
#             # close if now is equal or past close_t today (this simple method might close repeatedly)
#             # We'll close only once per day; track last_close_date in state.
#             last_close_date = self.state.get("last_close_date")
#             today_date = datetime.utcnow().date().isoformat()
#             if now >= close_t and last_close_date != today_date:
#                 print(f"[{datetime.utcnow().isoformat()}] Scheduled close time reached -> closing ALL positions.")
#                 res = close_all_positions()
#                 self.state["last_close_date"] = today_date
#                 save_state(self.state)
#                 return res

#         # 2) target balance or target profit
#         virtual_balance = self.get_virtual_balance()
#         positions_profit = self.compute_positions_profit()
#         positions = positions_get()
#         cumulative_metric = None

#         if self.config["TARGET_BALANCE"] is not None:
#             # If LIVE: actual balance + positions_profit (unrealized) -> virtualish total
#             if self.config["LIVE"]:
#                 acct = get_account_info()
#                 total_estimated = float(acct.balance) + float(positions_profit)
#             else:
#                 total_estimated = virtual_balance + positions_profit
#             if total_estimated >= float(self.config["TARGET_BALANCE"]):
#                 print(f"[{datetime.utcnow().isoformat()}] TARGET_BALANCE reached ({total_estimated} >= {self.config['TARGET_BALANCE']}) -> closing all.")
#                 return close_all_positions()
#         elif self.config["TARGET_PROFIT"] is not None:
#             # Close if total positions profit (unrealized) >= target_profit
#             if positions_profit >= float(self.config["TARGET_PROFIT"]):
#                 print(f"[{datetime.utcnow().isoformat()}] TARGET_PROFIT reached ({positions_profit} >= {self.config['TARGET_PROFIT']}) -> closing all.")
#                 return close_all_positions()

#         return None

#     def on_new_trade_update_state(self, trade_result):
#         """
#         Called after an order_send result is positive; update virtual balance and store trade record (simulation).
#         trade_result: the object returned by mt5.order_send
#         """
#         # In simulation: we'll append to state["trades"] a record so unrealized profit tracking is possible (user can update later).
#         if not self.config["LIVE"]:
#             trades = self.state.get("trades", [])
#             rec = {
#                 "time": datetime.utcnow().isoformat(),
#                 "order_result": {
#                     "retcode": getattr(trade_result, "retcode", str(trade_result)),
#                     "order": getattr(trade_result, "order", None),
#                     "price": getattr(trade_result, "price", None),
#                 },
#                 # For simulation, require user to provide 'current_profit' externally or we set 0
#                 "current_profit": 0.0
#             }
#             trades.append(rec)
#             self.state["trades"] = trades
#             save_state(self.state)
#         # For LIVE mode: inform user that MT5 will reflect balance change when trades are closed/realized.
#         # We DO NOT modify broker balance.

#     def summary(self):
#         vb = self.get_virtual_balance()
#         pos_profit = self.compute_positions_profit()
#         positions = positions_get()
#         print("----- SUMMARY -----")
#         print("Mode:", "LIVE" if self.config["LIVE"] else "SIMULATION")
#         print("Virtual Balance:", vb)
#         if self.config["LIVE"]:
#             ai = get_account_info()
#             print("Real Account balance:", ai.balance, " equity:", ai.equity)
#         print("Open positions count:", len(positions))
#         print("Positions profit (sum):", pos_profit)
#         print("-------------------")

# # Example main loop
# def main_loop():
#     try:
#         if CONFIG["LIVE"]:
#             connect_mt5()
#             print("Connected to MT5.")
#         manager = BalanceManager(CONFIG)

#         print("Starting loop. Current virtual balance:", manager.get_virtual_balance())

#         # Example: you can call place_market_order(...) elsewhere (e.g., user triggers). Here we demonstrate monitoring loop.
#         last_summary = None
#         while True:
#             # update virtual balance if LIVE (sync)
#             if CONFIG["LIVE"]:
#                 manager.sync_from_account()

#             # check conditions
#             res = manager.check_and_close_conditions()
#             if res is not None:
#                 # res might be list of close results or similar
#                 print("Close action executed. Results:")
#                 for item in res:
#                     print(item)

#             # print periodic summary every minute
#             now = time.time()
#             if last_summary is None or (now - last_summary) > 60:
#                 manager.summary()
#                 last_summary = now

#             time.sleep(CONFIG["CHECK_INTERVAL"])
#     except KeyboardInterrupt:
#         print("Interrupted by user.")
#     finally:
#         shutdown_mt5()
#         print("Shutdown MT5 (if it was initialized).")

# # Minimal demonstration helper: splits target profit among open positions and prints the suggested per-position targets.
# def demo_split_print(manager, target_amount):
#     splits = manager.distribute_target_to_positions(target_amount)
#     if not splits:
#         print("No positions to split among.")
#         return
#     print("Splits for target", target_amount)
#     for ticket, amt in splits:
#         print(f"Position {ticket}: target {amt}")

# # If user wants to programmatically place a new order with virtual-balance override behavior:
# def place_order_and_update(manager, symbol, volume, buy=True):
#     """
#     Place a market order (live mode) or simulate a placed order in simulation mode.
#     If OVERRIDE_BALANCE is set (simulation), it sets virtual_balance immediately to that override value.
#     """
#     if not CONFIG["LIVE"]:
#         # Simulate an order: just add a trade record and optionally override balance
#         print("SIMULATION: placing simulated order", symbol, volume, "buy:", buy)
#         fake_result = {"retcode": "SIM_OK", "price": 0.0}
#         manager.on_new_trade_update_state(fake_result)
#         if CONFIG["OVERRIDE_BALANCE"] is not None:
#             manager.set_virtual_balance(CONFIG["OVERRIDE_BALANCE"])
#             print("SIMULATION: virtual balance overwritten to", CONFIG["OVERRIDE_BALANCE"])
#         return fake_result
#     else:
#         # LIVE mode: place the market order via MT5
#         res = place_market_order(symbol, volume, buy=buy)
#         if res is None:
#             print("Order send returned None.")
#             return None
#         if getattr(res, "retcode", None) in (mt5.TRADE_RETCODE_DONE, 10009, 10008):
#             manager.on_new_trade_update_state(res)
#             print("Order placed successfully:", res)
#             return res
#         else:
#             print("Order failed:", res)
#             return res

# # If run as script, start the main loop
# if __name__ == "__main__":
#     # Example quick usage:
#     # - To test: keep CONFIG["LIVE"]=False, set OVERRIDE_BALANCE to 150 to simulate balance overwrite on start.
#     # - To use real MT5: set CONFIG["LIVE"]=True and ensure terminal is running and logged in (demo recommended).
#     #
#     # You can modify CONFIG at the top or programmatically.
#     #
#     print("mt5_balance_manager starting. Config (summary):")
#     cpy = CONFIG.copy()
#     cpy["OVERRIDE_BALANCE"] = CONFIG["OVERRIDE_BALANCE"]
#     print(json.dumps(cpy, indent=2))
#     main_loop()
#!/usr/bin/env python3
"""
MT5 Enhanced Virtual Balance Override Manager

Features:
- Tracks a virtual balance independently of real MT5 account balance.
- Full override support: force virtual balance to any value at any time.
- Automatically distributes target profit to open positions.
- Auto-closes positions when virtual balance reaches TARGET_BALANCE or cumulative profit reaches TARGET_PROFIT.
- Works in LIVE or simulation mode.
- Scheduled daily closing supported.
"""

import MetaTrader5 as mt5
import time
import json
import os
from datetime import datetime, time as dtime
from decimal import Decimal, ROUND_DOWN

STATE_FILE = "mt5_balance_manager_state.json"

# ------------------- CONFIG ------------------- #
CONFIG = {
    "LIVE": True,                     # True = connect to MT5, False = simulation
    "ENABLE_VIRTUAL_BALANCE": True,
    "START_VIRTUAL_BALANCE": 200.0,
    "OVERRIDE_BALANCE": 200,          # Force virtual balance at start
    "TARGET_BALANCE": None,           # Close all positions if virtual balance reaches this
    "TARGET_PROFIT": 100.0,           # Close all if cumulative profit reaches this
    "SPLIT_MODE": "even",             # "even" or "custom"
    "CUSTOM_SPLITS": None,            # e.g., [0.5,0.3,0.2]
    "CLOSE_TIME_UTC": None,           # e.g., "15:00"
    "CHECK_INTERVAL": 5,              # seconds
    "DEVIATION": 20,
    "MAGIC": 123456,
    "COMMENT": "mt5_virtual_balance_manager",
    "ORDER_RETRY_ATTEMPTS": 5,
    "ORDER_RETRY_DELAY": 1.0
}
# ------------------- END CONFIG ------------------- #

# ------------------- Utilities ------------------- #
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def format_money(x):
    return float(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_DOWN))

# ------------------- MT5 Helpers ------------------- #
def connect_mt5():
    if not mt5.initialize():
        raise RuntimeError("MT5 initialize() failed. Is terminal running?")
    return True

def shutdown_mt5():
    try:
        mt5.shutdown()
    except:
        pass

def get_tick(symbol):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"Cannot get tick for {symbol}")
    return tick

def positions_get(symbol=None):
    return mt5.positions_get(symbol=symbol) or []

def send_order_with_retry(request):
    for _ in range(CONFIG["ORDER_RETRY_ATTEMPTS"]):
        res = mt5.order_send(request)
        if res is None:
            time.sleep(CONFIG["ORDER_RETRY_DELAY"])
            continue
        if res.retcode == mt5.TRADE_RETCODE_DONE or res.retcode in (10008, 10009):
            return res
        time.sleep(CONFIG["ORDER_RETRY_DELAY"])
    return res

def place_market_order(symbol, volume, buy=True):
    tick = get_tick(symbol)
    price = tick.ask if buy else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "price": price,
        "deviation": CONFIG["DEVIATION"],
        "magic": CONFIG["MAGIC"],
        "comment": CONFIG["COMMENT"],
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC
    }
    return send_order_with_retry(request)

def close_position(position):
    buy_close = (position.type == mt5.POSITION_TYPE_SELL)
    return place_market_order(position.symbol, position.volume, buy=buy_close)

def close_all_positions():
    results = []
    for pos in positions_get():
        res = close_position(pos)
        results.append((pos.ticket, res))
    return results

# ------------------- Balance Manager ------------------- #
class BalanceManager:
    def __init__(self, config):
        self.config = config
        self.state = load_state()
        if "virtual_balance" not in self.state:
            self.state["virtual_balance"] = config["START_VIRTUAL_BALANCE"]
        if config["OVERRIDE_BALANCE"] is not None:
            self.state["virtual_balance"] = float(config["OVERRIDE_BALANCE"])
        save_state(self.state)

    def get_virtual_balance(self):
        return float(self.state.get("virtual_balance", self.config["START_VIRTUAL_BALANCE"]))

    def set_virtual_balance(self, value):
        self.state["virtual_balance"] = float(value)
        save_state(self.state)

    def add_virtual_balance(self, delta):
        self.set_virtual_balance(self.get_virtual_balance() + float(delta))

    def override_virtual_balance(self, new_value):
        """Force virtual balance to a specific value anytime"""
        self.set_virtual_balance(float(new_value))
        print(f"[{datetime.utcnow().isoformat()}] Virtual balance overridden to {new_value}")

    def compute_positions_profit(self):
        if self.config["LIVE"]:
            return sum([float(p.profit) for p in positions_get()])
        else:
            trades = self.state.get("trades", [])
            return sum([t.get("current_profit",0) for t in trades])

    def distribute_target_to_positions(self, target_amount):
        positions = positions_get()
        n = len(positions)
        if n == 0: return []
        splits = None
        if self.config["SPLIT_MODE"]=="custom" and self.config["CUSTOM_SPLITS"]:
            splits = self.config["CUSTOM_SPLITS"]
            if len(splits) != n: splits = None
        if splits is None:
            share = target_amount / n
            return [(p.ticket, float(format_money(share))) for p in positions]
        else:
            ssum = sum(splits)
            splits = [x/ssum for x in splits]
            return [(p.ticket, float(format_money(target_amount*s))) for p,s in zip(positions,splits)]

    def check_targets_and_close(self):
        vb = self.get_virtual_balance()
        pos_profit = self.compute_positions_profit()
        # Check TARGET_BALANCE
        if self.config["TARGET_BALANCE"] and vb >= self.config["TARGET_BALANCE"]:
            print(f"[{datetime.utcnow().isoformat()}] Virtual balance target reached: {vb}")
            res = close_all_positions()
            return res
        # Check TARGET_PROFIT
        if self.config["TARGET_PROFIT"] and pos_profit >= self.config["TARGET_PROFIT"]:
            print(f"[{datetime.utcnow().isoformat()}] Target profit reached: {pos_profit}")
            res = close_all_positions()
            return res
        return None

    def update_virtual_balance_from_positions(self):
        if self.config["LIVE"]:
            positions = positions_get()
            unrealized = sum([p.profit for p in positions])
            self.add_virtual_balance(unrealized)

    def summary(self):
        print("----- SUMMARY -----")
        print("Mode:", "LIVE" if self.config["LIVE"] else "SIMULATION")
        print("Virtual Balance:", self.get_virtual_balance())
        if self.config["LIVE"]:
            ai = mt5.account_info()
            print("Real Account balance:", ai.balance, "equity:", ai.equity)
        positions = positions_get()
        print("Open positions count:", len(positions))
        print("Positions profit (sum):", self.compute_positions_profit())
        print("-------------------")

    def record_trade_simulation(self, trade_result):
        trades = self.state.get("trades", [])
        trades.append({
            "time": datetime.utcnow().isoformat(),
            "order_result": trade_result,
            "current_profit": 0.0
        })
        self.state["trades"] = trades
        save_state(self.state)

# ------------------- Script Functions ------------------- #
def place_order_and_update(manager, symbol, volume, buy=True):
    if CONFIG["LIVE"]:
        res = place_market_order(symbol, volume, buy=buy)
        if res and getattr(res,"retcode",None) in (mt5.TRADE_RETCODE_DONE,10009,10008):
            manager.update_virtual_balance_from_positions()
            print(f"[{datetime.utcnow().isoformat()}] Order placed successfully:", res)
        return res
    else:
        print(f"[{datetime.utcnow().isoformat()}] Simulation: placing order {symbol} {volume} buy={buy}")
        manager.record_trade_simulation({"sim":True})
        if CONFIG["OVERRIDE_BALANCE"] is not None:
            manager.set_virtual_balance(CONFIG["OVERRIDE_BALANCE"])
        return {"sim":True}

# ------------------- Main Loop ------------------- #
def main_loop():
    try:
        if CONFIG["LIVE"]: connect_mt5()
        manager = BalanceManager(CONFIG)
        print(f"[{datetime.utcnow().isoformat()}] Starting loop. Virtual Balance: {manager.get_virtual_balance()}")
        last_summary = None

        while True:
            if CONFIG["LIVE"]:
                manager.update_virtual_balance_from_positions()

            res = manager.check_targets_and_close()
            if res is not None:
                print(f"[{datetime.utcnow().isoformat()}] Close action executed:", res)

            now = time.time()
            if last_summary is None or now - last_summary > 60:
                manager.summary()
                last_summary = now

            time.sleep(CONFIG["CHECK_INTERVAL"])

    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        shutdown_mt5()
        print("MT5 shutdown complete")

# ------------------- Run Script ------------------- #
if __name__ == "__main__":
    print(f"[{datetime.utcnow().isoformat()}] Starting mt5_virtual_balance_manager...")
    main_loop()
