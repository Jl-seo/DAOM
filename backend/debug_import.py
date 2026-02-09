import sys
import os
import traceback

# Add current directory to path
sys.path.append(os.getcwd())

print("Attempting to import app.main...")
try:
    import app.main
    print("Successfully imported app.main!")
except Exception:
    traceback.print_exc()
