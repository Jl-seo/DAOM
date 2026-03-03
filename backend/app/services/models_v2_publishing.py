"""
Models V2 Publishing Service - Manages lifecycle (Draft, Testing, Published) non-intrusively.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional
from app.db.cosmos import get_models_container
from app.schemas.model_v2 import VersionedExtractionModel
from app.services.models import get_model_by_id, save_model

logger = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

async def get_active_models_v2(tenant_id: Optional[str] = None) -> List[VersionedExtractionModel]:
    """
    Get all models that are either explicitly PUBLISHED or legacy (no status).
    Performs Lazy Migration on the fly.
    """
    container = get_models_container()
    if not container:
        return []

    try:
        # Cosmos DB query: get PUBLISHED or where status is missing (Legacy)
        query = "SELECT * FROM c WHERE (NOT IS_DEFINED(c.status) OR c.status = 'PUBLISHED')"
        parameters = []

        if tenant_id:
            # Assuming tenant multi-tenancy is based on a field like tenant_id if applicable.
            # Currently original models.py doesn't strictly filter tenant for models, 
            # but we can add placeholders. Let's stick to the current schema.
            pass

        items = [item async for item in container.query_items(
            query=query,
            parameters=parameters,
        )]

        v2_models = []
        for item in items:
            # Add lazy defaults if missing
            if "status" not in item:
                item["status"] = "PUBLISHED"
            if "version" not in item:
                item["version"] = "v1.0.0"
            v2_models.append(VersionedExtractionModel(**item))
            
        return v2_models
    except Exception as e:
        logger.error(f"[ModelsV2] get_active_models_v2 failed: {e}")
        return []


async def create_draft_v2(parent_model_id: str) -> Optional[VersionedExtractionModel]:
    """
    Creates a new DRAFT clone of an existing model.
    """
    parent_model = await get_model_by_id(parent_model_id)
    if not parent_model:
        return None

    # Determine baseline version logic (e.g., v1.0.0 -> v1.1.0-draft)
    # Since we don't have a complex version bumper here yet, let's keep it simple
    current_version = getattr(parent_model, "version", "v1.0.0")
    
    # Simple semantic version bump for draft (e.g. v1.1.0-draft)
    # We will just append '-draft' or parse and bump minor.
    # For now, let's use a generic 'timestamp' based draft version or fixed incremental.
    draft_version = f"{current_version.replace('-draft', '')}-draft-{datetime.now().strftime('%Y%m%d%H%M')}"

    parent_dict = parent_model.model_dump()
    parent_dict["id"] = str(uuid.uuid4())
    parent_dict.pop("created_at", None)
    parent_dict.pop("updated_at", None)
    
    # Overwrite v2 fields
    parent_dict["status"] = "DRAFT"
    parent_dict["version"] = draft_version
    parent_dict["parent_model_id"] = parent_model_id
    parent_dict["published_at"] = None
    
    # Create new model
    new_draft = VersionedExtractionModel(
        **parent_dict,
        created_at=_now(),
        updated_at=_now()
    )
    
    # Since we use existing models.save_model, we need to cast it to dict and upsert manually 
    # OR we can just use the cosmos container directly here. Let's use it directly to keep it clean.
    container = get_models_container()
    if container:
        await container.upsert_item(new_draft.model_dump())
        logger.info(f"[ModelsV2] Created DRAFT {new_draft.id} from {parent_model_id}")
        return new_draft
    return None


async def get_model_v2(model_id: str) -> Optional[VersionedExtractionModel]:
    """Get a model as V2 schema, filling in legacy gaps dynamically"""
    legacy_model = await get_model_by_id(model_id)
    if not legacy_model:
        return None
        
    m_dict = legacy_model.model_dump()
    if "status" not in m_dict:
        m_dict["status"] = "PUBLISHED"
        m_dict["version"] = "v1.0.0"
        
    return VersionedExtractionModel(**m_dict)


async def publish_model_v2(draft_model_id: str, changelog: str) -> Optional[VersionedExtractionModel]:
    """
    Promote a DRAFT to PUBLISHED. 
    If it has a parent_model_id, that parent gets ARCHIVED.
    """
    draft_model = get_model_v2(draft_model_id)
    if not draft_model or draft_model.status != "DRAFT":
        return None

    container = get_models_container()
    if not container:
        return None

    # Archive parent if exists
    if draft_model.parent_model_id:
        parent = get_model_v2(draft_model.parent_model_id)
        if parent:
            parent_dict = parent.model_dump()
            parent_dict["status"] = "ARCHIVED"
            await container.upsert_item(parent_dict)
            logger.info(f"[ModelsV2] Archived parent model {parent.id}")

    # Generate published version (remove -draft suffix)
    new_version = draft_model.version.split("-draft")[0]

    # Publish the draft
    draft_dict = draft_model.model_dump()
    draft_dict["status"] = "PUBLISHED"
    draft_dict["version"] = new_version
    draft_dict["published_at"] = _now()
    draft_dict["changelog"] = changelog
    draft_dict["updated_at"] = _now()

    await container.upsert_item(draft_dict)
    logger.info(f"[ModelsV2] Published model {draft_model_id}")
    
    return VersionedExtractionModel(**draft_dict)
