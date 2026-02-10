"""
Extraction endpoints - Logs management
"""
from fastapi import APIRouter, Depends, Request
from typing import Optional, List
from app.services import extraction_logs
from app.services.audit import log_action, AuditAction, AuditResource
from app.core.auth import get_current_user, CurrentUser
from app.core.rate_limit import limiter
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/logs")
@limiter.limit("60/minute")  # Enterprise: Prevent bulk data scraping
async def get_extraction_logs_by_model(
    request: Request,
    model_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 100
):
    """
    Get extraction logs for a specific model
    """
    # Fix IDOR: Enforce tenant isolation
    tenant_id = current_user.tenant_id if current_user else None
    logs = extraction_logs.get_logs_by_model(model_id, limit=limit, tenant_id=tenant_id)

    # Enterprise Hardening: Audit bulk data access for exfiltration detection
    await log_action(
        user=current_user,
        action=AuditAction.READ,
        resource_type=AuditResource.EXTRACTION,
        resource_id=model_id,
        details={"count": len(logs), "limit": limit},
        request=request
    )

    return [log.model_dump() for log in logs]


@router.get("/logs/all")
@limiter.limit("30/minute")  # Enterprise: Stricter limit for /all endpoint
async def get_all_extraction_logs(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 100,
    model_id: Optional[str] = None
):
    """
    Get all extraction logs (admin) or user's logs (regular user)
    Optional filter by model_id
    """
    tenant_id = current_user.tenant_id if current_user else None

    if model_id:
        logs = extraction_logs.get_logs_by_model(model_id, limit=limit, tenant_id=tenant_id)
    else:
        logs = extraction_logs.get_all_logs(limit=limit, tenant_id=tenant_id)

    # Enterprise Hardening: Audit bulk data access for exfiltration detection
    await log_action(
        user=current_user,
        action=AuditAction.EXPORT,  # EXPORT for /all endpoint signifies broader intent
        resource_type=AuditResource.EXTRACTION,
        resource_id="ALL" if not model_id else model_id,
        details={"count": len(logs), "limit": limit, "model_id": model_id},
        request=request
    )

    return [log.model_dump() for log in logs]


@router.delete("/logs/bulk")
def delete_logs_bulk(
    log_ids: List[str],
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete multiple extraction logs"""
    deleted_count = extraction_logs.delete_logs(log_ids)
    return {"deleted_count": deleted_count}


@router.get("/logs/{log_id}")
async def get_extraction_log(
    log_id: str,
    model_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get a single extraction log with full data (hydrated from Blob)
    """
    log = extraction_logs.get_log_by_id(log_id, model_id)
    if not log:
        # Try without model_id just in case (fallback)
        log = extraction_logs.get_log(log_id)
        if not log:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Log not found")

    # Enforce Tenant Isolation
    if current_user.tenant_id and log.tenant_id and log.tenant_id != current_user.tenant_id:
        # Admin bypass could be added here if needed
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")

    # Hydrate preview_data from Blob if offloaded
    # Logic mirrors extraction_preview.py
    preview_data = log.preview_data
    if preview_data and isinstance(preview_data, dict) and preview_data.get("_preview_blob_path"):
        try:
            from app.services.storage import load_json_from_blob
            full_preview = await load_json_from_blob(preview_data["_preview_blob_path"])
            if full_preview:
                preview_data = full_preview
        except Exception as e:
            logger.error(f"[API] Failed to hydrate log preview from blob: {e}")

    # Hydrate individual offloaded fields within preview_data
    if preview_data and isinstance(preview_data, dict):
        from app.services.storage import load_json_from_blob
        for field_key in ["raw_content", "_beta_parsed_content", "_beta_ref_map", "raw_tables"]:
            field_val = preview_data.get(field_key)
            if isinstance(field_val, dict) and field_val.get("source") == "blob_storage" and field_val.get("blob_path"):
                try:
                    hydrated = await load_json_from_blob(field_val["blob_path"])
                    if hydrated is not None:
                        preview_data[field_key] = hydrated
                except Exception as e:
                    logger.error(f"[API] Failed to hydrate log {field_key} from blob: {e}")

    # Hydrate debug_data from Blob if offloaded
    debug_data = log.debug_data
    if debug_data and isinstance(debug_data, dict) and debug_data.get("_debug_blob_path"):
        try:
            from app.services.storage import load_json_from_blob
            full_debug = await load_json_from_blob(debug_data["_debug_blob_path"])
            if full_debug:
                debug_data = full_debug
        except Exception as e:
            logger.error(f"[API] Failed to hydrate log debug from blob: {e}")

    # Construct response with hydrated data
    response = log.model_dump()
    response["preview_data"] = preview_data
    response["debug_data"] = debug_data
    
    return response
