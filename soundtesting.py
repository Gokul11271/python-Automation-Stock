import pygame
import time

# =========================================================
# INIT
# =========================================================
pygame.init()

pygame.mixer.init()

print("✅ Pygame Mixer Initialized")

# =========================================================
# LOAD SOUNDS
# =========================================================
try:

    trade_sound = pygame.mixer.Sound("tradewave.mp3")

    close_sound = pygame.mixer.Sound("closewave.mp3")

    trade_sound.set_volume(1.0)

    close_sound.set_volume(1.0)

    print("✅ Sounds Loaded Successfully")

except Exception as e:

    print("❌ Failed To Load Sound")
    print(e)

    quit()

# =========================================================
# CREATE CHANNELS
# =========================================================
trade_channel = pygame.mixer.Channel(0)

close_channel = pygame.mixer.Channel(1)

print("✅ Channels Created")

# =========================================================
# TEST TRADE SOUND
# =========================================================
print("\n🔊 PLAYING TRADE SOUND")

trade_channel.play(trade_sound)

while trade_channel.get_busy():

    time.sleep(0.1)

print("✅ TRADE SOUND FINISHED")

# =========================================================
# WAIT
# =========================================================
time.sleep(1)

# =========================================================
# TEST CLOSE SOUND
# =========================================================
print("\n🔊 PLAYING CLOSE SOUND")

close_channel.play(close_sound)

while close_channel.get_busy():

    time.sleep(0.1)

print("✅ CLOSE SOUND FINISHED")

# =========================================================
# FINAL TEST
# =========================================================
print("\n🔊 PLAYING BOTH TOGETHER")

trade_channel.play(trade_sound)

time.sleep(0.5)

close_channel.play(close_sound)

while trade_channel.get_busy() or close_channel.get_busy():

    time.sleep(0.1)

print("✅ BOTH SOUNDS FINISHED")

# =========================================================
# CLEANUP
# =========================================================
pygame.quit()

print("\n🎉 SOUND TEST COMPLETED")