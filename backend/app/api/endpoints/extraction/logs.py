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


@router.get("/logs/{log_id}")
async def get_log_detail(
    log_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get detailed extraction log.
    Automatically hydrates debug_data from Blob Storage if available (recovering full OCR text).
    """
    log = extraction_logs.get_log(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    
    # Hydrate debug_data from Blob if needed (Optimization for historical data)
    debug_data = log.debug_data
    if debug_data and debug_data.get("source") == "blob_storage":
        blob_path = debug_data.get("raw_data_blob_path")
        if blob_path:
            try:
                from app.services import storage
                raw_data = await storage.load_json_from_blob(blob_path)
                if raw_data:
                     # Merge or replace debug_data with full raw data
                     # Use update to preserve existing keys if any, but raw_data usually has full set
                     if isinstance(debug_data, dict) and isinstance(raw_data, dict):
                         debug_data.update(raw_data)
                     else:
                         debug_data = raw_data
                     
                     # Update log object
                     log.debug_data = debug_data
            except Exception as e:
                # Log error but return what we have
                logger.warning(f"[LogDetail] Failed to hydrate debug data: {e}")
                if isinstance(debug_data, dict):
                    debug_data["error"] = f"Failed to hydrate: {str(e)}"

    return log.model_dump()
