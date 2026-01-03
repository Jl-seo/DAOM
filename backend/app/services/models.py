"""
Models Service - Manages extraction models in Azure Cosmos DB

Falls back to local JSON file if Cosmos DB is not configured.
"""
import json
import os
import uuid
from datetime import datetime
from typing import List, Optional
from app.schemas.model import ExtractionModel, ExtractionModelCreate
from app.db.cosmos import get_models_container
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


def load_models() -> List[ExtractionModel]:
    """Load all models from Cosmos DB or JSON fallback"""
    container = get_models_container()
    
    if not container:
        logger.info("[Models] Using JSON fallback")
        return _load_models_from_json()
    
    try:
        items = list(container.read_all_items())
        logger.info(f"[Models] Loaded {len(items)} models from Cosmos DB")
        return [ExtractionModel(**item) for item in items]
    except Exception as e:
        logger.error(f"[Models] Cosmos read failed: {e}")
        return _load_models_from_json()


def save_model(model: ExtractionModel) -> ExtractionModel:
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
        container.upsert_item(model_dict)
        logger.info(f"[Models] Saved model {model.id} to Cosmos DB")
        return model
    except Exception as e:
        logger.error(f"[Models] Cosmos save failed: {e}")
        raise e


def create_model(model_data: ExtractionModelCreate) -> ExtractionModel:
    """Create a new model"""
    model = ExtractionModel(
        id=str(uuid.uuid4()),
        **model_data.model_dump(),
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat()
    )
    return save_model(model)


def update_model(model_id: str, model_data: dict) -> Optional[ExtractionModel]:
    """Update an existing model"""
    existing = get_model_by_id(model_id)
    if not existing:
        return None
    
    updated_dict = existing.model_dump()
    updated_dict.update(model_data)
    updated_dict["updated_at"] = datetime.utcnow().isoformat()
    
    model = ExtractionModel(**updated_dict)
    return save_model(model)


def get_model_by_id(model_id: str) -> Optional[ExtractionModel]:
    """Get a single model by ID"""
    container = get_models_container()
    
    if not container:
        models = _load_models_from_json()
        for model in models:
            if model.id == model_id:
                return model
        return None
    
    try:
        item = container.read_item(item=model_id, partition_key=model_id)
        return ExtractionModel(**item)
    except Exception:
        return None


def delete_model(model_id: str) -> bool:
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
        container.delete_item(item=model_id, partition_key=model_id)
        logger.info(f"[Models] Deleted model {model_id}")
        return True
    except Exception as e:
        logger.error(f"[Models] Delete failed: {e}")
        return False


# Legacy function for backward compatibility
def save_models(models: List[ExtractionModel]):
    """Bulk save models (for migration)"""
    for model in models:
        save_model(model)
