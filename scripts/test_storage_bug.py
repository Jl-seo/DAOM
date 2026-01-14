
import asyncio
import os
import shutil

# Mock settings
class MockSettings:
    AZURE_STORAGE_CONNECTION_STRING = None # Simulate Local Mode
    AZURE_CONTAINER_NAME = "test-container"

import sys
from unittest.mock import MagicMock
sys.modules["app.core.config"] = MagicMock()
sys.modules["app.core.config"].settings = MockSettings()

# Import the function to test (copy-paste for isolation or import if possible, but import is tricky with mocks)
# I will copy-paste the local fallback logic from storage.py for accurate reproduction
async def save_json_as_blob_mock(data: dict, filename: str):
    print(f"Attempting to save to {filename}...")
    try:
        base_dir = "temp_tests/cache"
        os.makedirs(base_dir, exist_ok=True)
        local_path = f"{base_dir}/{filename}"
        
        # LOGIC TO TEST:
        # storage.py logic:
        # os.makedirs("temp_uploads/cache", exist_ok=True)
        # local_path = f"temp_uploads/cache/{filename}"
        # with open(local_path, "w", _) ...
        
        with open(local_path, "w", encoding="utf-8") as f:
            f.write('{}')
        print("✅ Success!")
        return local_path
    except FileNotFoundError:
        print("❌ FileNotFoundError: Intermediate directories missing!")
    except Exception as e:
        print(f"❌ Error: {e}")

async def run():
    if os.path.exists("temp_tests"):
        shutil.rmtree("temp_tests")
        
    # Test flat path (Should work)
    await save_json_as_blob_mock({}, "flat.json")
    
    # Test nested path (Should fail if logic is flawed)
    await save_json_as_blob_mock({}, "nested/dir/test.json")
    
    # Clean up
    if os.path.exists("temp_tests"):
        shutil.rmtree("temp_tests")

if __name__ == "__main__":
    asyncio.run(run())
