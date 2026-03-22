"""
Extraction endpoints - Logs management
"""
from fastapi import APIRouter, Depends, Request
from typing import Optional, List
from app.services import extraction_logs
from app.services.audit import log_action, AuditAction, AuditResource
from app.core.auth import get_current_user, CurrentUser
from pydantic import BaseModel
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
    limit: int = 500
):
    """
    Get extraction logs for a specific model.
    Single-tenant: model_id is the only filter.
    Access control: handled by list_models (group permissions).
    """
    logs = await extraction_logs.get_logs_by_model(model_id, limit=limit)
    logger.info(f"[LOGS] user={current_user.email} model_id={model_id} count={len(logs)}")

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
    limit: int = 500,
    model_id: Optional[str] = None
):
    """
    Get all extraction logs.
    Single-tenant: model_id is the only filter (if provided).
    """
    if model_id:
        logs = await extraction_logs.get_logs_by_model(model_id, limit=limit)
    else:
        logs = await extraction_logs.get_all_logs(limit=limit)

    await log_action(
        user=current_user,
        action=AuditAction.EXPORT,
        resource_type=AuditResource.EXTRACTION,
        resource_id="ALL" if not model_id else model_id,
        details={"count": len(logs), "limit": limit, "model_id": model_id},
        request=request
    )

    return [log.model_dump() for log in logs]


@router.delete("/logs/bulk")
async def delete_logs_bulk(
    log_ids: List[str],
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete multiple extraction logs"""
    deleted_count = await extraction_logs.delete_logs(log_ids)
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
    log = await extraction_logs.get_log_by_id(log_id, model_id)
    if not log:
        # Try without model_id just in case (fallback)
        log = await extraction_logs.get_log(log_id)
        if not log:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Log not found")

    # Enforce Tenant Isolation (respect multi-tenant 'common' mode)
    from app.core.config import settings
    if settings.AZURE_AD_TENANT_ID not in ("common", ""):
        # Single-tenant mode: strict check, but allow 'default' legacy records
        if (current_user.tenant_id and log.tenant_id 
                and log.tenant_id not in (current_user.tenant_id, "default")
                and log.tenant_id != ""):
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Access denied")

    # Centralized hydration — never miss a field again
    from app.services.hydration import hydrate_preview_data, hydrate_debug_data, hydrate_extracted_data
    preview_data = await hydrate_preview_data(log.preview_data)
    debug_data = await hydrate_debug_data(log.debug_data)
    log.extracted_data = await hydrate_extracted_data(log.extracted_data)

    # Construct response with hydrated data
    from app.services.models import get_model_by_id
    from app.services.masking import mask_pii_data
    
    model = await get_model_by_id(log.model_id)
    if model:
        log.extracted_data = mask_pii_data(log.extracted_data, model)
        preview_data = mask_pii_data(preview_data, model)

    response = log.model_dump()
    response["preview_data"] = preview_data
    response["debug_data"] = debug_data
    
    return response


class UnmaskRequest(BaseModel):
    path: str  # JSON path like 'items.0.name' or 'customer_name'

class ExportAuditRequest(BaseModel):
    log_ids: List[str]
    model_id: Optional[str] = None

@router.post("/logs/audit/export")
async def audit_export_logs(
    payload: ExportAuditRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Called by the frontend when downloading Excel locally to ensure the EXPORT
    action is formally recorded in the backend AuditLog.
    """
    await log_action(
        user=current_user,
        action=AuditAction.EXPORT,
        resource_type=AuditResource.EXTRACTION,
        resource_id=payload.model_id or "MULTIPLE",
        details={
            "log_ids": payload.log_ids,
            "count": len(payload.log_ids)
        }
    )
    return {"status": "audited"}

@router.post("/logs/{log_id}/unmask")
async def unmask_log_field(
    log_id: str,
    payload: UnmaskRequest,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Unmask a specific PII field for a document using its JSON path and write to AuditLog.
    """
    # 1. Fetch raw log (bypassing the mask)
    log = await extraction_logs.get_log(log_id)
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Log not found")

    # Enforce Tenant Isolation (respect multi-tenant 'common' mode)
    from app.core.config import settings
    if settings.AZURE_AD_TENANT_ID not in ("common", ""):
        if (current_user.tenant_id and log.tenant_id 
                and log.tenant_id not in (current_user.tenant_id, "default")
                and log.tenant_id != ""):
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Access denied")

    # 2. Extract Data Hydration
    from app.services.hydration import hydrate_preview_data
    # Use preview_data or extracted_data
    preview_data = await hydrate_preview_data(log.preview_data)
    raw_data = log.extracted_data or {}
    if not raw_data and preview_data and getattr(preview_data, "get", None):
        raw_data = preview_data.get("guide_extracted", {})

    # 3. Find field using exact JSON path
    def get_value_by_path(data, path_str):
        if not path_str or not isinstance(data, dict):
            return None
            
        path_str = path_str.replace('[', '.').replace(']', '')
        parts = [p for p in path_str.split('.') if p]
        
        current = data
        for part in parts:
            if isinstance(current, dict):
                # Auto-unwrap 'value' dict if present and we aren't explicitly looking for 'value'
                if part not in current and "value" in current and isinstance(current["value"], (dict, list)):
                    current = current["value"]
                    
                if part in current:
                    current = current[part]
                else:
                    return None
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
                
        # If the final resolved value is still a wrapped dict, unwrap it.
        if isinstance(current, dict) and "value" in current:
            return current["value"]
            
        return current

    raw_value = get_value_by_path(raw_data, payload.path)

    if raw_value is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Path {payload.path} not found in this document")

    # 4. Write to AuditLog
    await log_action(
        user=current_user,
        action=AuditAction.READ, # Translates to UNMASK visually in audit logs based on details
        resource_type=AuditResource.EXTRACTION,
        resource_id=log_id,
        details={
            "unmask": True,
            "path": payload.path,
            "model_id": log.model_id
        }
    )

    return {"path": payload.path, "value": raw_value}
