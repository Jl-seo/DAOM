
import asyncio
import os
import sys
from pathlib import Path
import json

# Add backend to path
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend"))

from app.db.cosmos import get_jobs_container, get_extractions_container
from app.services.storage import load_json_from_blob
from azure.cosmos import PartitionKey

JOB_ID = "fca90308-66b0-42ab-b4f0-dc8fb02ed9a4"

async def inspect():
    print(f"--- INSPECTING JOB {JOB_ID} ---")
    
    # 1. Check Jobs Container
    jobs_container = get_jobs_container()
    if not jobs_container:
        print("[ERROR] No Jobs Container context")
        return

    print("Querying Jobs container...")
    try:
        # Query by ID (cross-partition)
        query = "SELECT * FROM c WHERE c.id = @id"
        items = list(jobs_container.query_items(
            query=query,
            parameters=[{"name": "@id", "value": JOB_ID}],
            enable_cross_partition_query=True
        ))
        
        if not items:
            print(f"[FAIL] Job {JOB_ID} NOT FOUND in Cosmos DB 'jobs' container.")
        else:
            job = items[0]
            print(f"[SUCCESS] Job Found!")
            print(f"Status: {job.get('status')}")
            print(f"Debug Data Present: {'YES' if job.get('debug_data') else 'NO'}")
            if job.get('debug_data'):
                print(json.dumps(job.get('debug_data'), indent=2))
                
                # Check Blob if referenced
                blob_path = job.get('debug_data', {}).get('raw_data_blob_path')
                if blob_path:
                    print(f"Checking Blob Path: {blob_path}")
                    blob_data = await load_json_from_blob(blob_path)
                    print(f"Blob Load Result: {'SUCCESS' if blob_data else 'FAIL'}")
    except Exception as e:
        print(f"[ERROR] Job Query Failed: {e}")

    # 2. Check Logs Container
    print("\nQuerying Logs container...")
    logs_container = get_extractions_container()
    try:
         query = "SELECT * FROM c WHERE c.job_id = @id"
         items = list(logs_container.query_items(
             query=query,
             parameters=[{"name": "@id", "value": JOB_ID}],
             enable_cross_partition_query=True
         ))
         
         if not items:
             print("[INFO] No associated Logs found.")
         else:
             print(f"[INFO] Found {len(items)} associated logs.")
             for item in items:
                 print(f" - Log {item['id']} | Status: {item.get('status')} | DebugData: {'YES' if item.get('debug_data') else 'NO'}")
                 
    except Exception as e:
        print(f"[ERROR] Log Query Failed: {e}")

if __name__ == "__main__":
    asyncio.run(inspect())
