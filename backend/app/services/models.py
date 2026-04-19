"""
Models Service - Manages extraction models in Azure Cosmos DB (Async)

Falls back to local JSON file if Cosmos DB is not configured.
"""
import json
import os
import uuid
from datetime import datetime
from typing import List, Optional
from app.schemas.model import ExtractionModel, ExtractionModelCreate
from app.db.cosmos import get_models_container, get_vibe_dictionary_container
import logging

logger = logging.getLogger(__name__)

# Fallback JSON file
MODELS_FILE = "extraction_models.json"


def _load_models_from_json() -> List[ExtractionModel]:
    """Load models from local JSON file (fallback)"""
    if not os.path.exists(MODELS_FILE):
        return []
    with open(MODELS_FILE, "r") as f:
        try:
            data = json.load(f)
            return [ExtractionModel(**item) for item in data]
        except Exception:
            return []


def _save_models_to_json(models: List[ExtractionModel]):
    """Save models to local JSON file (fallback)"""
    with open(MODELS_FILE, "w") as f:
        json.dump([model.model_dump() for model in models], f, indent=2)


async def load_models() -> List[ExtractionModel]:
    """Load all models from Cosmos DB or JSON fallback"""
    container = get_models_container()

    if not container:
        logger.info("[Models] Using JSON fallback")
        return _load_models_from_json()

    try:
        items = [item async for item in container.read_all_items()]
        logger.info(f"[Models] Loaded {len(items)} models from Cosmos DB")

        # Per-item validation: one malformed doc must not blackhole every
        # model. Previously a single schema mismatch caused the whole list
        # to fall back to the bundled JSON (2 sample rows), hiding the
        # user's real Cosmos models entirely. We now skip broken docs and
        # log them so the operator can fix the offending document.
        models: List[ExtractionModel] = []
        skipped: List[tuple[str, str]] = []
        for item in items:
            try:
                models.append(ExtractionModel(**item))
            except Exception as item_err:  # noqa: BLE001
                skipped.append((item.get("id", "<no-id>"), str(item_err)))

        if skipped:
            logger.error(
                f"[Models] Skipped {len(skipped)}/{len(items)} "
                f"malformed model documents:"
            )
            for mid, err in skipped:
                # Truncate long Pydantic error messages in log lines
                logger.error(f"[Models]   id={mid}  error={err[:500]}")

        return models
    except Exception as e:
        logger.error(f"[Models] Cosmos read failed: {e}")
        return _load_models_from_json()


async def save_model(model: ExtractionModel) -> ExtractionModel:
    """Save or update a model in Cosmos DB"""
    container = get_models_container()

    if not container:
        # JSON fallback
        models = _load_models_from_json()
        existing_idx = next((i for i, m in enumerate(models) if m.id == model.id), None)
        if existing_idx is not None:
            models[existing_idx] = model
        else:
            models.append(model)
        _save_models_to_json(models)
        return model

    try:
        model_dict = model.model_dump()
        await container.upsert_item(model_dict)
        logger.info(f"[Models] Saved model {model.id} to Cosmos DB")
        return model
    except Exception as e:
        logger.error(f"[Models] Cosmos save failed: {e}")
        raise e


async def create_model(model_data: ExtractionModelCreate) -> ExtractionModel:
    """Create a new model"""
    model = ExtractionModel(
        id=str(uuid.uuid4()),
        **model_data.model_dump(),
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat()
    )
    return await save_model(model)


async def update_model(model_id: str, model_data: dict) -> Optional[ExtractionModel]:
    """Update an existing model"""
    existing = await get_model_by_id(model_id)
    if not existing:
        return None

    updated_dict = existing.model_dump()
    updated_dict.update(model_data)
    updated_dict["updated_at"] = datetime.utcnow().isoformat()

    model = ExtractionModel(**updated_dict)
    return await save_model(model)


async def get_model_by_id(model_id: str) -> Optional[ExtractionModel]:
    """Get a single model by ID, including joined vibe_dictionaries reference data"""
    container = get_models_container()
    vibe_container = get_vibe_dictionary_container()

    if not container:
        models = _load_models_from_json()
        for model in models:
            if model.id == model_id:
                return model
        return None

    try:
        item = await container.read_item(item=model_id, partition_key=model_id)
        
        # Application-level join: Fetch all Vibe Dictionary entries for this model
        reference_data = item.get("reference_data", {}) or {}
        
        if vibe_container:
            query = "SELECT * FROM c WHERE c.model_id = @model_id"
            parameters = [{"name": "@model_id", "value": model_id}]
            
            try:
                vibe_items = [v async for v in vibe_container.query_items(
                    query=query, 
                    parameters=parameters, 
                    enable_cross_partition_query=True # Optional safeguard depending on index
                )]
                
                # Reconstruct the reference_data dictionary
                for v_item in vibe_items:
                    field = v_item.get("field_name")
                    raw_val = v_item.get("raw_val")
                    
                    if not field or not raw_val:
                        continue
                        
                    if field not in reference_data:
                        reference_data[field] = {}
                        
                    reference_data[field][raw_val] = {
                        "value": v_item.get("value", ""),
                        "source": v_item.get("source", "MANUAL"),
                        "is_verified": v_item.get("is_verified", True),
                        "hit_count": v_item.get("hit_count", 1)
                    }
                    
                item["reference_data"] = reference_data
            except Exception as e:
                logger.error(f"[Models] Failed to fetch vibe_dictionaries for {model_id}: {e}")

        return ExtractionModel(**item)
    except Exception as e:
        logger.warning(f"[Models] get_model_by_id({model_id}) failed: {e}")
        return None


async def delete_model(model_id: str) -> bool:
    """Delete a model by ID"""
    container = get_models_container()

    if not container:
        models = _load_models_from_json()
        original_len = len(models)
        models = [m for m in models if m.id != model_id]
        if len(models) < original_len:
            _save_models_to_json(models)
            return True
        return False

    try:
        await container.delete_item(item=model_id, partition_key=model_id)
        logger.info(f"[Models] Deleted model {model_id}")
        return True
    except Exception as e:
        logger.error(f"[Models] Delete failed: {e}")
        return False


# Legacy function for backward compatibility
async def save_models(models: List[ExtractionModel]):
    """Bulk save models (for migration)"""
    for model in models:
        await save_model(model)
