"""
Extraction endpoints - Logs management
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from app.services import extraction_logs
from app.core.auth import get_current_user, CurrentUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/logs")
def get_extraction_logs_by_model(
    model_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = 100
):
    """
    Get extraction logs for a specific model
    """
    logs = extraction_logs.get_logs_by_model(model_id, limit=limit)
    return [log.model_dump() for log in logs]


@router.get("/logs/all")
def get_all_extraction_logs(
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
        logs = extraction_logs.get_logs_by_model(model_id, limit=limit)
    else:
        logs = extraction_logs.get_all_logs(limit=limit)
    
    return [log.model_dump() for log in logs]


@router.delete("/logs/bulk")
def delete_logs_bulk(
    log_ids: List[str],
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete multiple extraction logs"""
    deleted_count = extraction_logs.delete_logs(log_ids)
    return {"deleted_count": deleted_count}
