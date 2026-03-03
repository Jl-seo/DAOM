import logging
from typing import Dict, Any, List

from app.services.dictionary_service import get_dictionary_service

logger = logging.getLogger(__name__)

class RuleEngine:
    async def apply_dictionary_normalization(self, raw_result: Dict[str, Any], dictionaries: List[str], fields: List[Any] = None) -> Dict[str, Any]:
        """
        Step 2: Normalizes raw extracted texts using active dictionary categories mapped at the field-level.
        Only wraps fields if a dictionary is mapped in the field schema and a match is found.
        """
        # If no fields schema is provided, we no longer do global search to prevent false positives.
        if not fields:
            # Note: For backward compatibility with tests/legacy, if you want global search you could check dictionaries. 
            # But Enterprise spec says 1:1 mapping only.
            return raw_result

        guide_extracted = raw_result.get("guide_extracted", {})
        if not isinstance(guide_extracted, dict):
            return raw_result

        dict_service = get_dictionary_service()
        if not dict_service.is_available:
            logger.warning("[RuleEngine] DictionaryService unavailable. Skipping normalization.")
            return raw_result

        # Build a lookup map of field_key -> dictionary_category
        # Handle both top-level fields and sub_fields
        field_dict_map = {}
        for f in fields:
            key = getattr(f, "key", None)
            dict_cat = getattr(f, "dictionary", None)
            if key and dict_cat:
                field_dict_map[key] = dict_cat
            
            # Check for sub_fields in tables
            sub_fields = getattr(f, "sub_fields", None)
            if sub_fields and isinstance(sub_fields, list):
                for sub in sub_fields:
                    sub_key = sub.get("key")
                    sub_dict = sub.get("dictionary")
                    if sub_key and sub_dict:
                        field_dict_map[f"{key}.{sub_key}"] = sub_dict

        if not field_dict_map:
            # Early exit if no fields have dictionary mapping
            return raw_result

        async def _normalize_value(val: str, target_dictionary: str) -> Dict[str, Any]:
            if not isinstance(val, str) or len(val.strip()) < 2:
                return {"raw_value": val, "normalized_code": None, "dict_score": 0.0}
            
            best_match = None
            best_score = 0.0

            try:
                matches = await dict_service.search(query=val, category=target_dictionary, top_k=1)
                if matches and matches[0].score > best_score:
                    best_match = matches[0]
                    best_score = matches[0].score
            except Exception as e:
                logger.error(f"[RuleEngine] Dictionary search failed for val='{val}' in cat='{target_dictionary}': {e}")
                pass
            
            if best_match and best_score > 0.5: # arbitrary threshold for now
                return {
                    "raw_value": val,
                    "normalized_code": best_match.code,
                    "dict_score": best_score,
                    "normalized_category": best_match.category
                }
            
            return {"raw_value": val, "normalized_code": None, "dict_score": 0.0}

        # Apply to all top-level fields
        for key, item in guide_extracted.items():
            if isinstance(item, dict) and "value" in item:
                val = item["value"]
                
                # Top level string
                if isinstance(val, str):
                    dict_cat = field_dict_map.get(key)
                    if dict_cat:
                        norm = await _normalize_value(val, dict_cat)
                        item["raw_value"] = norm["raw_value"]
                        item["normalized_code"] = norm["normalized_code"]
                        item["dict_score"] = norm["dict_score"]
                
                # Table / Array
                elif isinstance(val, list):
                    for row in val:
                        if isinstance(row, dict):
                            for sub_key, sub_val in row.items():
                                if isinstance(sub_val, str):
                                    # composite key for lookup: parentKey.subKey
                                    # Fallback to parentKey for table-level generic dictionary cascading
                                    sub_dict_cat = field_dict_map.get(f"{key}.{sub_key}") or field_dict_map.get(key)
                                    if sub_dict_cat:
                                        norm = await _normalize_value(sub_val, sub_dict_cat)
                                        row[sub_key] = {
                                            "raw_value": sub_val,
                                            "normalized_code": norm["normalized_code"],
                                            "dict_score": norm["dict_score"]
                                        }

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
