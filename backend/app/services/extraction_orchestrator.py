"""
Extraction Orchestrator — Background Pipeline & Confirmation Logic
===================================================================
Extracted from extraction_preview.py to enforce clean separation:
  - API endpoints (FastAPI routes) → extraction_preview.py
  - Business logic (pipeline, save, webhook) → this file

All functions here are pure async business logic with NO FastAPI
dependencies (no Request, Response, Depends, HTTPException).
"""
import logging
import mimetypes
import traceback
from typing import Any, Dict, List, Optional

from app.core.enums import ExtractionStatus
from app.services import extraction_jobs, extraction_logs
from app.services.models import get_model_by_id

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Background Pipeline (was process_extraction_job)
# ──────────────────────────────────────────────

async def run_pipeline_job(
    job_id: str,
    model_id: str,
    file_url: str,
    candidate_file_url: Optional[str] = None,
    candidate_file_urls: Optional[List[str]] = None,
    candidate_filenames: Optional[List[str]] = None,
    barcode: Optional[str] = None,
):
    """Background task to run full extraction or comparison pipeline."""
    logger.info(f"[Background] Starting extraction job {job_id}")
    from app.services.storage import download_blob_to_bytes
    from app.services.extraction_service import extraction_service

    try:
        # 1. Update Status
        await extraction_jobs.update_job(job_id, status=ExtractionStatus.ANALYZING.value)

        # 2. Load Model to determine pipeline type
        model = await get_model_by_id(model_id)
        if not model:
            await extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=f"Model {model_id} not found")
            return

        # ── COMPARISON BRANCH ──
        all_candidates = candidate_file_urls or ([candidate_file_url] if candidate_file_url else [])

        if getattr(model, "model_type", "extraction") == "comparison" and all_candidates:
            await _run_comparison_branch(job_id, model, file_url, all_candidates, candidate_filenames)
            return

        # ── EXTRACTION BRANCH (default) ──

        # 2b. Download File
        try:
            file_content = await download_blob_to_bytes(file_url)
            if not file_content:
                raise ValueError("Downloaded file content is empty or None")
            logger.info(f"[Background] Downloaded {len(file_content)} bytes from {file_url}")
        except Exception as e:
            error_msg = f"Failed to download file: {str(e)}"
            logger.error(f"[Background] {error_msg}")

            job = await extraction_jobs.get_job(job_id)
            await extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=error_msg)
            if job and getattr(job, "original_log_id", None):
                await extraction_logs.update_log_status(
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
        job = await extraction_jobs.get_job(job_id)
        if result.get("error"):
             await extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=result["error"])
             if job and getattr(job, "original_log_id", None):
                 try:
                     await extraction_logs.update_log_status(
                         log_id=str(job.original_log_id),
                         status=ExtractionStatus.ERROR.value,
                         error=result["error"]
                     )
                 except Exception as log_sync_err:
                     logger.error(f"[Background] Log sync (error) failed for job {job_id}: {log_sync_err}")
        else:
             export_preview = None
             if getattr(model, "export_config", None) and model.export_config.enabled:
                 from app.services.extraction.export_engine import apply_export_definition
                 try:
                     gui_data = result.get("guide_extracted", {})
                     sub_docs = result.get("sub_documents")
                     if not gui_data and sub_docs and len(sub_docs) > 0:
                         gui_data = sub_docs[0].get("data", {}).get("guide_extracted", {})
                     
                     if isinstance(gui_data, list) and len(gui_data) > 0:
                         exported_data = apply_export_definition(gui_data, model.export_config)
                         if exported_data:
                             export_preview = exported_data
                             # Attach to result so preview_data has it too (optional, but good for logs)
                             result["extracted_data"] = exported_data
                             logger.info(f"[Background] Applied export definition for preview generation for {job_id}")
                 except Exception as e:
                     logger.error(f"[Background] Preview export mapping failed: {e}")

             await extraction_jobs.update_job(
                job_id,
                status=ExtractionStatus.PREVIEW_READY.value,
                preview_data=result,
                extracted_data=export_preview
            )
             logger.info(f"[Background] Job {job_id} status set to PREVIEW_READY")

             # Note: update_job already auto-syncs status to ExtractionLog internally.
             # This explicit call is a safety fallback but MUST NOT crash the pipeline.
             if job and getattr(job, "original_log_id", None):
                 try:
                     await extraction_logs.update_log_status(
                         log_id=str(job.original_log_id),
                         status=ExtractionStatus.PREVIEW_READY.value,
                         preview_data=result
                     )
                 except Exception as log_sync_err:
                     logger.error(f"[Background] Log sync failed for job {job_id} (non-fatal, job is already PREVIEW_READY): {log_sync_err}")

             # Trigger Async Vibe Dictionary Generator
             try:
                 import asyncio
                 asyncio.create_task(run_vibe_processing_background(job_id, model_id, result))
                 logger.info(f"[Background] Launched Vibe Dictionary AI generator for job {job_id}")
             except Exception as vibe_error:
                 logger.error(f"[Background] Failed to launch Vibe Dictionary generator: {vibe_error}")

        logger.info(f"[Background] Completed extraction job {job_id}")

    except Exception as e:
        logger.error(f"[Background] FATAL ERROR in job {job_id}: {e}")
        traceback.print_exc()
        # Update job with error status
        try:
            job = await extraction_jobs.get_job(job_id)
            await extraction_jobs.update_job(job_id, status=ExtractionStatus.ERROR.value, error=str(e))
            if job and getattr(job, "original_log_id", None):
                await extraction_logs.update_log_status(
                    log_id=str(job.original_log_id),
                    status=ExtractionStatus.ERROR.value,
                    error=str(e)
                )
        except Exception as update_err:
            logger.error(f"[Background] Failed to update job status: {update_err}")
            pass


