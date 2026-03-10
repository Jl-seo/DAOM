from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from app.core.auth import get_current_user, CurrentUser
from app.core.permissions import require_admin
from app.db.cosmos import get_container
from app.services.models import get_model_by_id, update_model
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/")
async def get_vibe_dictionary_entries(current_user: CurrentUser = Depends(get_current_user)):
    """
    Fetch all Vibe Dictionary entries aggregated across all extraction models.
    Returns: [ { "model_id", "model_name", "field_name", "raw_val", "standard_val", "source", "hit_count", "is_verified" } ]
    """
    container = await get_container()
    
    # Query all active models
    query = "SELECT c.id, c.name, c.reference_data FROM c WHERE c.model_type = 'extraction' AND c.is_active = true"
    
    models = []
    async for item in container.query_items(query=query, enable_cross_partition_query=True):
        models.append(item)
    
    entries = []
    for model in models:
        model_id = model.get("id")
        model_name = model.get("name")
        ref_data = model.get("reference_data", {})
        
        if not ref_data:
            continue
            
        for field_name, mappings in ref_data.items():
            if not isinstance(mappings, dict):
                continue
                
            for raw_val, data in mappings.items():
                if isinstance(data, dict) and "source" in data:
                    # It's a VibeDictionaryEntry
                    entries.append({
                        "model_id": model_id,
                        "model_name": model_name,
                        "field_name": field_name,
                        "raw_val": raw_val,
                        "standard_val": data.get("value", ""),
                        "source": data.get("source", "MANUAL"),
                        "hit_count": data.get("hit_count", 1),
                        "is_verified": data.get("is_verified", False)
                    })
                    
    # Sort by hit_count descending, then model_name
    entries.sort(key=lambda x: (-x["hit_count"], x["model_name"], x["field_name"], x["raw_val"]))
    return entries

@router.post("/")
async def add_vibe_dictionary_entry(
    model_id: str,
    field_name: str,
    raw_val: str,
    standard_val: str,
    current_user: CurrentUser = Depends(require_admin)
):
    """Manually add a new Vibe Dictionary entry mapping."""
    model = await get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    ref_data = getattr(model, "reference_data", {}) or {}
    
    if field_name not in ref_data:
        ref_data[field_name] = {}
        
    ref_data[field_name][raw_val] = {
        "value": standard_val,
        "source": "MANUAL",
        "is_verified": True,
        "hit_count": 1
    }
    
    # Update Model
    await update_model(model_id, {"reference_data": ref_data})
    
    return {"status": "success", "message": "Entry added"}

@router.put("/{model_id}/{field_name}/{raw_val}")
async def update_vibe_dictionary_entry(
    model_id: str,
    field_name: str,
    raw_val: str,
    payload: Dict[str, Any],
    current_user: CurrentUser = Depends(require_admin)
):
    """
    Update an existing Vibe Dictionary entry (e.g., toggle is_verified or change standard_val).
    Payload allows "is_verified" or "standard_val".
    """
    model = await get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    ref_data = getattr(model, "reference_data", {}) or {}
    
    if field_name not in ref_data or raw_val not in ref_data[field_name]:
        raise HTTPException(status_code=404, detail="Dictionary entry not found")
        
    entry = ref_data[field_name][raw_val]
    if not isinstance(entry, dict):
        raise HTTPException(status_code=400, detail="Entry is not in the correct format")
        
    if "is_verified" in payload:
        entry["is_verified"] = payload["is_verified"]
    if "standard_val" in payload:
        entry["value"] = payload["standard_val"]
        
    await update_model(model_id, {"reference_data": ref_data})
    
    return {"status": "success", "entry": entry}

@router.delete("/{model_id}/{field_name}/{raw_val}")
async def delete_vibe_dictionary_entry(
    model_id: str,
    field_name: str,
    raw_val: str,
    current_user: CurrentUser = Depends(require_admin)
):
    """Delete a Vibe Dictionary entry."""
    model = await get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    ref_data = getattr(model, "reference_data", {}) or {}
    
    if field_name not in ref_data or raw_val not in ref_data[field_name]:
        raise HTTPException(status_code=404, detail="Dictionary entry not found")
        
    del ref_data[field_name][raw_val]
    
    # If field is empty after deletion, remove the field container too
    if not ref_data[field_name]:
        del ref_data[field_name]
        
    await update_model(model_id, {"reference_data": ref_data})
    
    return {"status": "success", "message": "Entry deleted"}
