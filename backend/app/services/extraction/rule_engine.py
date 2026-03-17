import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def build_field_dict_map(fields: List[Any], dictionaries: List[str]) -> Dict[str, str]:
    """
    Build a lookup map of field_key -> dictionary_category.
    Handles both top-level fields and sub_fields in tables.
    
    Dictionary mapping comes ONLY from model schema:
    - field.dictionary (top-level)
    - sub_field.dictionary (table sub-fields)
    
    No auto-guessing by field name. If the model doesn't define
    a dictionary for a field, it won't get dictionary normalization.
    
    Returns: {"pol": "port", "Rate_List.pol": "port", ...}
    """
    field_dict_map = {}
    
    for f in (fields or []):
        key = getattr(f, "key", None) if not isinstance(f, dict) else f.get("key")
        dict_cat = getattr(f, "dictionary", None) if not isinstance(f, dict) else f.get("dictionary")
        
        if key and dict_cat:
            field_dict_map[key] = dict_cat
        
        # Sub-fields in tables
        sub_fields = (getattr(f, "sub_fields", None) if not isinstance(f, dict) else f.get("sub_fields")) or []
        if isinstance(sub_fields, list):
            for sub in sub_fields:
                sub_key = sub.get("key") if isinstance(sub, dict) else getattr(sub, "key", None)
                sub_dict = sub.get("dictionary") if isinstance(sub, dict) else getattr(sub, "dictionary", None)
                if sub_key and sub_dict:
                    field_dict_map[f"{key}.{sub_key}"] = sub_dict
    
    return field_dict_map


