
import asyncio
import os
import sys

# Add current directory to path so we can import app modules
sys.path.append(os.getcwd())

from app.db.cosmos import init_cosmos
from app.services import extraction_logs
from app.core.config import settings

async def main():
    print("Initializing Cosmos DB...")
    init_cosmos()
    
    print("Fetching last 10 logs...")
    try:
        logs = extraction_logs.get_all_logs(limit=10)
        print(f"Found {len(logs)} logs.")
        
        for log in logs:
            print(f"ID: {log.id}")
            print(f"Filename: {log.filename}")
            print(f"Status: '{log.status}'") # Quote to see spaces or empty
            print(f"Extracted Data Keys: {list(log.extracted_data.keys()) if log.extracted_data else 'None'}")
            print("-" * 30)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
