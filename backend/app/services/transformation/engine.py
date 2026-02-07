import logging
from typing import List, Dict, Any
from pydantic import BaseModel
from simpleeval import simple_eval, EvalWithCompoundTypes

logger = logging.getLogger(__name__)

class TransformationRule(BaseModel):
    type: str  # EXPLODE, CALCULATE, VALIDATE
    config: Dict[str, Any]
    enabled: bool = True

class TransformationEngine:
    def __init__(self):
        self.handlers = {
            "EXPLODE": self._handle_explode,
            "CALCULATE": self._handle_calculate,
            "VALIDATE": self._handle_validate
        }

    def apply(self, data: Dict[str, Any], rules: List[TransformationRule]) -> Dict[str, Any]:
        """Apply a list of transformation rules to the data."""
        # Deep copy data to avoid mutating original during processing steps
        import copy
        processed_data = copy.deepcopy(data)

        results = {
            "original": data,
            "processed": processed_data,
            "audit": []
        }

        for i, rule in enumerate(rules):
            if not rule.enabled:
                continue

            try:
                handler = self.handlers.get(rule.type)
                if not handler:
                    logger.warning(f"[Transformation] Unknown rule type: {rule.type}")
                    continue

                processed_data = handler(processed_data, rule.config)
                results["audit"].append({
                    "rule_index": i,
                    "type": rule.type,
                    "status": "success"
                })

            except Exception as e:
                logger.error(f"[Transformation] Rule failed: {rule.type} - {e}")
                results["audit"].append({
                    "rule_index": i,
                    "type": rule.type,
                    "status": "failed",
                    "error": str(e)
                })
                # Decide policy: Continue or Stop?
                # For now, we continue but log the error

        results["processed"] = processed_data
        return results

    def _handle_explode(self, data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Explode lists into combinations.
        Config:
          - sources: [{"field": "POL_List", "as": "POL"}, {"field": "POD_List", "as": "POD"}]
          - output_field: "Rate_Explosion_List"
          - preserve_fields: ["Carrier"] (fields to copy to every row)
        """
        import itertools

        # 1. Get source lists
        sources = config.get("sources", [])
        output_field = config.get("output_field", "Exploded_List")
        preserve_fields = config.get("preserve_fields", [])

        list_values = []
        keys = []

        for src in sources:
            fname = src.get("field")
            alias = src.get("as", fname)
            val = data.get(fname)

            # Validation: ensure it is a list
            if not isinstance(val, list):
                if val is None:
                    val = []  # Handle null as empty list
                else:
                    # Try to parse if it's a string representation of list
                    # But for now, wrap single value in list
                    val = [val]

            list_values.append(val)
            keys.append(alias)

        # 2. Generate Cartesian Product
        combinations = list(itertools.product(*list_values))

        # 3. Create Rows
        result_rows = []
        for combo in combinations:
            row = {}
            for k, v in zip(keys, combo):
                row[k] = v

            # Copy preserved fields
            for pf in preserve_fields:
                if pf in data:
                    row[pf] = data[pf]

            result_rows.append(row)

        # 4. Assign to output
        data[output_field] = result_rows
        return data

    def _handle_calculate(self, data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply calculations.
        Config:
          - target_list: "Rate_Explosion_List" (optional, if operating on list items)
          - calculations: [
              {"field": "Rate", "expression": "Base_Rate + 50", "condition": "POL == 'Incheon'"}
            ]
        """
        target_list = config.get("target_list")
        calcs = config.get("calculations", [])

        # Helper to safely evaluate expression using simpleeval (no eval() / no code injection)
        def safe_eval(expr, context):
            try:
                evaluator = EvalWithCompoundTypes(names=context)
                return evaluator.eval(str(expr))
            except Exception as e:
                logger.warning(f"Safe eval failed: {expr} with context keys={list(context.keys())} -> {e}")
                return None

        if target_list:
            # Operation on list items
            rows = data.get(target_list, [])
            if not isinstance(rows, list):
                return data

            for row in rows:
                # Context is the row itself plus top-level data
                context = {**data, **row}

                for calc in calcs:
                    condition = calc.get("condition", "True")
                    if safe_eval(condition, context):
                        field = calc.get("field")
                        expr = calc.get("expression")
                        result = safe_eval(expr, context)
                        if result is not None:
                            row[field] = result
        else:
            # Top level operation
            for calc in calcs:
                condition = calc.get("condition", "True")
                if safe_eval(condition, data):
                    field = calc.get("field")
                    expr = calc.get("expression")
                    result = safe_eval(expr, data)
                    if result is not None:
                        data[field] = result

        return data

    def _handle_validate(self, data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate data and add audit warnings/errors.
        Config:
          - check: "len(Routes) == len(POL_List) * len(POD_List)"
          - severity: "warning" | "error"
          - message: "Validation failed"
        """
        check_expr = config.get("check")
        severity = config.get("severity", "warning")
        message = config.get("message", "Validation failed")

        # Safe evaluation using simpleeval (no eval() / no code injection)
        def safe_eval(expr, context):
            try:
                evaluator = EvalWithCompoundTypes(
                    names=context,
                    functions={"len": len}
                )
                return evaluator.eval(str(expr))
            except Exception as e:
                logger.warning(f"Validation eval failed: {expr} -> {e}")
                return False

        if check_expr:
            if not safe_eval(check_expr, data):
                logger.info(f"Validation failed: {check_expr}")
                # Add validation failure to audit
                if "validation_errors" not in data:
                    data["validation_errors"] = []

                data["validation_errors"].append({
                    "severity": severity,
                    "message": message,
                    "check": check_expr
                })

        return data
