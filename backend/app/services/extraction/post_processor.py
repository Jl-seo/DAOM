import re
import fnmatch
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Guard patterns for extract_digits
# ──────────────────────────────────────────────
_DATE_GUARD = re.compile(r'\d{4}[-/\.]\d{1,2}[-/\.]\d{1,4}|\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}')
_EQUIPMENT_GUARD = re.compile(r'^\d{2}(GP|HC|DC|RF|OT|FR|TK|NOR)\b', re.IGNORECASE)
_PORT_GUARD = re.compile(r'^[A-Z]{2,5}$')
_SERVICE_MODE_GUARD = re.compile(r'^(CY|CFS|SD|DR)[/-](CY|CFS|SD|DR)$', re.IGNORECASE)


def _is_protected_value(val: str) -> bool:
    """Return True if the value should NOT be digit-extracted (would destroy data)."""
    v = val.strip()
    if _DATE_GUARD.search(v):
        return True
    if _EQUIPMENT_GUARD.match(v):
        return True
    if _PORT_GUARD.match(v):
        return True
    if _SERVICE_MODE_GUARD.match(v):
        return True
    return False


# ──────────────────────────────────────────────
# Wildcard path matching
# ──────────────────────────────────────────────

def _match_rules(path_key: str, rules_by_target: Dict[str, list]) -> list:
    """Match rules using 3 strategies: exact → basename → wildcard.

    Examples:
        path_key = "Basic_Rate_List.POL"
        - exact match:    "Basic_Rate_List.POL" in rules
        - basename match: "POL" in rules
        - wildcard match: "*.POL" or "Basic_Rate_List.*" in rules
    """
    # 1. Exact match
    if path_key in rules_by_target:
        return rules_by_target[path_key]

    # 2. Basename match (last segment of dotted path)
    # Only if path is nested (contains dot) — prevents colliding with top-level scalar fields
    if "." in path_key:
        basename = path_key.rsplit(".", 1)[-1]
        if basename in rules_by_target:
            return rules_by_target[basename]

    # 3. fnmatch wildcard
    for target, rules in rules_by_target.items():
        if "*" in target and fnmatch.fnmatch(path_key, target):
            return rules

    return []


# ──────────────────────────────────────────────
# Schema-driven sibling resolution
# ──────────────────────────────────────────────

def _find_currency_key(parent_row: Dict[str, Any], fields_def: Optional[List[Any]] = None) -> Optional[str]:
    """Find sibling currency field key using schema first, heuristic fallback.

    Schema-driven: look for sub_field with dictionary=="currency" or type=="currency".
    Heuristic fallback: key containing "curr" or "통화".
    """
    # Strategy 1: Schema-driven (if fields_def provided)
    if fields_def:
        for fd in fields_def:
            subs = None
            if hasattr(fd, 'sub_fields'):
                subs = fd.sub_fields
            elif isinstance(fd, dict):
                subs = fd.get("sub_fields")
            if not subs:
                continue
            for sf in (subs or []):
                sf_dict = sf if isinstance(sf, dict) else (sf.model_dump() if hasattr(sf, 'model_dump') else vars(sf))
                if sf_dict.get("dictionary") == "currency" or sf_dict.get("type") == "currency":
                    key = sf_dict.get("key", "")
                    if key in parent_row:
                        return key

    # Strategy 2: Heuristic fallback
    for pk in parent_row.keys():
        pk_lower = pk.lower()
        if "curr" in pk_lower or "통화" in pk_lower or "currency" == pk_lower:
            return pk

    return None


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def apply_post_processing(guide_extracted: Dict[str, Any], rules: List[Any], fields_def: List[Any]) -> Dict[str, Any]:
    """
    Stage 3: Deterministic Rule-Based Post-Processing.
    Applies Action Enums (e.g., SPLIT_CURRENCY) to the extracted data.
    """
    if not rules:
        return guide_extracted

    logger.info(f"[PostProcessor] Applying {len(rules)} rule(s) to extracted data.")

    # Group rules by target_field for fast lookup
    rules_by_target: Dict[str, list] = {}
    for rule in rules:
        target = rule.target_field
        if target not in rules_by_target:
            rules_by_target[target] = []
        rules_by_target[target].append(rule)

    _traverse_and_apply(guide_extracted, rules_by_target, fields_def=fields_def)

    return guide_extracted


