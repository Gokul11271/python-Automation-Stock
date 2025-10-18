#!/usr/bin/env python3
"""
mt5_hypothetical_balance.py

Safe helper: read MT5 account info + history, compute a hypothetical balance/profit
This script NEVER modifies MT5 account history or balances.

Usage examples:
  python mt5_hypothetical_balance.py --days 30 --virtual_add 500.0 --csv out.csv
  python mt5_hypothetical_balance.py --from 2025-01-01 --to 2025-10-01 --virtual_add -100.0

Requires:
  pip install MetaTrader5 pandas
"""

import argparse
import sys
from datetime import datetime, timedelta
import MetaTrader5 as mt5
import pandas as pd

def init_mt5():
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    # Optionally you can specify path: mt5.initialize(path="C:\\Program Files\\MetaTrader 5\\terminal64.exe")

def shutdown_mt5():
    mt5.shutdown()

def get_account_info():
    info = mt5.account_info()
    if info is None:
        raise SystemExit(f"Failed to get account info: {mt5.last_error()}")
    return info

def parse_date(s):
    # Accept YYYY-MM-DD
    return datetime.strptime(s, "%Y-%m-%d")

def fetch_history(from_dt, to_dt):
    """
    Fetch closed deals and closed positions in the given time range.
    Returns two pandas DataFrames: deals_df, positions_df
    """
    # Deals
    deals = mt5.history_deals_get(from_dt, to_dt)
    if deals is None:
        # history_deals_get returns None on error or empty result; check last_error
        last = mt5.last_error()
        if last and last[0] != 0:
            raise SystemExit(f"Error fetching deals: {last}")
        deals = []
    deals_df = pd.DataFrame(list(deals))
    # Positions (closed positions are in history_positions_get)
    positions = mt5.history_positions_get(from_dt, to_dt)
    if positions is None:
        last = mt5.last_error()
        if last and last[0] != 0:
            raise SystemExit(f"Error fetching positions: {last}")
        positions = []
    positions_df = pd.DataFrame(list(positions))
    return deals_df, positions_df

def aggregate_profit(deals_df, positions_df):
    """
    Compute total realized profit from deals/positions.
    Prefer deals_df profit column if available; otherwise sum positions_df.profit
    """
    total_profit = 0.0
    if not deals_df.empty and 'profit' in deals_df.columns:
        total_profit = float(deals_df['profit'].sum())
    elif not positions_df.empty and 'profit' in positions_df.columns:
        total_profit = float(positions_df['profit'].sum())
    return total_profit

def main():
    parser = argparse.ArgumentParser(description="Compute hypothetical MT5 balance from real history (read-only).")
    group = parser.add_mutually_exclusive_group(required=False)
    parser.add_argument("--days", type=int, default=30, help="How many past days of history to fetch (default: 30).")
    parser.add_argument("--from", dest="from_date", type=str, help="Start date YYYY-MM-DD (overrides --days).")
    parser.add_argument("--to", dest="to_date", type=str, help="End date YYYY-MM-DD (overrides --days).")
    parser.add_argument("--virtual_add", type=float, default=0.0,
                        help="Amount to virtually add (positive) or subtract (negative) from balance for hypothetical scenario.")
    parser.add_argument("--csv", type=str, default=None, help="Optional: export combined history + hypothetical columns to this CSV path.")
    args = parser.parse_args()

    init_mt5()
    try:
        info = get_account_info()
        account = {
            "login": info.login,
            "name": info.name,
            "server": info.server,
            "balance": float(info.balance),
            "equity": float(info.equity),
            "currency": info.currency
        }

        # Determine date range
        if args.from_date:
            from_dt = parse_date(args.from_date)
            if args.to_date:
                to_dt = parse_date(args.to_date)
            else:
                to_dt = datetime.now()
        else:
            to_dt = datetime.now()
            from_dt = to_dt - timedelta(days=args.days)

        # MetaTrader requires timezone-aware datetimes or naive in local; mt5.history_deals_get expects datetime objects
        # Fetch history
        deals_df, positions_df = fetch_history(from_dt, to_dt)

        # Compute realized profit
        realized_profit = aggregate_profit(deals_df, positions_df)

        # Current account values from server (real-time)
        real_balance = account['balance']
        real_equity = account['equity']

        # Hypothetical scenario: add virtual_add to balance (this is purely local calculation)
        virtual_add = float(args.virtual_add)
        hypothetical_balance = real_balance + virtual_add
        hypothetical_equity = real_equity + virtual_add  # simple model: add same to equity

        # Summary printout
        print("=== MT5 Account Summary (READ-ONLY) ===")
        print(f"Login: {account['login']} | Account name: {account['name']} | Server: {account['server']}")
        print(f"Currency: {account['currency']}")
        print(f"Real Balance: {real_balance:.2f}")
        print(f"Real Equity:  {real_equity:.2f}")
        print(f"Realized Profit in range {from_dt.date()} -> {to_dt.date()}: {realized_profit:.2f}")
        print("--- Hypothetical scenario (LOCAL CALCULATION ONLY) ---")
        print(f"Virtual add/subtract: {virtual_add:.2f}")
        print(f"Hypothetical Balance: {hypothetical_balance:.2f}")
        print(f"Hypothetical Equity:  {hypothetical_equity:.2f}")
        print("========================================")

        # Optional CSV export: combine deals + positions and add hypothetical columns
        if args.csv:
            # Normalize deals_df and positions_df to a single table if possible
            combined = None
            if not deals_df.empty:
                df = deals_df.copy()
                # convert mt5 time fields (if present) to datetime
                for col in ['time', 'time_msc', 'time_done', 'time_setup', 'time_expr']:
                    if col in df.columns:
                        try:
                            df[col] = pd.to_datetime(df[col], unit='s', errors='ignore')
                        except Exception:
                            pass
                combined = df
            elif not positions_df.empty:
                df = positions_df.copy()
                for col in ['time', 'time_msc', 'time_done', 'time_setup', 'time_expiration']:
                    if col in df.columns:
                        try:
                            df[col] = pd.to_datetime(df[col], unit='s', errors='ignore')
                        except Exception:
                            pass
                combined = df

            if combined is None:
                # nothing to export: create a minimal summary
                summary = pd.DataFrame([{
                    "login": account['login'],
                    "balance": real_balance,
                    "equity": real_equity,
                    "realized_profit": realized_profit,
                    "virtual_add": virtual_add,
                    "hypothetical_balance": hypothetical_balance,
                    "hypothetical_equity": hypothetical_equity,
                    "from": from_dt,
                    "to": to_dt
                }])
                summary.to_csv(args.csv, index=False)
                print(f"Exported summary to {args.csv}")
            else:
                # Add hypothetical columns to each row (same global hypothetical)
                combined = combined.reset_index(drop=True)
                combined['account_login'] = account['login']
                combined['account_balance_real'] = real_balance
                combined['account_equity_real'] = real_equity
                combined['realized_profit_range'] = realized_profit
                combined['virtual_add'] = virtual_add
                combined['hypothetical_balance'] = hypothetical_balance
                combined['hypothetical_equity'] = hypothetical_equity
                combined.to_csv(args.csv, index=False)
                print(f"Exported combined history + hypothetical columns to {args.csv}")

    finally:
        shutdown_mt5()

if __name__ == "__main__":
    main()
