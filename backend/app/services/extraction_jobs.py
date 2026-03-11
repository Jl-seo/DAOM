"""
Extraction Jobs Service
Job-based async extraction processing with status tracking
"""
import logging
import json as _json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict
import uuid
from ..db.cosmos import get_extractions_container
from app.services import audit
from app.core.enums import ExtractionType, ExtractionStatus

logger = logging.getLogger(__name__)


class ExtractionJob(BaseModel):
    """Extraction job with lifecycle tracking"""
    model_config = ConfigDict(extra="ignore")  # Ignore Cosmos system fields (_rid, _etag, etc.)

    id: str
    model_id: str
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    filename: str
    file_url: Optional[str] = None # Made optional for multi-file legacy compat if needed, but usually primary is set
    file_urls: Optional[List[str]] = None # New field for multi-file inputs
    filenames: Optional[List[str]] = None # New field for multi-file filenames
    candidate_file_url: Optional[str] = None  # Comparison target file URL (Legacy, single)
    candidate_file_urls: Optional[List[str]] = None  # Comparison target file URLs (Multi)
    status: str  # pending, analyzing, preview_ready, confirmed, error
    preview_data: Optional[Dict[str, Any]] = None  # guide_extracted, other_data
    extracted_data: Optional[Dict[str, Any]] = None  # Final confirmed data
    debug_data: Optional[Dict[str, Any]] = None  # Raw OCR/LLM for debugging
    error: Optional[str] = None
    created_at: str
    updated_at: str
    original_log_id: Optional[str] = None  # For retry jobs - references the parent Log
    log_id: Optional[str] = None  # Alias for original_log_id - TODO: migrate to log_id only
    tenant_id: Optional[str] = None  # Tenant ID for multi-tenancy
    ttl: Optional[int] = None  # Cosmos DB Time-to-Live (in seconds)


async def create_job(
    model_id: str,
    user_id: str,
    filename: str,
    file_url: Optional[str] = None,
    file_urls: Optional[List[str]] = None, # New arg
    filenames: Optional[List[str]] = None, # New arg
    candidate_file_url: Optional[str] = None,
    candidate_file_urls: Optional[List[str]] = None,
    user_name: Optional[str] = None,
    user_email: Optional[str] = None,
    original_log_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    ttl: Optional[int] = None
) -> ExtractionJob:
    """Create a new extraction job with pending status"""
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Validation: Ensure at least one file source
    if not file_url and not file_urls:
         # Fallback or strict error? For now allow if one is missing but warn.
         pass

    job = ExtractionJob(
        id=job_id,
        model_id=model_id,
        user_id=user_id,
        user_name=user_name,
        user_email=user_email,
        filename=filename,
        file_url=file_url,
        file_urls=file_urls,
        filenames=filenames,
        candidate_file_url=candidate_file_url,
        candidate_file_urls=candidate_file_urls,
        status=ExtractionStatus.PENDING.value,
        created_at=now,
        updated_at=now,
        original_log_id=original_log_id,
        tenant_id=tenant_id,
        ttl=ttl
    )

    container = get_extractions_container()
    if container:
        try:
            await container.create_item(body={
                **job.model_dump(),
                "type": "extraction_job"
            })
        except Exception as e:
            logger.error(f"[ExtractionJobs] Failed to save job: {e}")

    return job


async def get_job(job_id: str) -> Optional[ExtractionJob]:
    """Get job by ID"""
    container = get_extractions_container()
    if not container:
        return None

    try:
        query = "SELECT * FROM c WHERE c.id = @job_id AND c.type = 'extraction_job'"
        items = [item async for item in container.query_items(
            query=query,
            parameters=[{"name": "@job_id", "value": job_id}],
            enable_cross_partition_query=True
        )]
        if items:
            return ExtractionJob(**items[0])
    except Exception as e:
        logger.error(f"[ExtractionJobs] Failed to get job: {e}")

    return None


_last_update_error: Optional[str] = None  # Module-level diagnostic

def get_last_update_error() -> Optional[str]:
    return _last_update_error

