import asyncio
import json
import os

from app.core.config import settings
from azure.cosmos.aio import CosmosClient

async def get_latest_job():
    from app.db.cosmos import get_extractions_container
    container = get_extractions_container()
    
    query = """
    SELECT TOP 5 c.id, c.model_id, c.status, c.preview_data, c.error, c.created_at, c.filename 
    FROM c 
    ORDER BY c.created_at DESC
    """
    
    items = list(container.query_items(
        query=query,
        enable_cross_partition_query=True
    ))
    
    jobs = items
    
    if jobs:
        from app.services.hydration import hydrate_preview_data
        for i, job in enumerate(jobs):
            if job.get("preview_data"):
                hydrated = await hydrate_preview_data(job.get("preview_data"))
                job["preview_data"] = hydrated
        
        with open("latest_job_debug.json", "w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
            
        print(f"Saved {len(jobs)} jobs to latest_job_debug.json")
    else:
        print("No jobs found")

if __name__ == "__main__":
    asyncio.run(get_latest_job())
