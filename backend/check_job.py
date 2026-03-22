import os
from azure.cosmos import CosmosClient
from app.core.config import settings
import json

client = CosmosClient(settings.AZURE_COSMOS_DB_ENDPOINT, settings.AZURE_COSMOS_DB_KEY)
db = client.get_database_client(settings.AZURE_COSMOS_DB_DATABASE)

def check_jobs():
    container = db.get_container_client("extraction_jobs")
    # Fetch latest Maersk job
    query = "SELECT TOP 1 * FROM c WHERE (c.model_name = 'OOCL_INV' OR c.model_name = '머스크' OR CONTAINS(c.model_name, 'Maersk')) ORDER BY c._ts DESC"
    items = list(container.query_items(query=query, enable_cross_partition_query=True))
    if not items:
        print("No jobs found")
        return
        
    job = items[0]
    print(f"JOB ID: {job['id']}")
    print(f"STATUS: {job.get('status')}")
    print(f"ERROR: {job.get('error')}")
    
    # Check what is inside preview_data
    has_preview = "preview_data" in job and job["preview_data"] is not None
    print(f"JOB HAS PREVIEW_DATA: {has_preview}")
    
    if has_preview:
        pd = job["preview_data"]
        print(f"Preview keys: {list(pd.keys())[:10]}")
        
    # Also check the Log
    print("\n--- CHECKING LOG ---")
    log_id = job.get("original_log_id") or job.get("log_id")
    if log_id:
        log_container = db.get_container_client("extraction_logs")
        try:
            log_item = log_container.read_item(item=log_id, partition_key=log_id)
            print(f"LOG STATUS: {log_item.get('status')}")
            print(f"LOG ERROR: {log_item.get('error')}")
            has_log_preview = "preview_data" in log_item and log_item["preview_data"] is not None
            print(f"LOG HAS PREVIEW_DATA: {has_log_preview}")
            if has_log_preview:
                lpd = log_item["preview_data"]
                print(f"Log preview keys: {list(lpd.keys())[:10]}")
                for k in ["guide_extracted", "raw_extracted", "raw_content", "_beta_parsed_content"]:
                    if k in lpd:
                        if isinstance(lpd[k], dict) and lpd[k].get("source") == "blob_storage":
                            print(f"  {k} -> BLOB: {lpd[k]['blob_path']}")
                        else:
                            sz = len(json.dumps(lpd[k]))
                            print(f"  {k} -> INLINE (Size: {sz} bytes)")
        except Exception as e:
            print(f"Failed to read log: {e}")

if __name__ == "__main__":
    check_jobs()
