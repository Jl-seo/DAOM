from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.services import doc_intel, extraction_logs
from app.services.models import get_model_by_id
from app.services import extraction_jobs
from app.core.auth import get_current_user, is_admin, CurrentUser
from app.core.enums import ExtractionStatus
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class PreviewRequest(BaseModel):
    file_url: str


class PreviewWithGuideRequest(BaseModel):
    file_url: str
    model_id: str  # Model with guide fields


class RefineRequest(BaseModel):
    file_url: str
    selected_columns: List[str]  # Column names selected by user
    model_id: str
    language: str = "ko"


class MatchColumnsRequest(BaseModel):
    extracted_columns: List[str]  # Column names extracted by AI
    target_fields: List[Dict[str, str]]  # Model fields [{key, label}]


class SaveExtractionRequest(BaseModel):
    model_id: str
    filename: str
    file_url: str
    guide_extracted: Any  # Model field values (Dict for form, List for table)
    other_data: Optional[List[Dict[str, Any]]] = []  # Additional selected data (values can be any type)
    log_id: Optional[str] = None  # Optional: Update existing log
    debug_data: Optional[Dict[str, Any]] = None  # Raw debug data to persist


class StartExtractionRequest(BaseModel):
    """Request to start async extraction job"""
    model_id: str
    filename: str
    file_url: str


# Background task to process extraction
async def process_extraction_job(job_id: str, model_id: str, file_url: str, candidate_file_url: Optional[str] = None, candidate_file_urls: Optional[List[str]] = None, candidate_filenames: Optional[List[str]] = None, barcode: Optional[str] = None):
    """Background task to run full extraction or comparison pipeline"""
    logger.info(f"[Background] Starting extraction job {job_id}")
    import mimetypes
    from app.services.storage import download_blob_to_bytes

    try:
        # 1. Update Status
        await extraction_jobs.update_job(job_id, status=ExtractionStatus.ANALYZING.value)

        # 2. Load Model to determine pipeline type
        model = get_model_by_id(model_id)
        if not model:
            await extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=f"Model {model_id} not found")
            return

        # ──────────────────────────────────────────────
        # COMPARISON BRANCH: model_type == "comparison"
        # ──────────────────────────────────────────────
        all_candidates = candidate_file_urls or ([candidate_file_url] if candidate_file_url else [])

        if getattr(model, "model_type", "extraction") == "comparison" and all_candidates:
            logger.info(f"[Background] Comparison mode: {len(all_candidates)} candidate(s)")
            from app.services.comparison_service import compare_images

            # Build comparison settings dict from model
            comp_settings = None
            if hasattr(model, "comparison_settings") and model.comparison_settings:
                comp_settings = model.comparison_settings if isinstance(model.comparison_settings, dict) else model.comparison_settings.dict()

            custom_instructions = getattr(model, "global_rules", None)

            comparisons: List[Dict[str, Any]] = []
            for i, cand_url in enumerate(all_candidates):
                try:
                    logger.info(f"[Background] Comparing candidate {i+1}/{len(all_candidates)}")
                    result = await compare_images(
                        image_url_1=file_url,
                        image_url_2=cand_url,
                        custom_instructions=custom_instructions,
                        comparison_settings=comp_settings,
                    )
                    comparisons.append({
                        "candidate_index": i,
                        "result": result,
                        "file_url": cand_url,
                        "filename": candidate_filenames[i] if candidate_filenames and i < len(candidate_filenames) else None,
                    })
                except Exception as comp_err:
                    logger.error(f"[Background] Comparison failed for candidate {i}: {comp_err}")
                    comparisons.append({
                        "candidate_index": i,
                        "result": {"differences": [], "metadata": {"error": str(comp_err)}},
                        "file_url": cand_url,
                        "filename": candidate_filenames[i] if candidate_filenames and i < len(candidate_filenames) else None,
                        "error": str(comp_err),
                    })

            preview_data: Dict[str, Any] = {
                "comparisons": comparisons,
                "comparison_result": comparisons[0]["result"] if comparisons else None,
            }

            await extraction_jobs.update_job(
                job_id,
                status=ExtractionStatus.PREVIEW_READY.value,
                preview_data=preview_data,
            )
            
            job = extraction_jobs.get_job(job_id)
            if job and getattr(job, "original_log_id", None):
                extraction_logs.update_log_status(
                    log_id=str(job.original_log_id),
                    status=ExtractionStatus.PREVIEW_READY.value,
                    preview_data=preview_data
                )
                
            logger.info(f"[Background] Completed comparison job {job_id} — {len(comparisons)} candidate(s) processed")
            return

        # ──────────────────────────────────────────────
        # EXTRACTION BRANCH (default)
        # ──────────────────────────────────────────────

        # 2b. Download File
        try:
            file_content = await download_blob_to_bytes(file_url)
            if not file_content:
                raise ValueError("Downloaded file content is empty or None")
            logger.info(f"[Background] Downloaded {len(file_content)} bytes from {file_url}")
        except Exception as e:
            error_msg = f"Failed to download file: {str(e)}"
            logger.error(f"[Background] {error_msg}")
            
            job = extraction_jobs.get_job(job_id)
            await extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=error_msg)
            if job and getattr(job, "original_log_id", None):
                extraction_logs.update_log_status(
                    log_id=str(job.original_log_id),
                    status=ExtractionStatus.ERROR.value,
                    error=error_msg
                )
            
            return

        # 3. Detect MIME type
        filename = file_url.split('/')[-1]
        mime_type, _ = mimetypes.guess_type(filename)
        
        # 4. Call Pure Extraction Service
        result = await extraction_service.run_extraction_pipeline(
            file_content=file_content,
            model_id=model_id,
            filename=filename,
            mime_type=mime_type or "",
            barcode=barcode
        )
        
        # 5. Handle Result
        job = extraction_jobs.get_job(job_id)
        if result.get("error"):
             await extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=result["error"])
             if job and getattr(job, "original_log_id", None):
                 extraction_logs.update_log_status(
                     log_id=str(job.original_log_id),
                     status=ExtractionStatus.ERROR.value,
                     error=result["error"]
                 )
        else:
             await extraction_jobs.update_job(
                job_id, 
                status=ExtractionStatus.PREVIEW_READY.value, 
                preview_data=result
            )
             if job and getattr(job, "original_log_id", None):
                 extraction_logs.update_log_status(
                     log_id=str(job.original_log_id),
                     status=ExtractionStatus.PREVIEW_READY.value,
                     preview_data=result
                 )

        logger.info(f"[Background] Completed extraction job {job_id}")

    except Exception as e:
        logger.error(f"[Background] FATAL ERROR in job {job_id}: {e}")
        import traceback
        traceback.print_exc()
        # Update job with error status
        try:
            job = extraction_jobs.get_job(job_id)
            await extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=str(e))
            if job and getattr(job, "original_log_id", None):
                extraction_logs.update_log_status(
                    log_id=str(job.original_log_id),
                    status=ExtractionStatus.ERROR.value,
                    error=str(e)
                )
        except Exception as update_err:
            logger.error(f"[Background] Failed to update job status: {update_err}")
            pass