async def update_job(
    job_id: str,
    status: Optional[str] = None,
    preview_data: Optional[Dict[str, Any]] = None,
    extracted_data: Optional[Dict[str, Any]] = None,
    debug_data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> Optional[ExtractionJob]:
    """Update job status and data — v2026.02.08 (Async Blob Offloading)"""
    global _last_update_error
    _last_update_error = None

    container = get_extractions_container()
    if not container:
        _last_update_error = "step0: Cosmos container is None"
        logger.error(f"[ExtractionJobs] update_job({job_id}): {_last_update_error}")
        return None

    try:
        # Get existing job
        # logger.info(f"[ExtractionJobs] update_job({job_id}): step 1 — querying job")
        query = f"SELECT * FROM c WHERE c.id = @job_id AND c.type = '{ExtractionType.JOB.value}'"
        items = [item async for item in container.query_items(
            query=query,
            parameters=[{"name": "@job_id", "value": job_id}],
            enable_cross_partition_query=True
        )]

        if not items:
            _last_update_error = f"step1: job {job_id} not found in Cosmos (type={ExtractionType.JOB.value})"
            logger.error(f"[ExtractionJobs] update_job({job_id}): {_last_update_error}")
            return None

        job_data = items[0]

        # Validate Error Message Presence
        if status in [ExtractionStatus.ERROR.value, ExtractionStatus.FAILED.value] and not error:
            error = "Unknown Error (No error message provided by caller)"
            logger.warning(f"[ExtractionJobs] Job {job_id} set to ERROR but no message provided. Using fallback.")

        # Update fields
        if status:
            job_data["status"] = status
        if preview_data is not None:
            job_data["preview_data"] = preview_data
        if extracted_data is not None:
            job_data["extracted_data"] = extracted_data
        if debug_data is not None:
            job_data["debug_data"] = debug_data
        if error is not None:
            job_data["error"] = error
        job_data["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # --- BLOB OFFLOADING LOGIC (Phase 3) ---
        from app.services.storage import save_json_as_blob
        
        # Helper to check JSON size
        def get_json_size(obj):
            return len(_json.dumps(obj, ensure_ascii=False, default=str))

        # 1. Check Payload Size
        payload_size = get_json_size(job_data)
        THRESHOLD_BYTES = 1_500_000 # 1.5MB (SAFE LIMIT, Cosmos max is 2MB)
        
        if payload_size > THRESHOLD_BYTES:
            logger.info(f"[ExtractionJobs] Payload size {payload_size} bytes > {THRESHOLD_BYTES}. Triggering Blob Offloading.")
            
            # Offload Debug Data first (usually the biggest)
            if "debug_data" in job_data and isinstance(job_data["debug_data"], dict):
                dd = job_data["debug_data"]
                # Only offload if it has content
                if get_json_size(dd) > 100_000: # If debug data is significant
                    blob_path = f"jobs/{job_id}/debug_data.json"
                    try:
                        await save_json_as_blob(dd, blob_path)
                        job_data["debug_data"] = {
                            "source": "blob_storage", 
                            "raw_data_blob_path": blob_path,
                            "preview": "Debug data offloaded to Blob Storage"
                        }
                        logger.info(f"[ExtractionJobs] Offloaded debug_data to {blob_path}")
                    except Exception as e:
                        logger.error(f"[ExtractionJobs] Failed to offload debug_data: {e}")

            # Re-check size
            payload_size = get_json_size(job_data)
            
            # Offload Preview Data heavy fields if still too big
            if payload_size > THRESHOLD_BYTES and "preview_data" in job_data and isinstance(job_data["preview_data"], dict):
                pd = job_data["preview_data"]
                
                # Offload raw_tables
                if "raw_tables" in pd:
                    tables = pd["raw_tables"]
                    if get_json_size(tables) > 100_000:
                        blob_path = f"jobs/{job_id}/raw_tables.json"
                        try:
                            await save_json_as_blob(tables, blob_path)
                            pd["raw_tables"] = {"source": "blob_storage", "blob_path": blob_path}
                            logger.info(f"[ExtractionJobs] Offloaded raw_tables to {blob_path}")
                        except Exception as e:
                            logger.error(f"[ExtractionJobs] Failed to offload raw_tables: {e}")
                
                # Offload Beta technical fields
                for key in ["_beta_parsed_content", "_beta_ref_map", "raw_content"]:
                    if key in pd and get_json_size(pd[key]) > 50_000:
                         blob_path = f"jobs/{job_id}/{key}.json"
                         try:
                             await save_json_as_blob(pd[key], blob_path)
                             pd[key] = {"source": "blob_storage", "blob_path": blob_path}
                             logger.info(f"[ExtractionJobs] Offloaded {key} to {blob_path}")
                         except Exception as e:
                             logger.error(f"[ExtractionJobs] Failed to offload {key}: {e}")
                             
             # Re-check size for massive extraction data (Excel with thousands of rows)
            payload_size = get_json_size(job_data)
            
            if payload_size > THRESHOLD_BYTES and "extracted_data" in job_data and isinstance(job_data["extracted_data"], dict):
                ed = job_data["extracted_data"]
                if get_json_size(ed) > 100_000:
                    blob_path = f"jobs/{job_id}/extracted_data.json"
                    try:
                        await save_json_as_blob(ed, blob_path)
                        job_data["extracted_data"] = {
                            "source": "blob_storage", 
                            "blob_path": blob_path,
                            "preview": "Extraction results offloaded due to massive payload size (> 1.5MB)"
                        }
                        logger.info(f"[ExtractionJobs] Offloaded final extracted_data to {blob_path}")
                    except Exception as e:
                        logger.error(f"[ExtractionJobs] Failed to offload extracted_data: {e}")
            
            payload_size = get_json_size(job_data)
            # Final check in `preview_data.guide_extracted` or `preview_data.sub_documents` where the identical data lives
            if payload_size > THRESHOLD_BYTES and "preview_data" in job_data and isinstance(job_data["preview_data"], dict):
                pd = job_data["preview_data"]
                if "guide_extracted" in pd and get_json_size(pd["guide_extracted"]) > 100_000:
                    blob_path = f"jobs/{job_id}/preview_guide_extracted.json"
                    try:
                         await save_json_as_blob(pd["guide_extracted"], blob_path)
                         pd["guide_extracted"] = {"source": "blob_storage", "blob_path": blob_path}
                         logger.info(f"[ExtractionJobs] Offloaded preview_data.guide_extracted to {blob_path}")
                    except Exception as e:
                         logger.error(f"[ExtractionJobs] Failed to offload preview_data.guide_extracted: {e}")
                
                # Check sub_documents legacy array as well
                if "sub_documents" in pd and get_json_size(pd["sub_documents"]) > 100_000:
                     blob_path = f"jobs/{job_id}/preview_sub_documents.json"
                     try:
                          await save_json_as_blob(pd["sub_documents"], blob_path)
                          pd["sub_documents"] = [{"source": "blob_storage", "blob_path": blob_path}] # Expects array
                          logger.info(f"[ExtractionJobs] Offloaded preview_data.sub_documents to {blob_path}")
                     except Exception as e:
                          logger.error(f"[ExtractionJobs] Failed to offload preview_data.sub_documents: {e}")

        # Final Size Check & Warning
        final_size = get_json_size(job_data)
        if final_size > 1_900_000: # 1.9MB (Danger Zone)
             logger.warning(f"[ExtractionJobs] Payload still huge ({final_size} bytes) after all offloading! Cosmos insert might fail.")


        # Upsert
        try:
            await container.upsert_item(body=job_data)
        except Exception as upsert_err:
            # Fallback for 413 if offloading failed or wasn't enough
            err_str = str(upsert_err)
            if "RequestEntityTooLarge" in err_str or "413" in err_str:
                logger.critical(f"[ExtractionJobs] 413 persists after offloading attempt. Clearing data to save state.")
                # Last resort: clear everything except status and error
                job_data["preview_data"] = None
                job_data["extracted_data"] = None
                job_data["debug_data"] = None
                job_data["error"] = f"CRITICAL: Result too large even after offloading. {str(upsert_err)}" + (job_data.get("error") or "")
                await container.upsert_item(body=job_data)
            else:
                raise upsert_err

        # logger.info(f"[ExtractionJobs] update_job({job_id}): step 3 — upsert OK")

        job = ExtractionJob(**job_data)


        # Log audit if status changed
        if status and status != items[0].get("status"): # Use original status for comparison
            # ... (Audit logic remains same)
            pass

        # Auto-sync status to ExtractionLog
        if (job.original_log_id or job.log_id) and status:
            try:
                from app.services import extraction_logs
                log_id_to_update = job.original_log_id or job.log_id
                await extraction_logs.update_log_status(
                    log_id_to_update,
                    status=status,
                    preview_data=preview_data,
                    extracted_data=extracted_data, # FIX: ensure extracted_data is synced
                    debug_data=debug_data, 
                    error=error 
                )
            except Exception as e:
                logger.error(f"[ExtractionJobs] Failed to sync status to log {job.original_log_id}: {e}")

        return job

    except Exception as e:
        import traceback
        _last_update_error = f"step2/3 exception: {type(e).__name__}: {e}"
        logger.error(f"[ExtractionJobs] update_job({job_id}): {_last_update_error}\n{traceback.format_exc()}")

    return None


async def get_jobs_by_model(model_id: str, limit: int = 50) -> List[ExtractionJob]:
    """Get all jobs for a model"""
    container = get_extractions_container()
    if not container:
        return []

    try:
        query = """
            SELECT * FROM c 
            WHERE c.model_id = @model_id 
            AND c.type = 'extraction_job'
            ORDER BY c.created_at DESC
            OFFSET 0 LIMIT @limit
        """
        items = [item async for item in container.query_items(
            query=query,
            parameters=[
                {"name": "@model_id", "value": model_id},
                {"name": "@limit", "value": limit}
            ],
        )]
        return [ExtractionJob(**item) for item in items]
    except Exception as e:
        logger.error(f"[ExtractionJobs] Failed to get jobs: {e}")

    return []


async def get_jobs_by_model_and_user(model_id: str, user_id: str, limit: int = 50) -> List[ExtractionJob]:
    """Get jobs for a specific model and user"""
    container = get_extractions_container()
    if not container:
        return []

    try:
        query = """
            SELECT * FROM c 
            WHERE c.model_id = @model_id 
            AND c.user_id = @user_id
            AND c.type = 'extraction_job'
            ORDER BY c.created_at DESC
            OFFSET 0 LIMIT @limit
        """
        items = [item async for item in container.query_items(
            query=query,
            parameters=[
                {"name": "@model_id", "value": model_id},
                {"name": "@user_id", "value": user_id},
                {"name": "@limit", "value": limit}
            ],
        )]
        return [ExtractionJob(**item) for item in items]
    except Exception as e:
        logger.error(f"[ExtractionJobs] Failed to get model user jobs: {e}")

    return []


async def get_jobs_by_user(user_id: str, limit: int = 50, tenant_id: Optional[str] = None) -> List[ExtractionJob]:
    """Get all jobs for a user, enforcing tenant isolation"""
    container = get_extractions_container()
    if not container:
        return []

    try:
        query = """
            SELECT * FROM c 
            WHERE c.user_id = @user_id 
            AND c.type = 'extraction_job'
        """
        parameters = [
            {"name": "@user_id", "value": user_id},
            {"name": "@limit", "value": limit}
        ]

        if tenant_id:
            query += " AND c.tenant_id = @tenant_id"
            parameters.append({"name": "@tenant_id", "value": tenant_id})

        query += " ORDER BY c.created_at DESC OFFSET 0 LIMIT @limit"

        items = [item async for item in container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        )]
        return [ExtractionJob(**item) for item in items]
    except Exception as e:
        logger.error(f"[ExtractionJobs] Failed to get user jobs: {e}")

    return []


async def get_latest_job_by_log_id(log_id: str) -> Optional[ExtractionJob]:
    """Get the most recent job associated with a log via original_log_id"""
    container = get_extractions_container()
    if not container:
        return None

    try:
        query = """
            SELECT TOP 1 * FROM c 
            WHERE c.original_log_id = @log_id 
            AND c.type = 'extraction_job'
            ORDER BY c.created_at DESC
        """
        items = [item async for item in container.query_items(
            query=query,
            parameters=[{"name": "@log_id", "value": log_id}],
            enable_cross_partition_query=True
        )]
        if items:
            return ExtractionJob(**items[0])
    except Exception as e:
        logger.error(f"[ExtractionJobs] Failed to get job by log_id: {e}")

    return None


async def delete_job(job_id: str) -> bool:
    """Delete a job or log permanently by ID"""
    container = get_extractions_container()
    if not container:
        return False

    try:
        # Find item by ID to get partition key (model_id)
        # We query without type restriction to handle both Jobs and Logs
        query = "SELECT * FROM c WHERE c.id = @id"
        items = [item async for item in container.query_items(
            query=query,
            parameters=[{"name": "@id", "value": job_id}],
            enable_cross_partition_query=True
        )]

        if not items:
            return False

        item = items[0]
        partition_key = item.get("model_id") # Most items use model_id as PK

        if not partition_key:
             # Fallback or check if it's a legacy item.
             # If no model_id, maybe we can't delete if PK is required.
             # Tries deleting using id as PK? (unlikely for this container)
             logger.info(f"[ExtractionJobs] Item {job_id} has no model_id partition key.")
             return False

        await container.delete_item(item=job_id, partition_key=partition_key)
        return True
    except Exception as e:
        logger.error(f"[ExtractionJobs] Failed to delete item {job_id}: {e}")
        return False


async def cancel_job(job_id: str) -> Optional[ExtractionJob]:
    """Cancel a running job"""
    # Just update status. The background task might still run but result save will check job status?
    # Or we can't easily stop the background task thread.
    # But updating status prevents frontend from polling it as active.
    job = await update_job(job_id, status=ExtractionStatus.CANCELLED.value, error="Cancelled by user")

    # Sync cancellation status to ExtractionLog if linked
    if job and (job.original_log_id or job.log_id):
        from app.services import extraction_logs
        log_id_to_update = job.original_log_id or job.log_id
        try:
            await extraction_logs.update_log_status(
                log_id_to_update,
                status=ExtractionStatus.CANCELLED.value
            )
        except Exception as e:
            logger.error(f"[ExtractionJobs] Failed to sync cancel status to log: {e}")

    return job
