"""
Dictionary API Endpoints
Manage dictionary indexes for auto-normalization (port codes, charge codes, etc.)

Backend: ReferenceDataService (Cosmos DB + in-memory fuzzy matching)
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from app.core.auth import get_current_user, CurrentUser
from app.core.permissions import require_admin
from app.services.extraction.reference_data import get_reference_data_service
from app.services.audit import log_action, AuditAction, AuditResource

import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/categories")
async def list_categories(model_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """List all registered dictionary categories with item counts."""
    service = get_reference_data_service()
    logger.info(f"[Dict API] list_categories called: model_id={model_id}, service.is_available={service.is_available}")
    if not service.is_available:
        logger.warning("[Dict API] Service not available — returning empty")
        return {"categories": []}

    categories = await service.list_categories(model_id)
    logger.info(f"[Dict API] list_categories returned {len(categories)} categories")
    return {"categories": categories}


@router.post("/upload", dependencies=[Depends(require_admin)])
async def upload_dictionary(
    request: Request,
    file: UploadFile = File(...),
    model_id: str = Form(...),
    category: str = Form(...),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Upload an Excel/CSV file to create or update a dictionary."""
    service = get_reference_data_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail="Dictionary service not configured.")

    file_bytes = await file.read()
    result = await service.upload_from_excel(file_bytes, model_id, category, filename=file.filename or "")

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
    model_id: str,
    category: str = None,
    top_k: int = 5,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Search dictionary entries. Uses in-memory fuzzy matching."""
    service = get_reference_data_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail="Dictionary service not configured.")

    result = await service.match(q, model_id, category or "", threshold=0.3)
    matches = []
    if result:
        matches.append({
            "code": result.standard_code,
            "name": result.standard_label,
            "category": result.category,
            "score": result.score,
            **result.extra
        })
    
    return {
        "query": q,
        "matches": matches
    }


@router.delete("/{category}", dependencies=[Depends(require_admin)])
async def delete_category(
    category: str,
    model_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete all entries for a dictionary category."""
    service = get_reference_data_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail="Dictionary service not configured.")

    try:
        count = await service.delete_category(model_id, category)
    except Exception as e:
        logger.error(f"Failed to delete dictionary {category}: {e}")
        raise HTTPException(status_code=500, detail=f"딕셔너리 삭제 실패: {str(e)}")

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


@router.get("/entries")
async def list_entries(
    model_id: str,
    category: str,
    offset: int = 0,
    limit: int = 100,
    search: str = "",
    current_user: CurrentUser = Depends(get_current_user)
):
    """List entries in a dictionary category with pagination."""
    service = get_reference_data_service()
    if not service.is_available:
        return {"entries": [], "total": 0}

    result = await service.list_entries(model_id, category, offset, limit, search)
    return result


@router.put("/entries/{entry_id}", dependencies=[Depends(require_admin)])
async def update_entry(
    entry_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update a single dictionary entry."""
    service = get_reference_data_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail="Dictionary service not configured.")

    body = await request.json()
    model_id = body.pop("model_id", "__global__")

    try:
        updated = await service.update_entry(entry_id, model_id, body)
        return {"ok": True, "entry": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entries/{entry_id}", dependencies=[Depends(require_admin)])
async def delete_entry(
    entry_id: str,
    model_id: str = "__global__",
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete a single dictionary entry."""
    service = get_reference_data_service()
    if not service.is_available:
        raise HTTPException(status_code=503, detail="Dictionary service not configured.")

    ok = await service.delete_entry(entry_id, model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True}