class RuleEngine:

    def apply_validation_rules(self, normalized_result: Dict[str, Any], reference_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 3: Applies cross-field validation rules and composite unique constraints.
        
        reference_data format:
        {
            "validation_rules": [
                {"type": "required", "field": "pol", "message": "POL is required"},
                {"type": "format", "field": "start_date", "pattern": "\\d{4}-\\d{2}-\\d{2}", "message": "..."},
                {"type": "value_check", "field": "currency", "allowed": ["USD","EUR","KRW"], "message": "..."},
                {"type": "cross_field", "condition": "pol != pod", "severity": "error", "message": "POL and POD must differ"},
                {"type": "value_check", "field": "20ft", "min": 0, "severity": "warning", "message": "..."}
            ],
            "unique_constraints": [
                {"target_array": "Rate_List", "unique_keys": ["pol", "pod", "container_type"]}
            ]
        }
        """
        if not reference_data:
            return normalized_result

        guide_extracted = normalized_result.get("guide_extracted", {})
        warnings_list = normalized_result.get("_warnings", [])
        
        # ── 1. Unique Constraints (Composite Keys) ──
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
                
                composite_parts = []
                for k in keys:
                    v = row.get(k)
                    if isinstance(v, dict):
                        part = v.get("value") or v.get("normalized_code") or v.get("raw_value") or ""
                    else:
                        part = str(v) if v is not None else ""
                    composite_parts.append(str(part).strip().lower())
                
                composite_str = "|".join(composite_parts)
                
                if composite_str in seen_keys:
                    if "_row_warnings" not in row:
                        row["_row_warnings"] = []
                    row["_row_warnings"].append(f"중복된 값이 감지되었습니다. (고유 키: {', '.join(keys)})")
                    row["_is_duplicate"] = True
                else:
                    seen_keys.add(composite_str)

        # ── 2. Declarative Validation Rules ──
        import re
        validation_rules = reference_data.get("validation_rules", [])
        
        for rule in validation_rules:
            rule_type = rule.get("type")
            severity = rule.get("severity", "warning")
            message = rule.get("message", "Validation failed")
            field = rule.get("field")
            
            if rule_type == "required":
                # Check if a field has a non-empty value
                self._validate_field_values(
                    guide_extracted, field, severity, message, warnings_list,
                    check_fn=lambda v: v is not None and str(v).strip() != ""
                )
                
            elif rule_type == "format":
                # Check if a field matches a regex pattern
                pattern = rule.get("pattern")
                if not pattern:
                    continue
                compiled = re.compile(pattern)
                self._validate_field_values(
                    guide_extracted, field, severity, message, warnings_list,
                    check_fn=lambda v: v is None or str(v).strip() == "" or bool(compiled.match(str(v)))
                )
                
            elif rule_type == "value_check":
                # Check allowed values or numeric ranges
                allowed = rule.get("allowed")
                min_val = rule.get("min")
                max_val = rule.get("max")
                
                def _value_check(v):
                    if v is None or str(v).strip() == "":
                        return True  # Empty values skip (use "required" rule instead)
                    val_str = str(v).strip()
                    if allowed:
                        return val_str.upper() in [a.upper() for a in allowed]
                    if min_val is not None or max_val is not None:
                        try:
                            num = float(val_str.replace(",", ""))
                            if min_val is not None and num < min_val:
                                return False
                            if max_val is not None and num > max_val:
                                return False
                        except ValueError:
                            return True  # Non-numeric, skip range check
                    return True
                
                self._validate_field_values(
                    guide_extracted, field, severity, message, warnings_list,
                    check_fn=_value_check
                )
                
            elif rule_type == "cross_field":
                # Cross-field comparison (e.g., "pol != pod")
                condition = rule.get("condition", "")
                self._validate_cross_field(
                    guide_extracted, condition, severity, message, warnings_list
                )

        if warnings_list:
            normalized_result["_warnings"] = warnings_list
        normalized_result["guide_extracted"] = guide_extracted
        return normalized_result

    def _get_field_value(self, data: dict, field_key: str):
        """Extract a field's effective value from guide_extracted."""
        node = data.get(field_key)
        if node is None:
            return None
        if isinstance(node, dict):
            return node.get("value")
        return node

    def _validate_field_values(self, guide_extracted: dict, field: str, 
                                severity: str, message: str, warnings_list: list,
                                check_fn):
        """Validate a field across top-level and table rows."""
        if not field:
            return
        
        # Check if field is in a table (e.g., "Rate_List.pol")
        parts = field.split(".", 1) if "." in field else [field]
        
        if len(parts) == 1:
            # Top-level field
            val = self._get_field_value(guide_extracted, field)
            if not check_fn(val):
                warnings_list.append({
                    "field": field,
                    "severity": severity,
                    "message": message.replace("{value}", str(val) if val else ""),
                    "value": str(val) if val else None
                })
        else:
            # Table sub-field: parts[0] = table key, parts[1] = sub_field key
            table_key, sub_key = parts
            table_node = guide_extracted.get(table_key, {})
            rows = table_node.get("value") if isinstance(table_node, dict) else None
            if isinstance(rows, list):
                for idx, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    val = self._get_field_value(row, sub_key)
                    if not check_fn(val):
                        if "_row_warnings" not in row:
                            row["_row_warnings"] = []
                        row["_row_warnings"].append(message.replace("{value}", str(val) if val else ""))

    def _validate_cross_field(self, guide_extracted: dict, condition: str,
                               severity: str, message: str, warnings_list: list):
        """
        Evaluate simple cross-field conditions like "pol == pod" or "start_date < end_date".
        Supports operators: ==, !=, <, >, <=, >=
        """
        import re as _re
        match = _re.match(r'^\s*(\w+)\s*(==|!=|<=|>=|<|>)\s*(\w+)\s*$', condition)
        if not match:
            logger.warning(f"[RuleEngine] Invalid cross-field condition: '{condition}'")
            return
        
        left_key, operator, right_key = match.groups()
        
        # Try top-level first
        left_val = self._get_field_value(guide_extracted, left_key)
        right_val = self._get_field_value(guide_extracted, right_key)
        
        if left_val is not None and right_val is not None:
            if self._compare(left_val, operator, right_val) is False:
                warnings_list.append({
                    "field": f"{left_key}, {right_key}",
                    "severity": severity,
                    "message": message,
                    "condition": condition
                })
            return
        
        # Try in table rows (both fields in same table)
        for key, node in guide_extracted.items():
            if isinstance(node, dict) and isinstance(node.get("value"), list):
                for idx, row in enumerate(node["value"]):
                    if not isinstance(row, dict):
                        continue
                    lv = self._get_field_value(row, left_key)
                    rv = self._get_field_value(row, right_key)
                    if lv is not None and rv is not None:
                        if self._compare(lv, operator, rv) is False:
                            if "_row_warnings" not in row:
                                row["_row_warnings"] = []
                            row["_row_warnings"].append(message)

    @staticmethod
    def _compare(left, operator: str, right) -> bool:
        """Safe comparison of two values."""
        left_s = str(left).strip() if left is not None else ""
        right_s = str(right).strip() if right is not None else ""
        
        if operator == "==":
            return left_s.lower() == right_s.lower()
        elif operator == "!=":
            return left_s.lower() != right_s.lower()
        
        # Numeric comparisons
        try:
            left_n = float(left_s.replace(",", ""))
            right_n = float(right_s.replace(",", ""))
        except (ValueError, AttributeError):
            return True  # Can't compare non-numeric, skip
        
        if operator == "<":
            return left_n < right_n
        elif operator == ">":
            return left_n > right_n
        elif operator == "<=":
            return left_n <= right_n
        elif operator == ">=":
            return left_n >= right_n
        return True


rule_engine = RuleEngine()
