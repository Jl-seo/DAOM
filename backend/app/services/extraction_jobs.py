"""
Extraction Jobs Service
Job-based async extraction processing with status tracking
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import uuid
from ..db.cosmos import get_extractions_container
from app.services import audit
from app.core.enums import ExtractionType, ExtractionStatus


class ExtractionJob(BaseModel):
    """Extraction job with lifecycle tracking"""
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


def create_job(
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
    tenant_id: Optional[str] = None
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
        tenant_id=tenant_id
    )
    
    container = get_extractions_container()
    if container:
        try:
            container.create_item(body={
                **job.model_dump(),
                "type": "extraction_job"
            })
        except Exception as e:
            logger.info(f"[ExtractionJobs] Failed to save job: {e}")
    
    return job


def get_job(job_id: str) -> Optional[ExtractionJob]:
    """Get job by ID"""
    container = get_extractions_container()
    if not container:
        return None
    
    try:
        query = "SELECT * FROM c WHERE c.id = @job_id AND c.type = 'extraction_job'"
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@job_id", "value": job_id}],
            enable_cross_partition_query=True
        ))
        if items:
            return ExtractionJob(**items[0])
    except Exception as e:
        logger.info(f"[ExtractionJobs] Failed to get job: {e}")
    
    return None


def update_job(
    job_id: str,
    status: Optional[str] = None,
    preview_data: Optional[Dict[str, Any]] = None,
    extracted_data: Optional[Dict[str, Any]] = None,
    debug_data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
) -> Optional[ExtractionJob]:
    """Update job status and data"""
    container = get_extractions_container()
    if not container:
        return None
    
    try:
        # Get existing job
        query = f"SELECT * FROM c WHERE c.id = @job_id AND c.type = '{ExtractionType.JOB.value}'"
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@job_id", "value": job_id}],
            enable_cross_partition_query=True
        ))
        
        if not items:
            return None
        
        job_data = items[0]
        
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
        
        # Upsert
        container.upsert_item(body=job_data)
        
        job = ExtractionJob(**job_data)
        
        
        # Log audit if status changed
        if status and status != job_data.get("status"):
            previous_status = job_data.get("status")
            
            # Extract token_usage from debug_data for audit
            token_usage = None
            if debug_data and isinstance(debug_data, dict):
                token_usage = debug_data.get("token_usage")
            
            audit.log_extraction_action(
                job, 
                "UPDATE_STATUS", 
                status="SUCCESS" if status != "error" else "FAILURE",
                changes={
                    "status": {
                        "old": previous_status, 
                        "new": status
                    }
                },
                details={"error": error} if error else None,
                token_usage=token_usage  # Pass token usage to audit
            )
            
        # Auto-sync status to ExtractionLog to ensure history consistency
        # This handles SUCCESS, ERROR, CANCELLED, etc. automatically
        if (job.original_log_id or job.log_id) and status:
            try:
                from app.services import extraction_logs
                log_id_to_update = job.original_log_id or job.log_id
                extraction_logs.update_log_status(
                    log_id_to_update, 
                    status=status,
                    preview_data=preview_data,
                    debug_data=debug_data # FIXED: Propagate debug_data
                )
            except Exception as e:
                logger.info(f"[ExtractionJobs] Failed to sync status to log {job.original_log_id}: {e}")
            
        return job
        
    except Exception as e:
        logger.info(f"[ExtractionJobs] Failed to update job: {e}")
    
    return None


def get_jobs_by_model(model_id: str, limit: int = 50) -> List[ExtractionJob]:
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
        items = list(container.query_items(
            query=query,
            parameters=[
                {"name": "@model_id", "value": model_id},
                {"name": "@limit", "value": limit}
            ],
            enable_cross_partition_query=True
        ))
        return [ExtractionJob(**item) for item in items]
    except Exception as e:
        logger.info(f"[ExtractionJobs] Failed to get jobs: {e}")
    
    return []


def get_jobs_by_model_and_user(model_id: str, user_id: str, limit: int = 50) -> List[ExtractionJob]:
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
        items = list(container.query_items(
            query=query,
            parameters=[
                {"name": "@model_id", "value": model_id},
                {"name": "@user_id", "value": user_id},
                {"name": "@limit", "value": limit}
            ],
            enable_cross_partition_query=True
        ))
        return [ExtractionJob(**item) for item in items]
    except Exception as e:
        logger.info(f"[ExtractionJobs] Failed to get model user jobs: {e}")
    
    return []


def get_jobs_by_user(user_id: str, limit: int = 50, tenant_id: Optional[str] = None) -> List[ExtractionJob]:
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

        items = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        return [ExtractionJob(**item) for item in items]
    except Exception as e:
        logger.info(f"[ExtractionJobs] Failed to get user jobs: {e}")
    
    return []


def get_latest_job_by_log_id(log_id: str) -> Optional[ExtractionJob]:
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
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@log_id", "value": log_id}],
            enable_cross_partition_query=True
        ))
        if items:
            return ExtractionJob(**items[0])
    except Exception as e:
        logger.info(f"[ExtractionJobs] Failed to get job by log_id: {e}")
    
    return None


def delete_job(job_id: str) -> bool:
    """Delete a job or log permanently by ID"""
    container = get_extractions_container()
    if not container:
        return False
    
    try:
        # Find item by ID to get partition key (model_id)
        # We query without type restriction to handle both Jobs and Logs
        query = "SELECT * FROM c WHERE c.id = @id"
        items = list(container.query_items(
            query=query,
            parameters=[{"name": "@id", "value": job_id}],
            enable_cross_partition_query=True
        ))
        
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

        container.delete_item(item=job_id, partition_key=partition_key)
        return True
    except Exception as e:
        logger.info(f"[ExtractionJobs] Failed to delete item {job_id}: {e}")
        return False


def cancel_job(job_id: str) -> Optional[ExtractionJob]:
    """Cancel a running job"""
    # Just update status. The background task might still run but result save will check job status?
    # Or we can't easily stop the background task thread.
    # But updating status prevents frontend from polling it as active.
    # But updating status prevents frontend from polling it as active.
    job = update_job(job_id, status=ExtractionStatus.CANCELLED.value, error="Cancelled by user")
    
    # Sync cancellation status to ExtractionLog if linked
    if job and (job.original_log_id or job.log_id):
        from app.services import extraction_logs
        log_id_to_update = job.original_log_id or job.log_id
        try:
            extraction_logs.update_log_status(
                log_id_to_update, 
                status=ExtractionStatus.CANCELLED.value
            )
        except Exception as e:
            logger.info(f"[ExtractionJobs] Failed to sync cancel status to log: {e}")
            
    return job