def _traverse_and_apply(
    data: Any,
    rules_by_target: Dict[str, list],
    parent_row: Dict[str, Any] = None,
    current_path: str = "",
    fields_def: Optional[List[Any]] = None
):
    """
    Recursively traverse the guide_extracted payload.
    data format is usually {"value": "...", "confidence": 0.9}
    or {"value": [{"Sub": {"value": "..."}}]}
    """
    if isinstance(data, dict):
        for key, node in data.items():
            path_key = f"{current_path}.{key}" if current_path else key

            if isinstance(node, dict) and "value" in node:
                # 1. If it's a table array
                if isinstance(node["value"], list):
                    new_rows = []
                    for row in node["value"]:
                        # FIRST: Recurse into the row
                        _traverse_and_apply(row, rules_by_target, parent_row=row,
                                            current_path=path_key, fields_def=fields_def)
                        
                        # SECOND: Handle SPLIT_DELIMITER
                        # We only handle one split rule per row at a time to prevent combinatorial explosion
                        splits_generated = False
                        for sub_key, sub_node in row.items():
                            if isinstance(sub_node, dict) and "value" in sub_node and isinstance(sub_node["value"], str):
                                sub_path_key = f"{path_key}.{sub_key}"
                                matched_rules = _match_rules(sub_path_key, rules_by_target)
                                if matched_rules:
                                    has_split_rule = any(
                                        (getattr(r.action, "value", str(r.action)) == "split_delimiter")
                                        for r in matched_rules
                                    )
                                    if has_split_rule:
                                        val = sub_node["value"]
                                        if not val:
                                            continue
                                        # Split by semicolon, slash, or comma
                                        parts = [p.strip() for p in re.split(r'[;/,]', val) if p.strip()]
                                        if len(parts) > 1:
                                            import copy
                                            for p in parts:
                                                new_row = copy.deepcopy(row)
                                                new_row[sub_key]["value"] = p
                                                new_row[sub_key]["_modifier"] = "Rule: Split Delimiter"
                                                new_row[sub_key]["_modified_from"] = val
                                                new_rows.append(new_row)
                                            splits_generated = True
                                            break

                        if not splits_generated:
                            new_rows.append(row)

                    # Update the table array with potentially expanded rows
                    node["value"] = new_rows

                # 2. If it's a scalar value — use wildcard matching
                else:
                    matched_rules = _match_rules(path_key, rules_by_target)
                    if matched_rules:
                        _apply_rules_to_field(path_key, node, matched_rules,
                                              parent_row=data, fields_def=fields_def)

            elif isinstance(node, dict):
                # Dig deeper
                _traverse_and_apply(node, rules_by_target, parent_row=data,
                                    current_path=path_key, fields_def=fields_def)


def _apply_rules_to_field(
    field_key: str,
    node: Dict[str, Any],
    rules: list,
    parent_row: Dict[str, Any],
    fields_def: Optional[List[Any]] = None
):
    val = str(node.get("value", ""))
    if not val.strip():
        return

    for rule in rules:
        action = rule.action.value if hasattr(rule.action, "value") else str(rule.action)

        if action == "split_currency":
            # Match "USD 1602" or "1602 USD"
            m1 = re.search(r'(USD|EUR|KRW|JPY|CNY|GBP)\s*([\d\.,]+)', val, re.IGNORECASE)
            m2 = re.search(r'([\d\.,]+)\s*(USD|EUR|KRW|JPY|CNY|GBP)', val, re.IGNORECASE)

            num, cur = None, None
            if m1:
                cur, num = m1.group(1).upper(), m1.group(2)
            elif m2:
                num, cur = m2.group(1), m2.group(2).upper()

            if num and cur:
                node["value"] = num
                node["_modifier"] = "Rule: Split Currency"
                node["_modified_from"] = val

                # Schema-driven sibling currency resolution
                if parent_row:
                    curr_key = _find_currency_key(parent_row, fields_def)
                    if curr_key and curr_key in parent_row:
                        cell = parent_row[curr_key]
                        if isinstance(cell, dict) and not cell.get("value"):
                            cell["value"] = cur
                            cell["_modifier"] = "Rule: Split Currency"

                val = num

        elif action == "extract_digits":
            # Guard: skip if value would be destroyed by digit extraction
            if _is_protected_value(val):
                logger.debug(f"[PostProcessor] Skipping extract_digits for protected value: '{val}'")
                continue

            new_val = re.sub(r'[^\d\.]', '', val)
            if new_val and new_val != val:
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

        elif action in ("date_format_iso", "normalize_date_separator"):
            # Guard: skip pure numeric values (no separators) — dateutil would parse "1480" as a date
            # But don't skip if it looks like a date with separators like "2025.1.2"
            stripped = val.strip()
            if not _DATE_GUARD.search(stripped) and re.match(r'^[\d,]+$', stripped):
                continue

            # Try real ISO parsing first, fallback to separator normalization
            new_val = val
            try:
                from dateutil.parser import parse as dateparse
                parsed = dateparse(val, dayfirst=False)
                new_val = parsed.strftime("%Y-%m-%d")
            except Exception:
                # Fallback: simple separator normalization
                new_val = re.sub(r'[\./]', '-', val)

            if new_val != val:
                node["value"] = new_val
                node["_modifier"] = "Rule: Date ISO Format"
                node["_modified_from"] = val
                val = new_val
