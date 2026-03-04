import asyncio
import sys
import logging
import os

# Set up paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

# configure logging
logging.basicConfig(level=logging.INFO)

async def test_import():
    try:
        from app.services.extraction_service import extraction_service
        print("Import successful")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_import())
