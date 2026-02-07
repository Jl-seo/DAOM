"""
Extraction endpoints - Jobs management
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form, Request
from typing import Dict, Any, Optional, List
from app.services import extraction_jobs, extraction_logs
from app.services.models import get_model_by_id
from app.core.auth import get_current_user, CurrentUser
from app.core.config import settings
from app.core.enums import ExtractionStatus
from app.core.rate_limit import limiter
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


async def process_extraction_job(job_id: str, model_id: str, file_urls: List[str], filenames: List[str] = None):
    """Background task to run full extraction pipeline (Multi-file)"""
    from app.services.extraction_service import extraction_service
    # Pass necessary mapping for file_id generation if needed
    user_id = "bg-task" # TODO: Pass user_id
    filename = filenames[0] if filenames else "unknown"
    
    await extraction_service.run_extraction_pipeline(
        file_urls=file_urls, 
        model_id=model_id, 
        user_id=user_id,
        filename=filename,
        job_id=job_id,
        filenames=filenames
    )


@router.post("/start-job")
async def start_job_with_upload(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...), # Changed to List, expects 'files' key or 'file' if compatible?
    model_id: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Upload files and start extraction job.
    Supports single or multiple files.
    """
    from app.services.storage import upload_to_storage
    import asyncio
    
    # Upload files to Azure Blob Storage (Parallel)
    # Permission check: Verify user has access to this model
    from app.core.group_permission_utils import get_model_role_by_group
    from app.core.auth import is_super_admin
    
    is_super = await is_super_admin(current_user)
    if not is_super:
        model_role = await get_model_role_by_group(
            current_user.id, 
            current_user.tenant_id, 
            model_id
        )
        if model_role is None:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permission to use this model"
            )
    
    upload_tasks = []
    filenames = []
    
    for f in files:
        filenames.append(f.filename)
        upload_tasks.append(upload_to_storage(f))
    
    uploaded_urls = await asyncio.gather(*upload_tasks)
    
    # Filter failed uploads
    valid_urls = [url for url in uploaded_urls if url]
    if not valid_urls:
         raise HTTPException(status_code=500, detail="Failed to upload any files")
         
    primary_url = valid_urls[0]
    primary_filename = filenames[0]
    
    # Create extraction log
    log = extraction_logs.save_extraction_log(
        model_id=model_id,
        user_id=current_user.id if current_user else "unknown",
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        filename=primary_filename,
        file_url=primary_url,
        file_urls=valid_urls, # Multi
        filenames=filenames,
        status=ExtractionStatus.PENDING.value,
        tenant_id=current_user.tenant_id if current_user else None
    )
    
    # Create extraction job linked to log
    job = extraction_jobs.create_job(
        model_id=model_id,
        user_id=current_user.id if current_user else "unknown",
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        filename=primary_filename,
        file_url=primary_url,
        file_urls=valid_urls, # Multi
        filenames=filenames,
        original_log_id=log.id if log else None,
        tenant_id=current_user.tenant_id if current_user else None
    )
    
    # Update log to reference job
    if log:
        extraction_logs.save_extraction_log(
            model_id=model_id,
            user_id=current_user.id if current_user else "unknown",
            user_name=current_user.name if current_user else None,
            user_email=current_user.email if current_user else None,
            filename=primary_filename,
            file_url=primary_url,
            file_urls=valid_urls,
            filenames=filenames,
            status=ExtractionStatus.PENDING.value,
            log_id=log.id,
            job_id=job.id,
            tenant_id=current_user.tenant_id if current_user else None
        )
    
    # Start background extraction
    background_tasks.add_task(
        process_extraction_job,
        job.id,
        model_id,
        valid_urls,
        filenames
    )
    
    return {
        "job_id": job.id,
        "log_id": log.id if log else None,
        "file_url": primary_url,
        "filename": primary_filename,
        "status": job.status,
        "file_count": len(valid_urls)
    }


@router.get("/log/{log_id}/job")
def get_latest_job_for_log(
    log_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get the most recent job associated with a log"""
    job = extraction_jobs.get_latest_job_by_log_id(log_id)
    if not job:
        raise HTTPException(status_code=404, detail="No active job found for this log")
    
    return {
        "job_id": job.id,
        "status": job.status,
        "file_url": job.file_url,
        "filename": job.filename
    }


@router.get("/job/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get job status for polling"""
    job = extraction_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Hydrate debug_data from Blob if needed
    debug_data = job.debug_data
    if debug_data and debug_data.get("source") == "blob_storage":
        blob_path = debug_data.get("raw_data_blob_path")
        if blob_path:
            try:
                from app.services import storage
                raw_data = await storage.load_json_from_blob(blob_path)
                if raw_data:
                     # Merge or replace debug_data with full raw data
                     # We can either replace it entirely or wrap it
                     # Replacing is simpler for frontend which experts standard ADI structure
                     debug_data = raw_data
            except Exception as e:
                # Fallback: keep original metadata but add error
                debug_data["error"] = f"Failed to load full raw data: {e}"

    return {
        "job_id": job.id,
        "status": job.status,
        "preview_data": job.preview_data,
        "extracted_data": job.extracted_data,
        "debug_data": debug_data,
        "error": job.error,
        "filename": job.filename,
        "file_url": job.file_url,
        "candidate_file_url": job.candidate_file_url,
        "candidate_file_urls": job.candidate_file_urls,
        "created_at": job.created_at,
        "updated_at": job.updated_at
    }


@router.delete("/job/{job_id}")
def delete_extraction_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete a job"""
    success = extraction_jobs.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found or delete failed")
    return {"status": "deleted"}


@router.post("/job/{job_id}/cancel")
def cancel_extraction_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Cancel a running job"""
    job = extraction_jobs.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "cancelled", "job_id": job.id}


