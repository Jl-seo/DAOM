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
    limit: int = 500
):
    """
    Get extraction logs for a specific model
    """
    # Fix IDOR: Enforce tenant isolation
    tenant_id = current_user.tenant_id if current_user else None
    logs = await extraction_logs.get_logs_by_model(model_id, limit=limit, tenant_id=tenant_id)

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
    limit: int = 500,
    model_id: Optional[str] = None
):
    """
    Get all extraction logs (admin) or user's logs (regular user)
    Optional filter by model_id
    """
    tenant_id = current_user.tenant_id if current_user else None

    if model_id:
        logs = await extraction_logs.get_logs_by_model(model_id, limit=limit, tenant_id=tenant_id)
    else:
        logs = await extraction_logs.get_all_logs(limit=limit, tenant_id=tenant_id)

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

    # Enforce Tenant Isolation
    if current_user.tenant_id and log.tenant_id and log.tenant_id != current_user.tenant_id:
        # Admin bypass could be added here if needed
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")

    # Centralized hydration — never miss a field again
    from app.services.hydration import hydrate_preview_data, hydrate_debug_data
    preview_data = await hydrate_preview_data(log.preview_data)
    debug_data = await hydrate_debug_data(log.debug_data)

    # Construct response with hydrated data
    response = log.model_dump()
    response["preview_data"] = preview_data
    response["debug_data"] = debug_data
    
    return response
