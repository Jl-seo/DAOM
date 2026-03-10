from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from app.core.auth import get_current_user, CurrentUser
from app.core.permissions import require_admin
from app.db.cosmos import get_models_container, get_vibe_dictionary_container
from app.services.models import get_model_by_id
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/")
async def get_vibe_dictionary_entries(current_user: CurrentUser = Depends(get_current_user)):
    """
    Fetch all Vibe Dictionary entries from the standalone vibe_dictionaries container.
    Returns: [ { "model_id", "model_name", "field_name", "raw_val", "standard_val", "source", "hit_count", "is_verified" } ]
    """
    vibe_container = get_vibe_dictionary_container()
    models_container = get_models_container()
    
    if not vibe_container or not models_container:
        raise HTTPException(status_code=503, detail="Database not configured")
        
    # Pre-fetch model names to avoid N+1 queries
    models_query = "SELECT c.id, c.name FROM c WHERE c.model_type = 'extraction' AND c.is_active = true"
    model_name_map = {}
    async for item in models_container.query_items(query=models_query, enable_cross_partition_query=True):
        model_name_map[item["id"]] = item["name"]

    entries = []
    # Fetch all vibe dictionary entries
    query = "SELECT * FROM c"
    async for v_item in vibe_container.query_items(query=query, enable_cross_partition_query=True):
        model_id = v_item.get("model_id")
        # Only include entries where the parent model exists and is active
        if model_id in model_name_map:
            entries.append({
                "model_id": model_id,
                "model_name": model_name_map[model_id],
                "field_name": v_item.get("field_name"),
                "raw_val": v_item.get("raw_val"),
                "standard_val": v_item.get("value", ""),
                "source": v_item.get("source", "MANUAL"),
                "hit_count": v_item.get("hit_count", 1),
                "is_verified": v_item.get("is_verified", False)
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
    """Manually add a new Vibe Dictionary entry into vibe_dictionaries container."""
    vibe_container = get_vibe_dictionary_container()
    if not vibe_container:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Verify model exists
    model = await get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    # Check if duplicate exists
    query = "SELECT * FROM c WHERE c.model_id = @model_id AND c.field_name = @field AND c.raw_val = @raw_val"
    parameters = [
        {"name": "@model_id", "value": model_id},
        {"name": "@field", "value": field_name},
        {"name": "@raw_val", "value": raw_val}
    ]
    
    existing = [v async for v in vibe_container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)]
    
    if existing:
        # Update existing
        doc = existing[0]
        doc["value"] = standard_val
        doc["source"] = "MANUAL"
        doc["is_verified"] =  True
        await vibe_container.upsert_item(body=doc)
    else:
        # Create new
        doc = {
            "id": str(uuid.uuid4()),
            "model_id": model_id,
            "field_name": field_name,
            "raw_val": raw_val,
            "value": standard_val,
            "source": "MANUAL",
            "is_verified": True,
            "hit_count": 1
        }
        await vibe_container.create_item(body=doc)
    
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
    Update an existing Vibe Dictionary entry.
    Payload allows "is_verified" or "standard_val".
    """
    vibe_container = get_vibe_dictionary_container()
    if not vibe_container:
        raise HTTPException(status_code=503, detail="Database not configured")

    query = "SELECT * FROM c WHERE c.model_id = @model_id AND c.field_name = @field AND c.raw_val = @raw_val"
    parameters = [
        {"name": "@model_id", "value": model_id},
        {"name": "@field", "value": field_name},
        {"name": "@raw_val", "value": raw_val}
    ]
    
    existing = [v async for v in vibe_container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)]
    
    if not existing:
        raise HTTPException(status_code=404, detail="Dictionary entry not found")
        
    entry = existing[0]
        
    if "is_verified" in payload:
        entry["is_verified"] = payload["is_verified"]
    if "standard_val" in payload:
        entry["value"] = payload["standard_val"]
        
    await vibe_container.upsert_item(body=entry)
    
    return {"status": "success", "entry": entry}

@router.delete("/{model_id}/{field_name}/{raw_val}")
async def delete_vibe_dictionary_entry(
    model_id: str,
    field_name: str,
    raw_val: str,
    current_user: CurrentUser = Depends(require_admin)
):
    """Delete a Vibe Dictionary entry."""
    vibe_container = get_vibe_dictionary_container()
    if not vibe_container:
        raise HTTPException(status_code=503, detail="Database not configured")

    query = "SELECT c.id, c.model_id FROM c WHERE c.model_id = @model_id AND c.field_name = @field AND c.raw_val = @raw_val"
    parameters = [
        {"name": "@model_id", "value": model_id},
        {"name": "@field", "value": field_name},
        {"name": "@raw_val", "value": raw_val}
    ]
    
    existing = [v async for v in vibe_container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)]
    
    if not existing:
        raise HTTPException(status_code=404, detail="Dictionary entry not found")
        
    doc_to_delete = existing[0]
    await vibe_container.delete_item(item=doc_to_delete["id"], partition_key=doc_to_delete["model_id"])
    
    return {"status": "success", "message": "Entry deleted"}