@router.get("/jobs")
@limiter.limit("60/minute")  # Enterprise: Prevent bulk job scraping
async def get_jobs(
    request: Request,
    model_id: Optional[str] = None,
    scope: str = "mine",  # mine, team
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 50
):
    """Get jobs for current user or model with scope control"""
    from app.core.permissions import check_model_permission
    from app.services.audit import log_action, AuditAction, AuditResource

    jobs = []

    # 1. Team View (Require Model Admin or Super Admin)
    # We use check_model_permission("Admin") which handles Super Admin logic internally
    if scope == "team" and model_id:
        has_permission = await check_model_permission(current_user, model_id, "Admin")
        
        if has_permission:
            jobs = extraction_jobs.get_jobs_by_model(model_id, limit=limit)
        else:
            # Fallback to mine if no permission for team view
            jobs = extraction_jobs.get_jobs_by_model_and_user(model_id, current_user.id, limit=limit)

    # 2. Mine View (My jobs in specific model)
    elif model_id:
        jobs = extraction_jobs.get_jobs_by_model_and_user(model_id, current_user.id, limit=limit)
        
    # 3. Global My View (All my jobs across models)
    else:
        tenant_id = current_user.tenant_id if current_user else None
        jobs = extraction_jobs.get_jobs_by_user(
            current_user.id if current_user else "unknown", 
            limit=limit,
            tenant_id=tenant_id
        )

    # Enterprise Hardening: Audit bulk data access for exfiltration detection
    await log_action(
        user=current_user,
        action=AuditAction.READ,
        resource_type="job",
        resource_id=model_id or "ALL",
        details={"count": len(jobs), "scope": scope, "limit": limit},
        request=request
    )
    
    return [{
        "id": job.id,
        "model_id": job.model_id,
        "filename": job.filename,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "error": job.error
    } for job in jobs]


@router.post("/retry/{log_id}")
async def retry_extraction(
    log_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retry an extraction from a previous log (success or error).
    Updates the existing log status to processing and re-runs extraction.
    For comparison models, preserves candidate_file_urls from the original job.
    """
    # 1. Get original log
    log = extraction_logs.get_log(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Extraction log not found")
        
    if not log.file_url:
        raise HTTPException(status_code=400, detail="Original file URL not found in log")
        
    # 2. Check model existence
    model = get_model_by_id(log.model_id)
    if not model:
         raise HTTPException(status_code=404, detail=f"Model {log.model_id} not found")
    
    # 3. Get previous job to recover candidate_file_urls (for comparison models)
    previous_job = extraction_jobs.get_latest_job_by_log_id(log_id)
    candidate_file_urls = None
    candidate_file_url = None
    if previous_job:
        candidate_file_urls = previous_job.candidate_file_urls
        candidate_file_url = previous_job.candidate_file_url
        logger.info(f"[Retry] Recovered candidate_file_urls from previous job: {len(candidate_file_urls) if candidate_file_urls else 0} files")
    
    # 4. Create new job with reference to original log AND preserved candidate files
    job = extraction_jobs.create_job(
        model_id=log.model_id,
        user_id=current_user.id if current_user else "unknown",
        filename=log.filename,
        file_url=log.file_url,
        candidate_file_url=candidate_file_url,
        candidate_file_urls=candidate_file_urls,
        original_log_id=log_id,
        tenant_id=current_user.tenant_id if current_user else None
    )

    # 5. Update original log status to pending AND update job_id
    extraction_logs.save_extraction_log(
        model_id=log.model_id,
        user_id=current_user.id if current_user else log.user_id,
        user_name=current_user.name if current_user else log.user_name,
        user_email=current_user.email if current_user else log.user_email,
        filename=log.filename,
        file_url=log.file_url,
        status="P100",  # Pending status code
        extracted_data=None,  # Clear previous data
        error=None,  # Clear previous error
        log_id=log_id,  # This updates the existing log
        job_id=job.id,   # Link to the new job
        tenant_id=current_user.tenant_id if current_user else None
    )
    
    # 6. Start background task
    background_tasks.add_task(
        process_extraction_job,
        job.id,
        log.model_id,
        log.file_url
    )
    
    return {
        "job_id": job.id,
        "status": job.status,
        "file_url": job.file_url,
        "candidate_file_url": candidate_file_url,
        "candidate_file_urls": candidate_file_urls,
        "filename": job.filename,
        "original_log_id": log_id,
        "message": "Retry job started - existing record updated"
    }

