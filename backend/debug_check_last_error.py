
import asyncio
import os
import sys
from datetime import datetime

# Add current directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    # Script is in backend/debug_check_last_error.py
    # .env is in backend/.env
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    print(f"Loading .env from: {env_path}")
    load_dotenv(env_path)
    
    from app.core.config import settings
    from azure.cosmos import CosmosClient
except ImportError:
    print("❌ Error: Missing dependencies. Run 'pip install azure-cosmos python-dotenv'")
    sys.exit(1)

async def check_last_error():
    print(f"🔍 Connecting to Cosmos DB: {settings.COSMOS_ENDPOINT}")
    print(f"📂 Database: {settings.COSMOS_DATABASE}")
    
    try:
        client = CosmosClient(settings.COSMOS_ENDPOINT, credential=settings.COSMOS_KEY)
        database = client.get_database_client(settings.COSMOS_DATABASE)
        container = database.get_container_client("ExtractedData")
        
        # Query for SUCCESS job
        job_id = None # Let DB find any success job
        
        query = """
            SELECT TOP 1 c.id, c.type, c.status, c.preview_data, c.ocr_result, c.debug_data
            FROM c
            WHERE c.status = 'S100' OR c.status = 'P500' 
            AND (c.ocr_result != null OR c.debug_data != null)
            ORDER BY c._ts DESC
        """
        
        print(f"\n⏳ Querying for ANY successful/preview job with data...")
        items = list(container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        if not items:
            print("✅ No success/preview jobs found with data.")
        else:
            item = items[0]
            print(f"ID: {item['id']}")
            print(f"Status: {item.get('status')}")
            
            ocr = item.get("ocr_result")
            print(f"OCR: {type(ocr)} (Len: {len(str(ocr)) if ocr else 0})")
            if ocr:
                print(f"OCR Keys: {list(ocr.keys()) if isinstance(ocr, dict) else 'Not Dict'}")
            
            preview = item.get("preview_data")
            print(f"Preview: {type(preview)} (Len: {len(str(preview)) if preview else 0})")
            
            debug = item.get("debug_data")
            print(f"Debug: {type(debug)} (Len: {len(str(debug)) if debug else 0})")
            if debug:
                print(f"Debug Keys: {list(debug.keys()) if isinstance(debug, dict) else 'Not Dict'}")
            
    except Exception as e:
        print(f"❌ Failed to query database: {e}")
                
    except Exception as e:
        print(f"❌ Failed to query database: {e}")

if __name__ == "__main__":
    asyncio.run(check_last_error())