@router.post("/start-job")
async def start_job_with_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    candidate_files: List[UploadFile] = File(None),  # Multi-file support
    model_id: str = Form(...),
    barcode: Optional[str] = Form(None), # DEX target validation (optional)
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Upload file(s) and start extraction/comparison job.
    If candidate_files provided, it's a comparison job.
    """
    # Unified file type validation — Azure DI Layout supports all these formats
    allowed_exts = ('.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.xlsx', '.xls', '.csv', '.docx')

    if not file.filename.lower().endswith(allowed_exts):
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(allowed_exts)}")

    # 1. Upload files
    from app.services.storage import upload_file_to_blob
    try:
        file_url = await upload_file_to_blob(file)

        candidate_file_urls = []
        candidate_filenames = []  # NEW: Store original filenames
        candidate_file_url = None # Legacy support

        if candidate_files:
            for c_file in candidate_files:
                url = await upload_file_to_blob(c_file)
                candidate_file_urls.append(url)
                candidate_filenames.append(c_file.filename)  # NEW: Store original filename

            # Set legacy single URL to the first one for backward compatibility
            if candidate_file_urls:
                candidate_file_url = candidate_file_urls[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    # 2. Create Log (Initial Pending State)
    user_id = current_user.id if current_user else "unknown"

    # Logs might need schema update too, but for now specific log fields are flexible or we use extracted_data
    # We won't break log schema yet, just store primary candidate in legacy field if needed
    log = extraction_logs.save_extraction_log(
        model_id=model_id,
        user_id=user_id,
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        filename=file.filename,
        file_url=file_url,
        candidate_file_url=candidate_file_url,
        candidate_file_urls=candidate_file_urls,  # NEW: Multi candidate files
        status="P100",  # Pending
        tenant_id=current_user.tenant_id if current_user else None
    )
    log_id = log.id if log else None

    # 3. Create Job linked to Log
    job = extraction_jobs.create_job(
        model_id=model_id,
        user_id=user_id,
        filename=file.filename,
        file_url=file_url,
        candidate_file_url=candidate_file_url,
        candidate_file_urls=candidate_file_urls, # NEW
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        original_log_id=log_id,  # Link to the log
        tenant_id=current_user.tenant_id if current_user else None
    )

    # 4. Start Background Process
    background_tasks.add_task(
        process_extraction_job,
        job.id,
        model_id,
        file_url,
        candidate_file_url,
        candidate_file_urls,
        candidate_filenames,  # NEW: Pass original filenames
        barcode # DEX validation
    )

    return {
        "job_id": job.id,
        "log_id": log_id,
        "file_url": file_url,
        "candidate_file_urls": candidate_file_urls,
        "status": job.status
    }

@router.post("/start-batch-jobs")
async def start_batch_jobs(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    model_id: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Upload multiple files and start independent extraction jobs for each (Phase 1 Batch Mode).
    """
    allowed_exts = ('.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.xlsx', '.xls', '.csv', '.docx')
    user_id = current_user.id if current_user else "unknown"
    
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files allowed per batch request to prevent timeouts. Please upload in smaller chunks.")
    
    from app.services.storage import upload_file_to_blob
    results = []
    
    for file in files:
        if not file.filename.lower().endswith(allowed_exts):
            results.append({"filename": file.filename, "error": f"Invalid extension"})
            continue
            
        try:
            file_url = await upload_file_to_blob(file)
            
            # Create Log
            log = extraction_logs.save_extraction_log(
                model_id=model_id,
                user_id=user_id,
                user_name=current_user.name if current_user else None,
                user_email=current_user.email if current_user else None,
                filename=file.filename,
                file_url=file_url,
                status="P100",  # Pending
                tenant_id=current_user.tenant_id if current_user else None
            )
            log_id = log.id if log else None
            
            # Create Job
            job = extraction_jobs.create_job(
                model_id=model_id,
                user_id=user_id,
                filename=file.filename,
                file_url=file_url,
                user_name=current_user.name if current_user else None,
                user_email=current_user.email if current_user else None,
                original_log_id=log_id,
                tenant_id=current_user.tenant_id if current_user else None
            )
            
            # Start Background Task
            background_tasks.add_task(
                process_extraction_job,
                job.id,
                model_id,
                file_url,
                None,  # No single candidate
                None,  # No candidate_file_urls
                None   # No candidate_filenames
            )
            
            results.append({
                "filename": file.filename,
                "job_id": job.id,
                "log_id": log_id,
                "status": "started"
            })
            
        except Exception as e:
            logger.error(f"[Batch Upload] Failed for {file.filename}: {str(e)}")
            results.append({"filename": file.filename, "error": str(e)})

    return {"results": results}

