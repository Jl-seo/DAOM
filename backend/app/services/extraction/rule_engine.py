import logging
from typing import Dict, Any, List

from app.services.dictionary_service import get_dictionary_service

logger = logging.getLogger(__name__)

class RuleEngine:

    async def apply_dictionary_normalization(self, raw_result: Dict[str, Any], model_id: str, dictionaries: List[str], fields: List[Any] = None) -> Dict[str, Any]:
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

        import asyncio
        
        # Pass 1: Collect unique (value, category) pairs to fetch
        pending_tasks = set()
        cache = {}

        for key, item in guide_extracted.items():
            if isinstance(item, dict) and "value" in item:
                val = item["value"]
                
                if isinstance(val, str):
                    dict_cat = field_dict_map.get(key)
                    if dict_cat and len(val.strip()) >= 2:
                        pending_tasks.add((val, dict_cat))
                
                elif isinstance(val, list):
                    for row in val:
                        if isinstance(row, dict):
                            for sub_key, sub_node in row.items():
                                if isinstance(sub_node, dict) and "value" in sub_node:
                                    sub_val = sub_node["value"]
                                    if isinstance(sub_val, str):
                                        sub_dict_cat = field_dict_map.get(f"{key}.{sub_key}")
                                        if sub_dict_cat and getattr(sub_val, "strip", lambda: "")() and len(sub_val.strip()) >= 2:
                                            pending_tasks.add((sub_val, sub_dict_cat))

        # Pass 2: Execute concurrent searches with semaphore
        if pending_tasks:
            # Sort for deterministic processing
            sorted_tasks = sorted(list(pending_tasks))
            
            # Use smaller semaphore to avoid 429 Too Many Requests
            sem = asyncio.Semaphore(5)
            
            async def _fetch(task_val, target_dictionary):
                best_match = None
                best_score = 0.0
                try:
                    async with sem:
                        matches = await dict_service.search(query=task_val, model_id=model_id, category=target_dictionary, top_k=1)
                        if matches and matches[0].score > 0.5:
                            best_match = matches[0]
                            best_score = matches[0].score
                except Exception as e:
                    logger.error(f"[RuleEngine] Dictionary search failed for val='{task_val}' in cat='{target_dictionary}': {e}")
                
                if best_match:
                    cache[(task_val, target_dictionary)] = {
                        "raw_value": task_val,
                        "normalized_code": best_match.code,
                        "dict_score": best_score,
                        "normalized_category": best_match.category
                    }
                else:
                    cache[(task_val, target_dictionary)] = {"raw_value": task_val, "normalized_code": None, "dict_score": 0.0}

            await asyncio.gather(*[_fetch(v, d) for v, d in sorted_tasks])

        # Pass 3: Apply the cached results
        for key, item in guide_extracted.items():
            if isinstance(item, dict) and "value" in item:
                val = item["value"]
                
                if isinstance(val, str):
                    dict_cat = field_dict_map.get(key)
                    if dict_cat:
                        norm = cache.get((val, dict_cat))
                        if norm and norm.get("normalized_code"):
                            item["raw_value"] = norm["raw_value"]
                            item["normalized_code"] = norm["normalized_code"]
                            item["dict_score"] = norm["dict_score"]
                
                elif isinstance(val, list):
                    for row in val:
                        if isinstance(row, dict):
                            for sub_key, sub_node in row.items():
                                if isinstance(sub_node, dict) and "value" in sub_node:
                                    sub_val = sub_node["value"]
                                    if isinstance(sub_val, str):
                                        sub_dict_cat = field_dict_map.get(f"{key}.{sub_key}")
                                        if sub_dict_cat:
                                            norm = cache.get((sub_val, sub_dict_cat))
                                            if norm and norm.get("normalized_code"):
                                                sub_node["raw_value"] = norm["raw_value"]
                                                sub_node["normalized_code"] = norm["normalized_code"]
                                                sub_node["dict_score"] = norm["dict_score"]

        raw_result["guide_extracted"] = guide_extracted
        return raw_result

    async def apply_vibe_dictionary(self, normalized_result: Dict[str, Any], model_id: str) -> Dict[str, Any]:
        """
        Step 2.5: Normalization Engine - Deterministically replaces raw values with standard values
        if they match a Vibe Dictionary entry that is verified (`is_verified == True`).
        """
        if not model_id:
            return normalized_result
        
        from app.db.cosmos import get_vibe_dictionary_container
        vibe_container = get_vibe_dictionary_container()
        if not vibe_container:
            return normalized_result

        # Fetch all verified vibe dictionary entries for this model
        query = "SELECT * FROM c WHERE c.model_id = @model_id AND c.is_verified = true"
        parameters = [{"name": "@model_id", "value": model_id}]
        
        try:
            entries = [v async for v in vibe_container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True)]
        except Exception as e:
            logger.error(f"[RuleEngine] Failed to fetch Vibe Dictionary entries: {e}")
            entries = []

        if not entries:
            return normalized_result

        # Build a fast lookup map: { "field_name": { "raw_val": "standard_val" } }
        reference_data = {}
        for entry in entries:
            field = entry.get("field_name")
            raw_val = entry.get("raw_val")
            standard_val = entry.get("value")
            
            if not field or not raw_val or not standard_val:
                continue
                
            if field not in reference_data:
                reference_data[field] = {}
            reference_data[field][raw_val] = standard_val

        guide_extracted = normalized_result.get("guide_extracted", {})
        if not isinstance(guide_extracted, dict):
            return normalized_result

        def _apply_dict(cell: Any, field_name: str) -> Any:
            if not isinstance(cell, dict) or "value" not in cell:
                return cell

            raw_val = cell.get("value")
            if not isinstance(raw_val, str) or not raw_val:
                return cell

            # Check if this field has dictionary entries in reference_data
            field_dict = reference_data.get(field_name, {})
            
            # Check if the exact raw_val is in the dictionary (we already filtered for is_verified=true)
            standard_val = field_dict.get(raw_val)
            if standard_val:
                cell["value"] = standard_val
                cell["_modifier"] = "Vibe Dictionary" # Tag for UI badge
                if "raw_value" not in cell:
                    cell["raw_value"] = raw_val       # Keep original for tracing
            
            return cell

        def _process_recursive(data: Any) -> Any:
            if isinstance(data, dict):
                processed = {}
                for key, node in data.items():
                    if isinstance(node, dict) and "value" in node:
                        if isinstance(node["value"], list):
                            # It's an array of rows
                            processed_rows = []
                            for row in node["value"]:
                                processed_rows.append(_process_recursive(row))
                            processed_node = dict(node)
                            processed_node["value"] = processed_rows
                            processed[key] = processed_node
                        else:
                            # It's a leaf cell
                            processed[key] = _apply_dict(dict(node), key)
                    elif isinstance(node, dict):
                        processed[key] = _process_recursive(node)
                    else:
                        processed[key] = node
                return processed
            elif isinstance(data, list):
                return [_process_recursive(item) for item in data]
            return data

        # Apply to guide_extracted tree
        normalized_result["guide_extracted"] = _process_recursive(guide_extracted)
        return normalized_result

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
