"""
Migration script: Convert existing confirmed Jobs to Logs
Run once to fix existing data after architecture change.
"""
import asyncio
from app.db.cosmos import get_extractions_container
from datetime import datetime

def migrate_jobs_to_logs():
    container = get_extractions_container()
    if not container:
        print("ERROR: Could not connect to Cosmos DB")
        return
    
    # 1. Find all confirmed Jobs
    jobs = list(container.query_items(
        "SELECT * FROM c WHERE c.type = 'extraction_job' AND c.status = 'confirmed'",
        enable_cross_partition_query=True
    ))
    
    print(f"Found {len(jobs)} confirmed Jobs to migrate")
    
    migrated = 0
    for job in jobs:
        job_id = job['id']
        original_log_id = job.get('original_log_id')
        
        if original_log_id:
            # Job was a retry - update existing Log
            try:
                existing_log = container.read_item(original_log_id, partition_key=job['model_id'])
                existing_log['status'] = 'success'
                existing_log['extracted_data'] = job.get('extracted_data') or job.get('preview_data', {}).get('guide_extracted', {})
                existing_log['updated_at'] = datetime.utcnow().isoformat()
                container.upsert_item(existing_log)
                print(f"  Updated Log {original_log_id} from Job {job_id[:8]}...")
                migrated += 1
            except Exception as e:
                print(f"  WARNING: Could not update Log {original_log_id}: {e}")
        else:
            # Job was new extraction - create Log from Job
            log_data = {
                "id": job_id,  # Use same ID
                "type": "extraction_log",
                "model_id": job['model_id'],
                "user_id": job['user_id'],
                "user_name": job.get('user_name'),
                "user_email": job.get('user_email'),
                "filename": job['filename'],
                "file_url": job.get('file_url'),
                "status": "success",
                "extracted_data": job.get('extracted_data') or job.get('preview_data', {}).get('guide_extracted', {}),
                "created_at": job['created_at'],
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Check if Log with same ID exists
            try:
                existing = container.read_item(job_id, partition_key=job['model_id'])
                if existing.get('type') != 'extraction_log':
                    # It's a Job, convert it
                    container.upsert_item(log_data)
                    print(f"  Converted Job {job_id[:8]}... to Log")
                    migrated += 1
            except:
                # Log doesn't exist, create it
                container.upsert_item(log_data)
                print(f"  Created Log from Job {job_id[:8]}...")
                migrated += 1
    
    print(f"\nMigration complete: {migrated} Jobs migrated to Logs")

if __name__ == "__main__":
    migrate_jobs_to_logs()