async def _run_comparison_branch(
    job_id: str,
    model,
    file_url: str,
    all_candidates: List[str],
    candidate_filenames: Optional[List[str]] = None,
):
    """Run comparison pipeline for 1:N image comparison."""
    logger.info(f"[Background] Comparison mode: {len(all_candidates)} candidate(s)")
    from app.services.comparison_service import compare_images

    # Build comparison settings dict from model
    comp_settings = None
    if hasattr(model, "comparison_settings") and model.comparison_settings:
        comp_settings = model.comparison_settings if isinstance(model.comparison_settings, dict) else model.comparison_settings.dict()

    custom_instructions = getattr(model, "global_rules", None)

    import asyncio
    comparisons: List[Dict[str, Any]] = []
    sem = asyncio.Semaphore(3)

    # Fetch reference data for Vibe Dictionary normalization in comparison
    reference_data = getattr(model, "reference_data", None)

    async def _compare_single(i, cand_url):
        async with sem:
            try:
                logger.info(f"[Background] Comparing candidate {i+1}/{len(all_candidates)}")
                result = await compare_images(
                    image_url_1=file_url,
                    image_url_2=cand_url,
                    custom_instructions=custom_instructions,
                    comparison_settings=comp_settings,
                    reference_data=reference_data,
                )
                return {
                    "candidate_index": i,
                    "result": result,
                    "file_url": cand_url,
                    "filename": candidate_filenames[i] if candidate_filenames and i < len(candidate_filenames) else None,
                }
            except Exception as comp_err:
                logger.error(f"[Background] Comparison failed for candidate {i}: {comp_err}")
                return {
                    "candidate_index": i,
                    "result": {"differences": [], "metadata": {"error": str(comp_err)}},
                    "file_url": cand_url,
                    "filename": candidate_filenames[i] if candidate_filenames and i < len(candidate_filenames) else None,
                    "error": str(comp_err),
                }

    tasks = [_compare_single(i, cand_url) for i, cand_url in enumerate(all_candidates)]
    comparisons = await asyncio.gather(*tasks)
    
    # Sort by candidate_index to preserve original order
    comparisons.sort(key=lambda x: x["candidate_index"])

    preview_data: Dict[str, Any] = {
        "comparisons": comparisons,
        "comparison_result": comparisons[0]["result"] if comparisons else None,
    }

    await extraction_jobs.update_job(
        job_id,
        status=ExtractionStatus.PREVIEW_READY.value,
        preview_data=preview_data,
    )

    job = await extraction_jobs.get_job(job_id)
    if job and getattr(job, "original_log_id", None):
        await extraction_logs.update_log_status(
            log_id=str(job.original_log_id),
            status=ExtractionStatus.PREVIEW_READY.value,
            preview_data=preview_data
        )

    logger.info(f"[Background] Completed comparison job {job_id} — {len(comparisons)} candidate(s) processed")


# ──────────────────────────────────────────────
# Confirm & Save Logic (was inside confirm_job endpoint)
# ──────────────────────────────────────────────

