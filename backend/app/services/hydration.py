"""
Centralized Blob Hydration Utilities
=====================================
Single source of truth for hydrating Blob-offloaded fields from Cosmos DB.
All API endpoints that return preview_data or debug_data MUST use these helpers.

Offloading pattern (see extraction_jobs.py update_job):
  When payload > 1.5MB, heavy fields are replaced with:
    {"source": "blob_storage", "blob_path": "jobs/<id>/<field>.json"}
  or for top-level:
    {"_preview_blob_path": "jobs/<id>/preview.json"}

This module reverses that process before returning data to the frontend.
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Fields within preview_data that may be offloaded to Blob Storage
OFFLOADABLE_PREVIEW_FIELDS = [
    "raw_content",
    "_beta_parsed_content",
    "_beta_ref_map",
    "raw_tables",
    "guide_extracted",
    "raw_extracted",
]


async def hydrate_preview_data(preview_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Hydrate a preview_data dict by restoring any Blob-offloaded fields.
    
    Handles:
    1. Top-level offload: {"_preview_blob_path": "..."} → full preview
    2. Per-field offload: {"raw_content": {"source": "blob_storage", "blob_path": "..."}} → actual content
    
    Returns the hydrated dict (mutated in-place for per-field, replaced for top-level).
    """
    if not preview_data or not isinstance(preview_data, dict):
        return preview_data

    from app.services.storage import load_json_from_blob

    # 1. Top-level hydration (entire preview_data offloaded)
    if preview_data.get("_preview_blob_path"):
        try:
            full_preview = await load_json_from_blob(preview_data["_preview_blob_path"])
            if full_preview:
                preview_data = full_preview
        except Exception as e:
            logger.error(f"[Hydration] Failed to hydrate top-level preview from blob: {e}")

    # 2. Per-field hydration (individual heavy fields offloaded)
    for field_key in OFFLOADABLE_PREVIEW_FIELDS:
        field_val = preview_data.get(field_key)
        if isinstance(field_val, dict) and field_val.get("source") == "blob_storage" and field_val.get("blob_path"):
            try:
                hydrated = await load_json_from_blob(field_val["blob_path"])
                if hydrated is not None:
                    preview_data[field_key] = hydrated
                    logger.debug(f"[Hydration] Restored {field_key} from blob")
            except Exception as e:
                logger.error(f"[Hydration] Failed to hydrate {field_key} from blob ({field_val.get('blob_path')}): {e}")

    # 3. Handle sub_documents which is a list containing the offloaded dict
    sub_docs = preview_data.get("sub_documents")
    if isinstance(sub_docs, list) and len(sub_docs) == 1 and sub_docs[0].get("source") == "blob_storage":
        try:
            hydrated_sub = await load_json_from_blob(sub_docs[0]["blob_path"])
            if hydrated_sub is not None:
                preview_data["sub_documents"] = hydrated_sub
                logger.debug(f"[Hydration] Restored sub_documents from blob")
        except Exception as e:
            logger.error(f"[Hydration] Failed to hydrate sub_documents from blob ({sub_docs[0].get('blob_path')}): {e}")

    return preview_data


async def hydrate_debug_data(debug_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Hydrate debug_data dict by restoring Blob-offloaded content.
    
    Handles two patterns:
    1. {"_debug_blob_path": "..."} (extraction_preview.py pattern)
    2. {"source": "blob_storage", "raw_data_blob_path": "..."} (extraction/jobs.py pattern)
    """
    if not debug_data or not isinstance(debug_data, dict):
        return debug_data

    from app.services.storage import load_json_from_blob

    # Pattern 1: _debug_blob_path
    blob_path = debug_data.get("_debug_blob_path")
    # Pattern 2: raw_data_blob_path (extraction/jobs.py style)
    if not blob_path and debug_data.get("source") == "blob_storage":
        blob_path = debug_data.get("raw_data_blob_path")

    if blob_path:
        try:
            full_debug = await load_json_from_blob(blob_path)
            if full_debug:
                debug_data = full_debug
        except Exception as e:
            logger.error(f"[Hydration] Failed to hydrate debug_data from blob ({blob_path}): {e}")

    return debug_data


async def hydrate_extracted_data(extracted_data: Optional[Any]) -> Optional[Any]:
    """
    Hydrate extracted_data by restoring Blob-offloaded content.
    Handles the pattern: {"source": "blob_storage", "blob_path": "..."}
    """
    if not extracted_data or not isinstance(extracted_data, dict):
        return extracted_data

    from app.services.storage import load_json_from_blob

    if extracted_data.get("source") == "blob_storage" and extracted_data.get("blob_path"):
        blob_path = extracted_data.get("blob_path")
        try:
            full_extracted = await load_json_from_blob(blob_path)
            if full_extracted:
                return full_extracted
        except Exception as e:
            logger.error(f"[Hydration] Failed to hydrate extracted_data from blob ({blob_path}): {e}")

    return extracted_data
