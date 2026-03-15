"""
Vibe Dictionary API Endpoints
Manage synonym entries (AI-learned and manual) in the unified reference_data container.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
from app.core.auth import get_current_user, CurrentUser
from app.core.permissions import require_admin
from app.services.extraction.reference_data import get_reference_data_service
from app.services.models import get_model_by_id
import logging

logger = logging.getLogger(__name__)

router = APIRouter(redirect_slashes=False)


@router.get("")
@router.get("/")
async def get_vibe_dictionary_entries(current_user: CurrentUser = Depends(get_current_user)):
    """
    Fetch all synonym (Vibe Dictionary) entries from the unified reference_data container.
    """
    try:
        service = get_reference_data_service()
        if not service.is_available:
            return []
        
        # Get all synonyms (no model filter = list all)
        entries = await service.list_synonyms()
        
        # Fetch model name map
        from app.db.cosmos import get_models_container
        models_container = get_models_container()
        model_name_map = {}
        if models_container:
            try:
                models_query = "SELECT c.id, c.name FROM c WHERE c.model_type = 'extraction' AND c.is_active = true"
                async for item in models_container.query_items(query=models_query, enable_cross_partition_query=True):
                    model_name_map[item["id"]] = item["name"]
            except Exception as e:
                logger.warning(f"[VibeDictionary] Failed to fetch model names: {e}")

        result = []
        for item in entries:
            model_id = item.get("model_id", "")
            # Include entries where the model exists or is global
            if model_id in model_name_map or model_id == "__global__":
                result.append({
                    "model_id": model_id,
                    "model_name": model_name_map.get(model_id, "🌐 Global"),
                    "field_name": item.get("field_name", "default"),
                    "raw_val": item.get("raw_val", ""),
                    "standard_val": item.get("value", ""),
                    "source": item.get("source", "MANUAL"),
                    "hit_count": item.get("hit_count", 0),
                    "is_verified": item.get("is_verified", False)
                })

        # Sort by hit_count descending
        result.sort(key=lambda x: x["hit_count"], reverse=True)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VibeDictionary] GET / failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Internal error: {str(e)}"})


@router.post("/", dependencies=[Depends(require_admin)])
async def add_vibe_entry(data: Dict[str, Any], current_user: CurrentUser = Depends(get_current_user)):
    """Create a new synonym entry."""
    model_id = data.get("model_id")
    raw_val = data.get("raw_val", "").strip()
    standard_val = data.get("standard_val", "").strip()
    field_name = data.get("field_name", "default")

    if not model_id or not raw_val or not standard_val:
        raise HTTPException(status_code=400, detail="model_id, raw_val, standard_val are required")

    service = get_reference_data_service()
    doc = await service.upsert_synonym(
        model_id=model_id,
        field_name=field_name,
        raw_val=raw_val,
        standard_val=standard_val,
        source="MANUAL",
        is_verified=True
    )

    return {"message": "등록되었습니다", "entry": doc}


@router.put("/{model_id}/{field_name}/{raw_val}", dependencies=[Depends(require_admin)])
async def update_vibe_entry(
    model_id: str,
    field_name: str,
    raw_val: str,
    data: Dict[str, Any],
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update an existing synonym entry."""
    service = get_reference_data_service()
    
    try:
        updated = await service.update_synonym(model_id, field_name, raw_val, data)
        return {"message": "수정되었습니다", "entry": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{model_id}/{field_name}/{raw_val}", dependencies=[Depends(require_admin)])
async def delete_vibe_entry(
    model_id: str,
    field_name: str,
    raw_val: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete a synonym entry."""
    service = get_reference_data_service()
    
    success = await service.delete_synonym(model_id, field_name, raw_val)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return {"message": "삭제되었습니다"}
