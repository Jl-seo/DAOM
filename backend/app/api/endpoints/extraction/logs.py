"""
Extraction endpoints - Logs management
"""
from fastapi import APIRouter, HTTPException, Depends, Request
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