async def confirm_and_save_job(
    job_id: str,
    edited_data: Optional[Any],
    user_id: str,
    user_name: str,
    user_email: Optional[str],
    tenant_id: Optional[str],
) -> Dict[str, Any]:
    """
    Confirm extraction job: save to logs, call webhook if configured.

    Returns dict with {"success", "job_id", "extracted_data", "webhook"}.
    Raises ValueError/RuntimeError on business errors.
    """
    job = await extraction_jobs.get_job(job_id)
    if not job:
        raise ValueError("Job not found")

    # Check for valid states: either PREVIEW_READY (initial confirmation) or SUCCESS (re-editing a confirmed job)
    valid_states = [ExtractionStatus.PREVIEW_READY.value, ExtractionStatus.SUCCESS.value]
    if job.status not in valid_states:
        raise ValueError(f"Job is not ready for confirmation. Status: {job.status}")

    # Use edited data if provided, otherwise use preview data
    final_data = edited_data if edited_data else job.preview_data.get("guide_extracted", {})

    model = await get_model_by_id(job.model_id)
    if not model:
        raise ValueError(f"Model {job.model_id} not found")

    # Apply Deterministic Export Mapping if configured
    if getattr(model, "export_config", None) and model.export_config.enabled:
        from app.services.extraction.export_engine import apply_export_definition
        try:
            exported_data = apply_export_definition(final_data, model.export_config)
            if exported_data:
                final_data = exported_data
                logger.info(f"[ExportEngine] Successfully mapped payload for job {job_id}")
        except Exception as e:
            logger.error(f"[ExportEngine] Failed to apply export definition for job {job_id}: {e}")

    # Update job status
    await extraction_jobs.update_job(job_id, status=ExtractionStatus.SUCCESS.value, extracted_data=final_data)

    # Save extraction log(s) — multi-document or single-doc
    sub_docs = job.preview_data.get("sub_documents")
    logger.info(f"[ConfirmJob] Job {job_id} | SubDocs: {len(sub_docs) if sub_docs else 0} | original_log_id: {job.original_log_id}")

    if sub_docs and len(sub_docs) > 0:
        final_data = await _save_multi_doc_logs(
            job=job, job_id=job_id, sub_docs=sub_docs,
            user_id=user_id, user_name=user_name, user_email=user_email, tenant_id=tenant_id
        )
    else:
        # Legacy/Single Doc mode
        logger.info(f"[ConfirmJob] Saving legacy single doc format")
        await extraction_logs.save_extraction_log(
            model_id=job.model_id,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            filename=job.filename,
            file_url=job.file_url,
            status=ExtractionStatus.SUCCESS.value,
            extracted_data=final_data,
            preview_data=job.preview_data,
            log_id=job.original_log_id,
            job_id=job_id,
            tenant_id=tenant_id,
            debug_data=job.debug_data,
            token_usage=job.preview_data.get("_token_usage") if job.preview_data else None
        )

    # Webhook
    webhook_result = await _call_webhook(job=job, job_id=job_id, final_data=final_data,
                                          user_id=user_id, user_email=user_email)

    return {
        "success": True,
        "job_id": job_id,
        "extracted_data": final_data,
        "webhook": webhook_result,
    }


async def _save_multi_doc_logs(
    job, job_id: str, sub_docs: list,
    user_id: str, user_name: str, user_email: Optional[str], tenant_id: Optional[str],
) -> Any:
    """Save extraction log for EACH sub-document. Returns final_data from first doc."""
    saved_logs = []
    for idx, sub in enumerate(sub_docs):
        try:
            if sub.get("status") == "success":
                split_data = sub.get("data", {}).get("guide_extracted", {})
                target_log_id = job.original_log_id if idx == 0 and job.original_log_id else None

                log = await extraction_logs.save_extraction_log(
                    model_id=job.model_id,
                    user_id=user_id,
                    user_name=user_name,
                    user_email=user_email,
                    filename=f"{job.filename} (Doc {sub['index']})" if len(sub_docs) > 1 else job.filename,
                    file_url=job.file_url,
                    status=ExtractionStatus.SUCCESS.value,
                    extracted_data=split_data,
                    preview_data=sub.get("data"),
                    job_id=job_id,
                    log_id=target_log_id,
                    tenant_id=tenant_id,
                    debug_data=job.debug_data,
                    token_usage=sub.get("data", {}).get("_token_usage")
                )
                if log:
                    saved_logs.append(log)
        except Exception as e:
            logger.error(f"[ConfirmJob] Failed to save sub-doc {sub.get('index')}: {e}")

    return sub_docs[0].get("data", {}).get("guide_extracted", {}) if sub_docs else {}


async def _call_webhook(
    job, job_id: str, final_data: Any,
    user_id: str, user_email: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Call webhook URL if configured on the model."""
    webhook_result = None
    try:
        model = await get_model_by_id(job.model_id)
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
                "user_email": user_email,
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

    return webhook_result

async def run_vibe_processing_background(job_id: str, model_id: str, result: Dict[str, Any]):
    """Background task to run Vibe Dictionary auto-discovery AFTER extraction completes.
    
    NOTE: Dictionary correction (apply_vibe_dictionary) is now handled synchronously 
    in extraction_service.py. This background task only runs LLM-based auto-discovery
    to generate new synonym suggestions for admin review.
    """
    try:
        from app.services import extraction_jobs, extraction_logs
        from app.services.dictionary.vibe_dictionary import generate_vibe_dictionary_async
        from app.core.enums import ExtractionStatus

        # Trigger Discovery (LLM Background Learning)
        logger.info(f"[Background Vibe] Starting AI Auto-Discovery for {job_id}")
        await generate_vibe_dictionary_async(model_id, result)
        logger.info(f"[Background Vibe] Phase 2 Complete for {job_id}")
        
    except Exception as e:
        logger.error(f"[Background Vibe] Failed: {e}")
        import traceback
        traceback.print_exc()
