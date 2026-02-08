
import sys
import os
import asyncio

# Add backend to path
sys.path.append(os.getcwd())

async def verify_imports():
    print("Verifying imports...")
    try:
        print("1. Importing settings...")
        from app.core.config import settings
        
        print("2. Importing extraction_service...")
        from app.services.extraction_service import extraction_service
        print("   -> Success")

        print("3. Importing extraction_preview endpoint...")
        from app.api.endpoints import extraction_preview
        print("   -> Success")

        print("4. Importing jobs endpoint...")
        from app.api.endpoints.extraction import jobs
        print("   -> Success")

        print("5. Importing power_automate endpoint...")
        from app.api.endpoints import power_automate
        print("   -> Success")
        
        print("ALL IMPORTS PASSED")
    except Exception as e:
        print(f"IMPORT FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify_imports())
