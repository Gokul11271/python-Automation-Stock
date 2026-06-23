import MetaTrader5 as mt5
import time
import pygame

# =========================
# SETTINGS
# =========================

PROFIT_TARGET = 1    # Close all trades at +$5
LOSS_LIMIT = -200      # Close all trades at -$20

CHECK_INTERVAL = 2     # seconds

# =========================
# SOUND INIT
# =========================

pygame.init()

pygame.mixer.init()

print("✅ Pygame Mixer Initialized")

try:

    # LOAD CLOSE SOUND
    close_sound = pygame.mixer.Sound("closewave.mp3")

    close_sound.set_volume(1.0)

    # SEPARATE CHANNEL
    close_channel = pygame.mixer.Channel(1)

    print("✅ Close Sound Loaded Successfully")

except Exception as e:

    print("❌ Failed To Load Close Sound")
    print(e)

    close_sound = None

# =========================
# PLAY CLOSE SOUND
# =========================

def play_close_sound():

    try:

        if close_sound:

            close_channel.play(close_sound)

            print("🔊 CLOSE SOUND PLAYED")

    except Exception as e:

        print("❌ Sound Play Error:", e)

# =========================
# CONNECT TO MT5
# =========================

if not mt5.initialize():

    print("❌ MT5 initialization failed")

    quit()

print("✅ Connected to MT5")

# =========================
# CLOSE POSITION FUNCTION
# =========================

def close_position(position):

    symbol = position.symbol
    volume = position.volume
    ticket = position.ticket

    print(f"\n🔄 Attempting to close position {ticket}")

    # Get latest tick
    tick = mt5.symbol_info_tick(symbol)

    if tick is None:

        print(f"❌ Tick data missing for {symbol}")

        return

    # Symbol info
    info = mt5.symbol_info(symbol)

    if info is None:

        print(f"❌ Symbol info missing for {symbol}")

        return

    print(f"📌 Broker Filling Mode: {info.filling_mode}")

    # Determine opposite order
    if position.type == mt5.POSITION_TYPE_BUY:

        order_type = mt5.ORDER_TYPE_SELL

        price = tick.bid

    else:

        order_type = mt5.ORDER_TYPE_BUY

        price = tick.ask

    # Try all possible filling modes
    filling_modes = [
        mt5.ORDER_FILLING_FOK,
        mt5.ORDER_FILLING_IOC,
        mt5.ORDER_FILLING_RETURN
    ]

    # Try different deviations too
    deviations = [20, 50, 100]

    for filling in filling_modes:

        for deviation in deviations:

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "position": ticket,
                "price": price,
                "deviation": deviation,
                "magic": 1000,
                "comment": "Auto Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            print(
                f"Trying filling={filling} | "
                f"deviation={deviation}"
            )

            result = mt5.order_send(request)

            if result is None:

                print("❌ order_send returned None")

                continue

            # SUCCESS
            if result.retcode == mt5.TRADE_RETCODE_DONE:

                print(f"✅ Successfully closed position {ticket}")

                return

            else:

                print(
                    f"❌ Failed | "
                    f"Retcode={result.retcode} | "
                    f"Comment={result.comment}"
                )

    # LAST ATTEMPT WITHOUT PRICE
    print("⚠ Trying final fallback without price...")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "position": ticket,
        "deviation": 100,
        "magic": 1000,
        "comment": "Auto Close Final",
        "type_time": mt5.ORDER_TIME_GTC,
    }

    result = mt5.order_send(request)

    if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:

        print(f"✅ Closed using fallback method {ticket}")

    else:

        print(f"❌ FINAL FAILED for {ticket}")

# =========================
# MAIN LOOP
# =========================

while True:

    positions = mt5.positions_get()

    if positions is None:

        print("❌ Could not fetch positions")

        time.sleep(CHECK_INTERVAL)

        continue

    if len(positions) == 0:

        print("✅ No open positions")

        break

    total_profit = sum(pos.profit for pos in positions)

    print(f"\n💰 Current Profit/Loss: {total_profit:.2f}")

    # =========================
    # PROFIT TARGET HIT
    # =========================

    if total_profit >= PROFIT_TARGET:

        print("\n🎯 Profit target reached. Closing all positions...")

        # PLAY CLOSE SOUND
        play_close_sound()

        # SMALL DELAY TO HEAR SOUND
        time.sleep(1)

        for pos in positions:

            close_position(pos)

        break

    # =========================
    # LOSS LIMIT HIT
    # =========================

    elif total_profit <= LOSS_LIMIT:

        print("\n🛑 Loss limit reached. Closing all positions...")

        # PLAY CLOSE SOUND
        play_close_sound()

        # SMALL DELAY TO HEAR SOUND
        time.sleep(1)

        for pos in positions:

            close_position(pos)

        break

    time.sleep(CHECK_INTERVAL)

# =========================
# WAIT FOR SOUND TO FINISH
# =========================

if close_sound:

    while close_channel.get_busy():

        time.sleep(0.1)

# =========================
# SHUTDOWN
# =========================

mt5.shutdown()

pygame.quit()

print("\n🔌 MT5 disconnected")