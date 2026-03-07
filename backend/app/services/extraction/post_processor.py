import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def apply_post_processing(guide_extracted: Dict[str, Any], rules: List[Any], fields_def: List[Any]) -> Dict[str, Any]:
    """
    Stage 3: Deterministic Rule-Based Post-Processing.
    Applies Action Enums (e.g., SPLIT_CURRENCY) to the extracted data.
    """
    if not rules:
        return guide_extracted

    logger.info(f"[PostProcessor] Applying {len(rules)} rule(s) to extracted data.")
    
    # Group rules by target_field for fast lookup
    rules_by_target = {}
    for rule in rules:
        target = rule.target_field
        if target not in rules_by_target:
            rules_by_target[target] = []
        rules_by_target[target].append(rule)

    _traverse_and_apply(guide_extracted, rules_by_target)
    
    return guide_extracted

def _traverse_and_apply(data: Any, rules_by_target: Dict[str, list], parent_row: Dict[str, Any] = None):
    """
    Recursively traverse the guide_extracted payload.
    data format is usually {"value": "...", "confidence": 0.9} 
    or {"value": [{"Sub": {"value": "..."}}]}
    """
    if isinstance(data, dict):
        # Check if this data dict itself is a collection of fields (like a row)
        # e.g., the parent_row context
        
        for key, node in data.items():
            if isinstance(node, dict) and "value" in node:
                # 1. If it's a table array
                if isinstance(node["value"], list):
                    for row in node["value"]:
                        _traverse_and_apply(row, rules_by_target, parent_row=row)
                
                # 2. If it's a scalar value
                elif key in rules_by_target:
                    _apply_rules_to_field(key, node, rules_by_target[key], parent_row=data)
            
            elif isinstance(node, dict):
                # Dig deeper just in case
                _traverse_and_apply(node, rules_by_target, parent_row=data)

def _apply_rules_to_field(field_key: str, node: Dict[str, Any], rules: list, parent_row: Dict[str, Any]):
    val = str(node.get("value", ""))
    if not val.strip():
        return
        
    for rule in rules:
        action = rule.action.value if hasattr(rule.action, "value") else str(rule.action)
        
        if action == "split_currency":
            # Match "USD 1602" or "1602 USD"
            # Return Rate to current node, and set Currency node if exists in parent_row
            m1 = re.search(r'(USD|EUR|KRW|JPY|CNY|GBP)\s*([\d\.,]+)', val, re.IGNORECASE)
            m2 = re.search(r'([\d\.,]+)\s*(USD|EUR|KRW|JPY|CNY|GBP)', val, re.IGNORECASE)
            
            num, cur = None, None
            if m1:
                cur, num = m1.group(1).upper(), m1.group(2)
            elif m2:
                num, cur = m2.group(1), m2.group(2).upper()
                
            if num and cur:
                # Update current Rate field
                node["value"] = num
                node["_modifier"] = "Rule: Split Currency"
                node["_modified_from"] = val
                
                # Attempt to find sibling "Currency" field to populate
                if parent_row:
                    curr_key = None
                    # Simple heuristic: find a key containing "currency" or "curr"
                    for pk in parent_row.keys():
                        if "curr" in pk.lower() or "통화" in pk:
                            curr_key = pk
                            break
                    if curr_key and curr_key in parent_row:
                        if not parent_row[curr_key].get("value"):
                            parent_row[curr_key]["value"] = cur
                            parent_row[curr_key]["_modifier"] = "Rule: Split Currency"
                
                val = num # update local val for next rules

        elif action == "extract_digits":
            new_val = re.sub(r'[^\d\.]', '', val)
            if new_val != val:
                node["value"] = new_val
                node["_modifier"] = "Rule: Extract Digits"
                node["_modified_from"] = val
                val = new_val
                
        elif action == "uppercase":
            new_val = val.upper()
            if new_val != val:
                node["value"] = new_val
                node["_modifier"] = "Rule: Uppercase"
                node["_modified_from"] = val
                val = new_val
                
        elif action == "date_format_iso":
            # Very basic date normalizer
            # Replace . or / with -
            new_val = re.sub(r'[\./]', '-', val)
            if new_val != val:
                node["value"] = new_val
                node["_modifier"] = "Rule: Date ISO Format"
                node["_modified_from"] = val
                val = new_val
