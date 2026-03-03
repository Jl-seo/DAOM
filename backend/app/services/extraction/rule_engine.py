import logging
from typing import Dict, Any, List

from app.services.dictionary_service import get_dictionary_service

logger = logging.getLogger(__name__)

class RuleEngine:
    async def apply_dictionary_normalization(self, raw_result: Dict[str, Any], dictionaries: List[str]) -> Dict[str, Any]:
        """
        Step 2: Normalizes raw extracted texts using active dictionary categories.
        Converts {"pol": "Busan"} -> {"pol": {"raw_value": "Busan", "normalized_code": "KRPUS", "dict_score": 0.98}}
        Only wraps fields if a dictionary is active and a match is found.
        """
        if not dictionaries:
            return raw_result

        guide_extracted = raw_result.get("guide_extracted", {})
        if not isinstance(guide_extracted, dict):
            return raw_result

        dict_service = get_dictionary_service()
        if not dict_service.is_available:
            logger.warning("[RuleEngine] DictionaryService unavailable. Skipping normalization.")
            return raw_result

        # Helper to recursively normalize
        # If we know mapping between field and dictionary, it would be exact, 
        # but for now we search all active dictionaries for any string value that looks like it needs mapping.
        # Actually, if we just search all active dictionaries for string field values, it might be slow for every single text string.
        # Instead, we will wrap *all* simple fields into the new dict structure, 
        # and attempt to query dictionaries if the string length is reasonable.
        # A more robust enterprise approach: only fields that have a specific mapping rule, but user wants it to be 'magic' or based on active dictionaries.
        # Let's search all dictionaries in parallel for top-level fields for now.

        async def _normalize_value(val: str) -> Dict[str, Any]:
            if not isinstance(val, str) or len(val.strip()) < 2:
                return {"raw_value": val, "normalized_code": None, "dict_score": 0.0}
            
            best_match = None
            best_score = 0.0

            # Search across all active dictionary categories for this model
            for cat in dictionaries:
                try:
                    matches = await dict_service.search(query=val, category=cat, top_k=1)
                    if matches and matches[0].score > best_score:
                        best_match = matches[0]
                        best_score = matches[0].score
                except Exception as e:
                    logger.error(f"[RuleEngine] Dictionary search failed for val='{val}' in cat='{cat}': {e}")
                    pass
            
            if best_match and best_score > 0.5: # arbitrary threshold for now
                return {
                    "raw_value": val,
                    "normalized_code": best_match.code,
                    "dict_score": best_score,
                    "normalized_category": best_match.category
                }
            
            return {"raw_value": val, "normalized_code": None, "dict_score": 0.0}
        
        async def _process_item(item):
            # item is {"value": "...", "confidence": ...}
            if isinstance(item, dict) and "value" in item:
                val = item["value"]
                if isinstance(val, str):
                    norm = await _normalize_value(val)
                    item["raw_value"] = norm["raw_value"]
                    item["normalized_code"] = norm["normalized_code"]
                    item["dict_score"] = norm["dict_score"]
                elif isinstance(val, list):
                    # For array/table fields
                    for row in val:
                        if isinstance(row, dict):
                            for k, v in row.items():
                                if isinstance(v, str):
                                    norm = await _normalize_value(v)
                                    # Inside array, we might not wrap everything to avoid bloat, but let's be consistent or just add normalized_code_k
                                    # Let's wrap it inside the dictionary row.
                                    row[k] = {
                                        "raw_value": v,
                                        "normalized_code": norm["normalized_code"],
                                        "dict_score": norm["dict_score"]
                                    }
            return item

        # Apply to all top-level fields
        for key, item in guide_extracted.items():
            guide_extracted[key] = await _process_item(item)

        raw_result["guide_extracted"] = guide_extracted
        return raw_result

    def apply_validation_rules(self, normalized_result: Dict[str, Any], reference_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 3: Applies cross-field validation rules and composite unique constraints.
        reference_data format expected:
        {
            "validation_rules": [
                {"type": "block", "condition": "...", "message": "..."}
            ],
            "unique_constraints": [
                {"target_array": "shipping_charges", "unique_keys": ["container_no", "charge_code"]}
            ]
        }
        """
        if not reference_data:
            return normalized_result

        guide_extracted = normalized_result.get("guide_extracted", {})
        
        # 1. Unique Constraints (Composite Keys)
        unique_constraints = reference_data.get("unique_constraints", [])
        for constraint in unique_constraints:
            target_array = constraint.get("target_array")
            keys = constraint.get("unique_keys", [])
            if not target_array or not keys:
                continue
            
            array_data = guide_extracted.get(target_array, {}).get("value")
            if not isinstance(array_data, list):
                continue

            seen_keys = set()
            for idx, row in enumerate(array_data):
                if not isinstance(row, dict):
                    continue
                
                # Build composite key
                # row[k] could be a primitive or a dict {"raw_value": "...", "normalized_code": "..."}
                composite_parts = []
                for k in keys:
                    v = row.get(k)
                    if isinstance(v, dict):
                        # Use normalized_code if available, else raw_value
                        part = v.get("normalized_code") or v.get("raw_value") or ""
                    else:
                        part = str(v) if v is not None else ""
                    composite_parts.append(str(part).strip().lower())
                
                composite_str = "|".join(composite_parts)
                
                if composite_str in seen_keys:
                    # Mark row as duplicate
                    if "_row_warnings" not in row:
                        row["_row_warnings"] = []
                    row["_row_warnings"].append(f"중복된 값이 감지되었습니다. (고유 키: {', '.join(keys)})")
                    row["_is_duplicate"] = True
                else:
                    seen_keys.add(composite_str)

        # 2. Cross-Field Logic (If-Then)
        # To be implemented fully with a safe eval or a typed rule parser in Phase 2
        # For now, we stub it to allow UI testing
        validation_rules = reference_data.get("validation_rules", [])
        for rule in validation_rules:
            # We can implement a simple parser later.
            pass

        normalized_result["guide_extracted"] = guide_extracted
        return normalized_result


rule_engine = RuleEngine()
