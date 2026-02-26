import asyncio
import os
import sys
from pathlib import Path

# Load .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.db.cosmos import get_extractions_container
from app.core.config import settings

async def check_recent_errors():
    container = get_extractions_container()
    if not container:
        print("Cosmos DB not connected.")
        return

    query = """
    SELECT c.id, c.filename, c.status, c.error, c.created_at, c.user_id 
    FROM c 
    WHERE c.type = 'extraction_job'
    ORDER BY c.created_at DESC
    """
    
    try:
        items = list(container.query_items(
            query=query,
            enable_cross_partition_query=True,
            max_item_count=5
        ))
        
        if not items:
            print("No recent errors found.")
            return
            
        print("=== RECENT FAILED JOBS ===")
        for item in items[:3]:
            print(f"Time: {item.get('created_at')}")
            print(f"File: {item.get('filename')}")
            print(f"Status: {item.get('status')}")
            print(f"Error: {item.get('error')}")
            print(f"User: {item.get('user_id')}")
            print("-" * 40)
            
    except Exception as e:
        print(f"Failed to query Cosmos DB: {e}")

if __name__ == "__main__":
    asyncio.run(check_recent_errors())