@router.post("/dex-validate")
async def dex_validate(
    cropped_image: UploadFile = File(...),
    barcode_value: str = Form(...),
    model_id: str = Form(...),
    target_field: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Hybrid Progressive UX DEX Validation Endpoint.
    1. Receives a small cropped Image & Barcode from the React Scanner.
    2. Calls Azure DI to extract 'queryFields' (Handwritten Name).
    3. Mocks an LIS database lookup using the barcode.
    4. Compares and returns Pass/Fail.
    """
    allowed_exts = ('.jpg', '.jpeg', '.png')
    if not cropped_image.filename.lower().endswith(allowed_exts):
        raise HTTPException(status_code=400, detail="Invalid cropped image format.")

    try:
        image_bytes = await cropped_image.read()

        # Step 1: Mock LIS Lookup based on Barcode ID
        # In a real scenario, this would be `requests.get('https://gclabs.lis/api/patient?barcode=...')`
        def mock_lis_lookup(barcode: str) -> str:
            # Deterministic mock based on the last digit of the barcode
            last_char = barcode[-1] if barcode else "0"
            mock_db = {
                "0": "김철수", "1": "홍길동", "2": "이영희", "3": "박지성", "4": "김연아",
                "5": "유재석", "6": "강호동", "7": "신동엽", "8": "이수근", "9": "전현무"
            }
            return mock_db.get(last_char, "알수없음")

        lis_name = mock_lis_lookup(barcode_value)

        # Step 2: Extract Handwritten text using Azure DI (query_fields)
        from app.services.doc_intel import extract_with_strategy
        # Using prebuilt-layout, requesting specific query fields
        di_result = await extract_with_strategy(
            file_source=image_bytes,
            model_type="prebuilt-layout",
            filename=cropped_image.filename,
            mime_type=cropped_image.content_type,
            features=["queryFields"],
            query_fields=[target_field] # Targeting the dynamic handwritten name
        )

        handwritten_name = "인식 실패"
        
        # Step 3: Parse Azure DI Output for the query field
        # In Azure DI, query fields appear in `result.documents[0].fields`
        documents = di_result.get("documents", [])
        if documents and len(documents) > 0:
            fields = documents[0].get("fields", {})
            # Look for the exact query field name
            if target_field in fields:
                field_data = fields[target_field]
                # Azure DI SDK usually populates `value_string` or `content`
                handwritten_name = field_data.get("value_string") or field_data.get("content") or "인식 실패"
        
        # Clean up strings (remove spaces, standardize)
        import re
        clean_lis = re.sub(r'\s+', '', lis_name).strip()
        clean_handwritten = re.sub(r'\s+', '', handwritten_name).strip()

        # Step 4: String Matching Logic
        is_match = (clean_lis == clean_handwritten)

        # Allow basic Levenshtein distance fallback (e.g., 홍길동 vs 홍길둥)
        if not is_match and len(clean_lis) > 2 and len(clean_handwritten) > 2:
            import Levenshtein
            distance = Levenshtein.distance(clean_lis, clean_handwritten)
            if distance <= 1: # Tolerate 1 typo
                is_match = True

        return {
            "barcode": barcode_value,
            "lis_name": lis_name,
            "handwritten_name": handwritten_name,
            "is_match": is_match
        }

    except Exception as e:
        logger.error(f"[DEX Validate] Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start-extraction")
async def start_extraction(
    request: StartExtractionRequest,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Start async extraction job. Returns job_id immediately.
    Client should poll /job/{job_id} for status.
    """
    user_id = current_user.id if current_user else "unknown"

    # 1. Create Log first (status=P100 pending)
    log = extraction_logs.save_extraction_log(
        model_id=request.model_id,
        user_id=user_id,
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        filename=request.filename,
        file_url=request.file_url,
        status="P100",  # Pending
        tenant_id=current_user.tenant_id if current_user else None
    )
    log_id = log.id if log else None

    # 2. Create Job with reference to Log
    job = extraction_jobs.create_job(
        model_id=request.model_id,
        user_id=user_id,
        filename=request.filename,
        file_url=request.file_url,
        user_name=current_user.name if current_user else None,
        user_email=current_user.email if current_user else None,
        original_log_id=log_id,
        tenant_id=current_user.tenant_id if current_user else None
    )

    # 3. Run extraction in background
    background_tasks.add_task(
        process_extraction_job,
        job.id,
        request.model_id,
        request.file_url
    )

    return {
        "job_id": job.id,
        "log_id": log_id,
        "status": job.status
    }


@router.get("/log/{log_id}")
async def get_log_by_id(
    log_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get a single extraction log by ID (for deep-linking) — hydrates from Blob"""
    log = extraction_logs.get_log(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Extraction log not found")

    # Centralized hydration — never miss a field again
    from app.services.hydration import hydrate_preview_data, hydrate_debug_data
    preview_data = await hydrate_preview_data(log.preview_data)
    debug_data = await hydrate_debug_data(log.debug_data)

    return {
        "id": log.id,
        "model_id": log.model_id,
        "filename": log.filename,
        "file_url": log.file_url,
        "status": log.status,
        "extracted_data": log.extracted_data,
        "preview_data": preview_data,
        "debug_data": debug_data,
        "candidate_file_url": log.candidate_file_url,
        "candidate_file_urls": log.candidate_file_urls,
        "created_at": log.created_at,
        "updated_at": log.updated_at,
        "user_name": log.user_name,
        "user_email": log.user_email,
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
    """Get job status for polling — hydrates large data from Blob Storage"""
    job = extraction_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Centralized hydration — never miss a field again
    from app.services.hydration import hydrate_preview_data, hydrate_debug_data
    preview_data = await hydrate_preview_data(job.preview_data)
    debug_data = await hydrate_debug_data(job.debug_data)

    return {
        "job_id": job.id,
        "status": job.status,
        "preview_data": preview_data,
        "extracted_data": job.extracted_data or (
            preview_data.get("sub_documents", [])[0].get("data", {}).get("guide_extracted", {})
            if preview_data and preview_data.get("sub_documents") else None
        ),
        "debug_data": debug_data,
        "error": job.error,
        "filename": job.filename,
        "file_url": job.file_url,
        "candidate_file_urls": job.candidate_file_urls,
        "log_id": job.original_log_id or job.log_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at
    }


@router.delete("/job/{job_id}")
async def delete_extraction_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete a job"""
    # Optional: check ownership if not admin
    job = extraction_jobs.get_job(job_id)
    if not job:
         raise HTTPException(status_code=404, detail="Job not found")

    if job.user_id != current_user.id and not await is_admin(current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    success = extraction_jobs.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete job")

    return {"success": True, "job_id": job_id}


@router.post("/job/{job_id}/cancel")
async def cancel_extraction_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Cancel a running job"""
    job = extraction_jobs.get_job(job_id)
    if not job:
         raise HTTPException(status_code=404, detail="Job not found")

    if job.user_id != current_user.id and not await is_admin(current_user):
        raise HTTPException(status_code=403, detail="Not authorized")

    updated_job = await extraction_jobs.cancel_job(job_id)
    if not updated_job:
         raise HTTPException(status_code=500, detail="Failed to cancel job")

    return {"success": True, "status": "cancelled"}


@router.post("/confirm-job/{job_id}")
async def confirm_job(
    job_id: str,
    request: Dict[str, Any],
    current_user: CurrentUser = Depends(get_current_user)
):
    """Confirm and save extraction job"""
    job = extraction_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Extract user_id early for use throughout the function
    user_id = current_user.id if current_user else "unknown"

    # Check for S100 (SUCCESS) status - only success jobs can be edited/confirmed
    if job.status != ExtractionStatus.SUCCESS.value:
        raise HTTPException(status_code=400, detail=f"Job is not ready for confirmation. Status: {job.status}")

    # Use edited data if provided, otherwise use preview data
    edited_data = request.get("edited_data") if request else None
    final_data = edited_data if edited_data else job.preview_data.get("guide_extracted", {})

    # Update job status
    try:
        await extraction_jobs.update_job(job_id, status=ExtractionStatus.SUCCESS.value, extracted_data=final_data)
        
        # Log audit
        # audit.log_action(...) - handled inside update_job now

    except Exception as e:
        logger.error(f"[Confirmation] Failed to update job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save result: {e}")

    try:
        # Multi-Document Support: Save extraction log for EACH sub-document
        saved_logs = []
        sub_docs = job.preview_data.get("sub_documents")
        logger.info(f"[ConfirmJob] Job {job_id} | SubDocs: {len(sub_docs) if sub_docs else 0} | original_log_id: {job.original_log_id}")

        if sub_docs and len(sub_docs) > 0:
            # Save each split as a separate record
            for idx, sub in enumerate(sub_docs):
                try:
                    if sub.get("status") == "success":  # Sub-doc internal status
                        # Flatten the data for this split
                        split_data = sub.get("data", {}).get("guide_extracted", {})

                        # Use original_log_id for the FIRST sub-doc (updates existing record)
                        # Additional sub-docs get new IDs
                        target_log_id = job.original_log_id if idx == 0 and job.original_log_id else None

                        log = extraction_logs.save_extraction_log(
                            model_id=job.model_id,
                            user_id=user_id,
                            user_name=(current_user.name if current_user and current_user.name else job.user_name or "Unknown"),
                            user_email=(current_user.email if current_user and current_user.email else job.user_email),
                            filename=f"{job.filename} (Doc {sub['index']})" if len(sub_docs) > 1 else job.filename,
                            file_url=job.file_url,
                            status=ExtractionStatus.SUCCESS.value,
                            extracted_data=split_data,
                            preview_data=sub.get("data"),  # Save full structure for this sub-doc
                            job_id=job_id,
                            tenant_id=current_user.tenant_id if current_user else None,
                            debug_data=job.debug_data
                        )
                        if log: saved_logs.append(log)
                except Exception as e:
                     logger.error(f"[ConfirmJob] Failed to save sub-doc {sub.get('index')}: {e}")

            # Use first doc data for return
            final_data = sub_docs[0].get("data", {}).get("guide_extracted", {}) if sub_docs else {}

        else:
            # Legacy/Single Doc mode
            logger.info(f"[ConfirmJob] Saving legacy single doc format")
            extraction_logs.save_extraction_log(
                model_id=job.model_id,
                user_id=user_id,
                user_name=(current_user.name if current_user and current_user.name else job.user_name or "Unknown"),
                user_email=(current_user.email if current_user and current_user.email else job.user_email),
                filename=job.filename,
                file_url=job.file_url,
                status=ExtractionStatus.SUCCESS.value,
                extracted_data=final_data,
                preview_data=job.preview_data,  # Save full structure for reload
                log_id=job.original_log_id,
                job_id=job_id,
                tenant_id=current_user.tenant_id if current_user else None,
                debug_data=job.debug_data
            )

    except Exception as e:
        logger.error(f"[ConfirmJob] Critical error saving logs: {e}")
        with open("last_error.txt", "w") as f:
            f.write(str(e))
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")

    # --- WEBHOOK CALL ---
    webhook_result = None
    try:
        model = get_model_by_id(job.model_id)
        if model and getattr(model, 'webhook_url', None):
            import httpx
            webhook_payload = {
                "event": "extraction_confirmed",
                "job_id": job_id,
                "model_id": job.model_id,
                "model_name": model.name,
                "filename": job.filename,
                "file_url": job.file_url,
                "extracted_data": final_data,
                "user_id": user_id,
                "user_email": current_user.email if current_user else None,
                "timestamp": job.updated_at or job.created_at
            }
            logger.info(f"[Webhook] Sending to {model.webhook_url}")
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(model.webhook_url, json=webhook_payload)
                webhook_result = {"status": resp.status_code, "success": resp.is_success}
                logger.info(f"[Webhook] Response: {resp.status_code}")
    except Exception as webhook_err:
        logger.error(f"[Webhook] Failed: {webhook_err}")
        webhook_result = {"error": str(webhook_err)}
    # ---------------------

    return {
        "success": True,
        "job_id": job_id,
        "extracted_data": final_data,
        "webhook": webhook_result
    }


@router.get("/jobs")
async def get_jobs(
    model_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 50
):
    """Get jobs for current user or model"""
    if model_id:
        jobs = extraction_jobs.get_jobs_by_model(model_id, limit)
    else:
        user_id = current_user.id if current_user else "unknown"
        jobs = extraction_jobs.get_jobs_by_user(user_id, limit)

    return [
        {
            "job_id": j.id,
            "model_id": j.model_id,
            "filename": j.filename,
            "status": j.status,
            "created_at": j.created_at,
            "updated_at": j.updated_at
        }
        for j in jobs
    ]


@router.post("/retry/{log_id}")
async def retry_extraction(
    log_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retry an extraction from a previous log (success or error).
    Updates the existing log status to processing and re-runs extraction.
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

    # 3. Recover candidate_file_urls from original log (for comparison models)
    candidate_file_urls = log.candidate_file_urls or []
    candidate_file_url = log.candidate_file_url or (candidate_file_urls[0] if candidate_file_urls else None)
    logger.info(f"[Retry] Recovered candidate_file_urls from log: {len(candidate_file_urls)} files")

    # 4. Create new job with reference to original log
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
        candidate_file_url=candidate_file_url,
        candidate_file_urls=candidate_file_urls,
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
        log.file_url,
        candidate_file_url,
        candidate_file_urls
    )

    return {
        "job_id": job.id,
        "status": job.status,
        "file_url": job.file_url,
        "candidate_file_urls": candidate_file_urls,  # NEW: Return for frontend
        "filename": job.filename,
        "original_log_id": log_id,
        "message": "Retry job started - existing record updated"
    }

@router.post("/save-extraction")
async def save_extraction(
    request: SaveExtractionRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Save the guide-based extraction result to database.
    """
    try:
        # Combine guide_extracted and any selected other_data
        raw_guide = request.guide_extracted
        extracted_data = list(raw_guide) if isinstance(raw_guide, list) else dict(raw_guide)

        # Add selected other_data as additional fields
        if request.other_data:
            for item in request.other_data:
                if 'column' in item and 'value' in item:
                    extracted_data[item['column']] = item['value']

        # Get user ID
        user_id = current_user.id if current_user else 'unknown'

        # Save to extraction logs
        log = extraction_logs.save_extraction_log(
            model_id=request.model_id,
            user_id=user_id,
            user_name=current_user.name if current_user else "Unknown",
            user_email=current_user.email if current_user else None,
            filename=request.filename,
            file_url=request.file_url,
            status=ExtractionStatus.SUCCESS.value,
            extracted_data=extracted_data,
            log_id=request.log_id,
            tenant_id=current_user.tenant_id if current_user else None,
            debug_data=request.debug_data
        )

        return {
            "success": True,
            "log_id": log.id if log else None,
            "extracted_data": extracted_data
        }

    except Exception as e:
        import traceback
        traceback.print_exc()

        # Save error log
        try:
            user_id = current_user.id if current_user else 'unknown'
            extraction_logs.save_extraction_log(
                model_id=request.model_id,
                user_id=user_id,
                user_name=current_user.name if current_user else "Unknown",
                filename=request.filename,
                file_url=request.file_url,
                status=ExtractionStatus.ERROR.value,
                error=str(e)
            )
        except Exception as log_err:
            logger.warning(f"[SaveExtraction] Failed to save error log: {log_err}")
            pass

        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")


@router.post("/match-columns")
async def match_columns_with_ai(request: MatchColumnsRequest):
    """
    Use OpenAI to semantically match extracted column names with model fields.
    Returns list of column names that should be pre-selected.
    """
    try:
        from openai import AsyncAzureOpenAI
        from app.core.config import settings

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        model_field_descriptions = [
            f"- {f.get('key', '')}: {f.get('label', '')}"
            for f in request.target_fields
        ]

        prompt = f"""You are a data field matching expert.

Given these extracted column names from a document:
{json.dumps(request.extracted_columns, ensure_ascii=False)}

And these target model fields (key: label):
{chr(10).join(model_field_descriptions)}

Match the extracted columns to the model fields semantically. Consider:
- Exact matches (e.g., "인보이스 번호" matches "invoice_number: 인보이스 번호")
- Semantic similarity (e.g., "Invoice Number" matches "invoice_number: 인보이스 번호")
- Abbreviations or variations (e.g., "발행일자" matches "issue_date: 발행일")

Return ONLY a JSON array of extracted column names that should be selected:
["column1", "column2", ...]

If no columns match, return an empty array: []
Return ONLY valid JSON, no markdown code blocks."""

        response = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a field matching expert. Return only valid JSON array."},
                {"role": "user", "content": prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        result = json.loads(response.choices[0].message.content)
        return {"matched_columns": result if isinstance(result, list) else []}

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Return empty on error - don't fail the whole flow
        return {"matched_columns": []}


@router.post("/preview-with-guide")
async def get_preview_with_guide(
    request: PreviewWithGuideRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Extract data guided by model fields.
    Returns:
    - guide_extracted: Values extracted for each model field (key-value pairs)
    - other_data: Other extracted data for optional selection
    """
    # Extract filename from URL for logging
    filename = request.file_url.split('/')[-1] if request.file_url else 'unknown'
    user_id = current_user.id if current_user else 'unknown'

    try:
        from openai import AsyncAzureOpenAI
        from app.core.config import settings

        # Get model definition
        model = get_model_by_id(request.model_id)
        if not model:
            # Log model not found error
            extraction_logs.save_extraction_log(
                model_id=request.model_id,
                user_id=user_id,
                filename=filename,
                file_url=request.file_url,
                status='error',
                error='Model not found'
            )
            raise HTTPException(status_code=404, detail="Model not found")

        # Get raw Document Intelligence output using Dynamic Strategy
        azure_model = getattr(model, "azure_model_id", settings.OCR_DEFAULT_MODEL)
        doc_intel_output = await doc_intel.extract_with_strategy(request.file_url, azure_model)

        # Build field descriptions for AI
        field_descriptions = []
        for field in model.fields:
            desc = f"- {field.key}: {field.label}"
            if hasattr(field, 'description') and field.description:
                desc += f" ({field.description})"
            field_descriptions.append(desc)

        # Build global rules and reference data sections
        global_rules_section = ""
        if hasattr(model, 'global_rules') and model.global_rules:
            global_rules_section = f"\n\nGlobal Rules (apply to ALL fields):\n{model.global_rules}"

        ref_data_section = ""
        if hasattr(model, 'reference_data') and model.reference_data:
            ref_json = json.dumps(model.reference_data, ensure_ascii=False, indent=2)
            ref_data_section = f"\n\nReference Data:\n{ref_json}"

        # AI prompt to extract values for each model field with confidence and positions
        extraction_prompt = f"""You are a document data extractor.

Given this document data extracted by Document Intelligence:
{json.dumps(doc_intel_output, ensure_ascii=False, indent=2)}

Extract values for these specific fields:
{chr(10).join(field_descriptions)}
{global_rules_section}
{ref_data_section}

Return a JSON object with TWO parts:
1. "guide_extracted": Object with each field key containing:
   - "value": The extracted value (string or null if not found)
   - "confidence": Your confidence level from 0.0 to 1.0 (e.g., 0.95 for high confidence)
   - "bbox": Bounding box if available from Document Intelligence [x1, y1, x2, y2] as percentages, or null

2. "other_data": Array of other data found that wasn't matched to fields, each with:
   - "column": The field/column name
   - "value": The value (can be string, array, or object)
   - "confidence": Confidence level 0.0 to 1.0
   - "bbox": Bounding box if available, or null

Example format:
{{
  "guide_extracted": {{
    "invoice_number": {{"value": "INV-2024-001", "confidence": 0.98, "bbox": [10, 5, 30, 8]}},
    "issue_date": {{"value": "2024-01-15", "confidence": 0.92, "bbox": [50, 5, 70, 8]}},
    "amount": {{"value": "324.66", "confidence": 0.85, "bbox": [60, 40, 80, 43]}}
  }},
  "other_data": [
    {{"column": "VAT", "value": "32.47", "confidence": 0.90, "bbox": [60, 45, 80, 48]}},
    {{"column": "Line Items", "value": [{{"description": "Item 1", "qty": 2, "price": 100}}], "confidence": 0.88, "bbox": null}}
  ]
}}

IMPORTANT:
- For guide_extracted, use the exact field keys provided
- If a field value cannot be found, set value to null and confidence to 0
- Confidence should reflect how certain you are the extraction is correct
- bbox coordinates are percentages (0-100) of page dimensions [left, top, right, bottom]
- If Document Intelligence provides bounding box, include it; otherwise null
- Return ONLY valid JSON, no markdown code blocks."""

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        response = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a precise document data extractor. Return only valid JSON."},
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        result = json.loads(response.choices[0].message.content)

        # Ensure proper structure
        return {
            "guide_extracted": result.get("guide_extracted", {}),
            "other_data": result.get("other_data", []),
            "model_fields": [{"key": f.key, "label": f.label} for f in model.fields]
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()

        # Save error log for any failure
        try:
            extraction_logs.save_extraction_log(
                model_id=request.model_id,
                user_id=user_id,
                filename=filename,
                file_url=request.file_url,
                status='error',
                error=str(e)
            )
        except Exception as log_err:
            logger.warning(f"[PreviewWithGuide] Failed to save error log: {log_err}")
            pass  # Don't fail if logging fails

        raise HTTPException(status_code=500, detail=f"Guide extraction failed: {str(e)}")


@router.post("/preview")
async def get_extraction_preview(request: PreviewRequest):
    """
    Step 1: Get Document Intelligence output using generic layout model, then ask AI to structure it into a table
    Returns AI-structured data with clear columns and sample rows
    """
    try:
        # Get raw Document Intelligence output using Dynamic Strategy
        # Use analyze_document_layout for backward compatibility with layout model
        # Or specifically use extract_with_strategy if model ID is available
        # Here we follow existing logic: Layout model for "full preview" unless specified otherwise
        doc_intel_output = await doc_intel.analyze_document_layout(request.file_url)

        # Ask AI to structure this into a meaningful table
        structuring_prompt = f"""
You are a data structuring expert. Given the following Document Intelligence extraction results (tables and key-value pairs), 
create a unified, structured table format.

Document Intelligence Output:
{json.dumps(doc_intel_output, ensure_ascii=False, indent=2)}

Your task:
1. Identify meaningful column headers (e.g., "상호명", "공급가액", "날짜" etc.)
2. Structure the data into rows with those columns
3. Return ONLY a JSON object with this structure:
{{
  "columns": [
    {{
      "name": "column_name",
      "sample_values": ["value1", "value2", "value3"]
    }}
  ],
  "total_rows": number
}}

Make column names clear and descriptive in Korean. Include up to 5 sample values per column.
Return ONLY valid JSON, no markdown code blocks.
"""

        # Call LLM to structure the data
        from openai import AsyncAzureOpenAI
        from app.core.config import settings

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        response = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a data structuring expert. Return only valid JSON."},
                {"role": "user", "content": structuring_prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        structured_result = json.loads(response.choices[0].message.content)

        return {
            "raw_data": doc_intel_output,  # Keep for debugging
            "structured_table": structured_result
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.post("/refine")
async def refine_extraction(
    request: RefineRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Step 2: Given user-selected columns, extract those specific fields from the document
    """
    try:
        # 1. Get Model to determine strategy
        model = get_model_by_id(request.model_id)
        # Default to layout if model not found or no strategy
        azure_model = getattr(model, "azure_model_id", settings.OCR_DEFAULT_MODEL) if model else settings.OCR_DEFAULT_MODEL

        # Get Document Intelligence output using correct strategy
        doc_intel_output = await doc_intel.extract_with_strategy(request.file_url, azure_model)

        # Extract only selected columns
        extraction_prompt = f"""
Given this Document Intelligence data:
{json.dumps(doc_intel_output, ensure_ascii=False, indent=2)}

Extract the following columns ONLY:
{', '.join(request.selected_columns)}

Return a JSON object where keys are the column names and values are the extracted data.
Example: {{"상호명": "회사이름", "공급가액": "1000000"}}

Return ONLY valid JSON, no markdown.
"""

        from openai import AsyncAzureOpenAI
        from app.core.config import settings

        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

        response = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a data extraction expert. Return only valid JSON."},
                {"role": "user", "content": extraction_prompt}
            ],
            temperature=settings.LLM_DEFAULT_TEMPERATURE
        )

        extracted_data = json.loads(response.choices[0].message.content)

        # Save extraction log
        user_id = current_user.id if current_user else 'unknown'

        extraction_logs.save_extraction_log(
            model_id=request.model_id,
            user_id=user_id,
            user_name=current_user.name if current_user else "Unknown",
            user_email=current_user.email if current_user else None,
            filename=request.file_url.split('/')[-1],  # Extract filename from URL
            status=ExtractionStatus.SUCCESS.value,
            file_url=request.file_url,
            extracted_data=extracted_data,
            tenant_id=current_user.tenant_id if current_user else None
        )

        return {
            "structured_data": extracted_data,
            "selected_columns": request.selected_columns
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()

        # Save error log
        try:
            user_id = current_user.id if current_user else 'unknown'

            extraction_logs.save_extraction_log(
                model_id=request.model_id,
                user_id=user_id,
                user_name=current_user.name if current_user else "Unknown",
                filename=request.file_url.split('/')[-1],
                status=ExtractionStatus.ERROR.value,
                file_url=request.file_url,
                error=str(e)
            )
        except Exception as log_err:
            logger.warning(f"[Refine] Failed to save error log: {log_err}")
            pass  # Don't fail if logging fails

        raise HTTPException(status_code=500, detail=f"Refinement failed: {str(e)}")


@router.get("/logs")
async def get_extraction_logs_by_model(
    model_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 100
):
    """
    Get extraction logs for a specific model
    """
    if await is_admin(current_user):
        logs = extraction_logs.get_logs_by_model(model_id=model_id, limit=limit)
    else:
        # Non-admin: only their own logs for this model
        logs = extraction_logs.get_logs_by_user(user_id=current_user.id, limit=limit)
        logs = [log for log in logs if log.model_id == model_id]
    return [log.model_dump() for log in logs]


@router.get("/logs/all")
async def get_all_extraction_logs(
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 100,
    model_id: Optional[str] = None
):
    """
    Get all extraction logs (admin) or user's logs (regular user)
    Optional filter by model_id
    """
    user_oid = current_user.id

    # Admin can see all logs, regular users see only their logs
    if await is_admin(current_user):
        logs = extraction_logs.get_all_logs(limit=limit)
    else:
        logs = extraction_logs.get_logs_by_user(user_id=user_oid, limit=limit)

    # Filter by model_id if provided
    if model_id:
        logs = [log for log in logs if log.model_id == model_id]

    return [log.model_dump() for log in logs]


@router.delete("/logs/bulk-delete")
async def bulk_delete_logs(
    log_ids: List[str],
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Bulk delete extraction logs.
    Admins can delete any logs, regular users can only delete their own.
    """
    if not log_ids:
        raise HTTPException(status_code=400, detail="No log IDs provided")

    # Verify permissions for each log
    if not await is_admin(current_user):
        # Non-admin: verify they own all logs
        for log_id in log_ids:
            log = extraction_logs.get_log(log_id)
            if not log or log.user_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to delete log {log_id}"
                )

    deleted_count = extraction_logs.delete_logs(log_ids)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "requested_count": len(log_ids)
    }
