import subprocess
import os

ahk_exe = r"C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe"   # correct exe
ahk_script = r"C:\Users\hp\OneDrive\Desktop\PlaceOrder.ahk"

subprocess.Popen([ahk_exe, ahk_script])


print("Checking if file exists...")

if os.path.exists(ahk_script):
    print(f"File found: {ahk_script}")
    print("Trying to run the AHK script...")

    try:
        subprocess.Popen([ahk_exe, ahk_script])
        print("✅ Script launched successfully!")
    except Exception as e:
        print("❌ Failed to run script:", e)
else:
    print(f"❌ File not found at: {ahk_script}")
