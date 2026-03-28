"""
Transform Engine — Post-Extraction Row Expansion

Applies transform rules to extracted data:
- Group code expansion: e.g., "AS1" → ["Ningbo", "Qingdao", "Shanghai", ...]
- Splits one row into N rows, one per expanded value
- Supports multiple expand fields per rule (POL × POD = cartesian product)

Rule format:
{
    "name": "AS1 Port Group",
    "target_field": "shipping_rates_extracted",   # which table to apply to
    "match_field": "POL_NAME",                    # field to check
    "match_value": "AS1",                         # value to match (or "*" for all)
    "expand_field": "POL_NAME",                   # field to expand (usually same as match_field)
    "expand_values": ["Ningbo", "Qingdao", "Shanghai", "Yantian", "Hong Kong", "Pusan", "Kaohsiung"],
    "expand_codes": ["CNNBO", "CNQND", "CNSHG", "CNYYT", "HKHKG", "KRPUS", "TWKSG"],  # optional code field
    "code_field": "POL_CODE"  # optional: field to write the code to
}
"""
import logging
import copy
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TransformEngine:
    """Applies transform rules to extracted guide_extracted data."""

    @staticmethod
    def apply(guide_extracted: dict, rules: List[dict]) -> dict:
        """
        Apply all transform rules to guide_extracted and return modified data.
        Rules are applied sequentially — each rule's output feeds the next.
        """
        if not rules:
            return guide_extracted

        result = copy.deepcopy(guide_extracted)

        for rule in rules:
            if not isinstance(rule, dict):
                logger.warning(f"[TransformEngine] Expected rule to be a dict, got {type(rule)}")
                continue
            try:
                result = TransformEngine._apply_rule(result, rule)
            except Exception as e:
                logger.error(f"[TransformEngine] Rule '{rule.get('name', 'unnamed')}' failed: {e}")

        return result

    @staticmethod
    def _apply_rule(guide_extracted: dict, rule: dict) -> dict:
        """Apply a single transform rule."""
        rule_name = rule.get("name", "unnamed")
        target_field = rule.get("target_field")
        match_field = rule.get("match_field")
        match_value = rule.get("match_value")
        expand_field = rule.get("expand_field")
        expand_values = rule.get("expand_values", [])
        expand_codes = rule.get("expand_codes", [])
        code_field = rule.get("code_field")

        if not target_field or not expand_field or not expand_values:
            logger.warning(f"[TransformEngine] Rule '{rule_name}' is incomplete, skipping.")
            return guide_extracted

        # Get the target table from guide_extracted
        table_data = guide_extracted.get(target_field)

        # Handle dict-wrapped table: {"value": [...], "confidence": ...}
        is_wrapped = False
        wrapper = {}
        if isinstance(table_data, dict) and "value" in table_data and isinstance(table_data["value"], list):
            is_wrapped = True
            wrapper = {k: v for k, v in table_data.items() if k != "value"}
            table_data = table_data["value"]

        if not isinstance(table_data, list):
            logger.debug(f"[TransformEngine] Target '{target_field}' is not a list, skipping rule '{rule_name}'.")
            return guide_extracted

        expanded_rows = []
        expansions = 0

        for row in table_data:
            if not isinstance(row, dict):
                expanded_rows.append(row)
                continue

            # Get the cell value to check
            cell = row.get(match_field, {})
            cell_value = cell.get("value") if isinstance(cell, dict) else cell

            # Check if this row matches the rule
            should_expand = False
            if match_value == "*":
                # Wildcard — expand all rows
                should_expand = True
            elif match_value and cell_value:
                # Exact or contains match
                if str(cell_value).strip().upper() == str(match_value).strip().upper():
                    should_expand = True
                elif str(match_value).strip().upper() in str(cell_value).strip().upper():
                    should_expand = True

            if not should_expand:
                expanded_rows.append(row)
                continue

            # Expand: create N new rows, one per expand_value
            for idx, exp_val in enumerate(expand_values):
                new_row = copy.deepcopy(row)

                # Set the expand_field value
                exp_cell = new_row.get(expand_field, {})
                if isinstance(exp_cell, dict):
                    new_row[expand_field] = {
                        **exp_cell,
                        "value": exp_val,
                        "confidence": exp_cell.get("confidence", 0) if isinstance(exp_cell, dict) else 0,
                        "_transformed": True
                    }
                else:
                    new_row[expand_field] = {"value": exp_val, "_transformed": True}

                # Set the code_field value if provided
                if code_field and expand_codes and idx < len(expand_codes):
                    code_cell = new_row.get(code_field, {})
                    if isinstance(code_cell, dict):
                        new_row[code_field] = {
                            **code_cell,
                            "value": expand_codes[idx],
                            "_transformed": True
                        }
                    else:
                        new_row[code_field] = {"value": expand_codes[idx], "_transformed": True}

                expanded_rows.append(new_row)
                expansions += 1

        if expansions > 0:
            logger.info(f"[TransformEngine] Rule '{rule_name}': expanded {expansions} rows on '{target_field}.{expand_field}'")

        # Write back
        if is_wrapped:
            guide_extracted[target_field] = {"value": expanded_rows, **wrapper}
        else:
            guide_extracted[target_field] = expanded_rows

        return guide_extracted
