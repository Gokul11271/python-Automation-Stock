import subprocess

# Full file paths
script1 = r"c:/Users/hp/OneDrive/Desktop/python script/manual seprate script/November Buy 2 and 4 gap -1.py"
script2 = r"c:/Users/hp/OneDrive/Desktop/python script/manual seprate script/November Sell buy 2 and 4 gap -1.py"

print("🚀 Starting both scripts...")

# Run both scripts simultaneously
subprocess.Popen(["python", script1])
subprocess.Popen(["python", script2])

print("✅ Both scripts launched successfully!")
