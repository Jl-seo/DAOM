from typing import Any, Dict, List, Set, Union
from app.schemas.model import _BaseExtractionModel

def _get_pii_paths(model: _BaseExtractionModel) -> Set[str]:
    """Extract paths to PII fields from the model schema."""
    pii_paths = set()
    for field in model.fields:
        if getattr(field, "is_pii", False):
            # Top-level field: path is just the key
            pii_paths.add(field.key)
            
        if field.sub_fields:
            for sub in field.sub_fields:
                if sub.get("is_pii", False):
                    # Sub-field within a table/array (or any nested structure).
                    # We represent array indices with a wildcard '*'
                    pii_paths.add(f"{field.key}.*.{sub.get('key')}")
    return pii_paths

def mask_pii_data(data: Any, model: _BaseExtractionModel) -> Any:
    """Recursively mask fields defined as is_pii in the model schema using path matching."""
    if not data or not model:
        return data

    pii_paths = _get_pii_paths(model)
    
    if not pii_paths:
        return data

    return _recursively_mask_path(data, pii_paths, current_path=[])

def _recursively_mask_path(data: Any, pii_paths: Set[str], current_path: List[str]) -> Any:
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            path_parts = current_path + [k]
            path_str = ".".join(path_parts)
            
            # Check if this exact path is in the pii_paths set
            if path_str in pii_paths and isinstance(v, str) and v:
                new_data[k] = "***"
            else:
                new_data[k] = _recursively_mask_path(v, pii_paths, path_parts)
        return new_data
    elif isinstance(data, list):
        new_list = []
        for i, item in enumerate(data):
            # For lists, we use '*' in the path to represent any index
            path_parts = current_path + ["*"]
            new_list.append(_recursively_mask_path(item, pii_paths, path_parts))
        return new_list
    else:
        return data
