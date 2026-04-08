# import winsound
# import time

# def play_custom_wav(
#     files=["profit.wav"],  # list of your .wav files
#     repeat=1,              # how many times to repeat
#     gap=0.2,               # gap between repeats (seconds)
#     label="🔊 Custom Sound"
# ):
#     """
#     Play custom WAV file(s) multiple times.

#     files: list of .wav file paths (relative or absolute)
#     repeat: number of times to repeat the sequence
#     gap: pause between repeats
#     label: printed message
#     """
#     print(f"{label} (×{repeat})")
#     for _ in range(repeat):
#         for file in files:
#             try:
#                 winsound.PlaySound(file, winsound.SND_FILENAME)
#             except RuntimeError:
#                 print(f"⚠️ Could not play sound: {file}")
#         time.sleep(gap)

import pygame
import time

def play_mp3_repeat(file_path, repeat=2, gap=0.1, label="🔊 Custom Sound"):
    
    print(f"{label} (×{repeat})")
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)

    for _ in range(repeat):
        pygame.mixer.music.play()
        # Wait until music finishes
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        time.sleep(gap)

# -------------------------
# Example usage
play_mp3_repeat(r"C:\Users\hp\Downloads\cash-register-purchase-87313.mp3", repeat=2, label="💰 Profit Sound")
