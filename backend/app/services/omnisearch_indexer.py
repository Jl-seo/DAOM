"""
Omni-Search Indexer - Asynchronously flattens JSON data for V2 Portal
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def _flatten_values(data: Any) -> str:
    """Recursively extract all string/number values from a nested JSON to form a searchable space-separated string"""
    if isinstance(data, dict):
        return " ".join(_flatten_values(v) for v in data.values())
    elif isinstance(data, list):
        return " ".join(_flatten_values(i) for i in data)
    elif data is not None:
        return str(data).strip()
    return ""

def process_searchable_text(extracted_data: Dict[str, Any]) -> str:
    """
    Takes an extracted_data dict and flattens it for the Omni-Search field: `searchable_text`.
    """
    if not extracted_data:
        return ""
    try:
        raw_text = _flatten_values(extracted_data)
        # Remove excess whitespace
        return " ".join(raw_text.split())
    except Exception as e:
        logger.error(f"[OmniSearchIndexer] Failed to flatten text: {e}")
        return ""
