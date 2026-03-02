"""
Dictionary API Endpoints
Manage dictionary indexes for auto-normalization (port codes, charge codes, etc.)
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from app.core.auth import get_current_user, CurrentUser
from app.core.permissions import require_admin
from app.services.dictionary_service import get_dictionary_service
from app.services.audit import log_action, AuditAction, AuditResource

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/categories")
async def list_categories(current_user: CurrentUser = Depends(get_current_user)):
    """List all registered dictionary categories with item counts."""
    service = get_dictionary_service()
    if not service.is_available:
        # Graceful fallback — panel shows empty state instead of error
        return {"categories": [], "_service_status": "not_configured"}

    categories = await service.list_categories()
    return {"categories": categories}


@router.post("/upload", dependencies=[Depends(require_admin)])
async def upload_dictionary(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Upload an Excel/CSV file to create or update a dictionary."""
    service = get_dictionary_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail="Dictionary service not configured.")

    file_bytes = await file.read()
    result = await service.upload_from_excel(file_bytes, category, filename=file.filename or "")

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Audit log
    await log_action(
        user=current_user,
        action=AuditAction.UPDATE_MODEL,
        resource_type=AuditResource.MODEL,
        resource_id=f"dictionary:{category}",
        details={
            "action": "dictionary_upload",
            "category": category,
            "filename": file.filename,
            "count": result.get("count", 0)
        },
        request=request
    )

    return result


@router.get("/search")
async def search_dictionary(
    q: str,
    category: str = None,
    top_k: int = 5,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Search dictionary entries. Supports keyword search with category filter."""
    service = get_dictionary_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail="Dictionary service not configured.")

    matches = await service.search(q, category=category, top_k=top_k)
    return {
        "query": q,
        "matches": [
            {"code": m.code, "name": m.name, "category": m.category, "score": m.score}
            for m in matches
        ]
    }


@router.delete("/{category}", dependencies=[Depends(require_admin)])
async def delete_category(
    category: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete all entries for a dictionary category."""
    service = get_dictionary_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail="Dictionary service not configured.")

    count = await service.delete_category(category)

    # Audit log
    await log_action(
        user=current_user,
        action=AuditAction.DELETE_EXTRACTION,
        resource_type=AuditResource.MODEL,
        resource_id=f"dictionary:{category}",
        details={
            "action": "dictionary_delete",
            "category": category,
            "deleted_count": count
        },
        request=request
    )

    return {"deleted": count, "category": category}
