from typing import Dict, Any
import json
import logging
from app.schemas.model import ExtractionModel
from app.core.config import settings

logger = logging.getLogger(__name__)

# Canonical set of field types that represent table/list data
TABLE_FIELD_TYPES = {'list', 'table', 'array'}

class RefinerEngine:
    """
    Constructs dynamic prompts based on natural language rules defined in the Studio.
    """

    @staticmethod
    def construct_prompt(model: ExtractionModel, language: str = "ko", table_only: bool = False, mode: str = "all") -> str:
        """
        Constructs a system prompt for the Refiner model.
        mode options:
        - "all": Include all fields (default)
        - "common": Include only non-list fields
        - "table": Include only list fields (equivalent to table_only=True)
        """
        if table_only:
             mode = "table"

        # Filter fields based on mode
        if mode == "common":
            active_fields = [f for f in model.fields if f.type not in TABLE_FIELD_TYPES]
            mode_instruction = "Extract ONLY the common/metadata fields. Ignore any table/list data."
        elif mode == "table":
            active_fields = [f for f in model.fields if f.type in TABLE_FIELD_TYPES]
            mode_instruction = "Extract ONLY the table/list fields. Ignore any common/metadata fields."
        else:
            active_fields = model.fields
            mode_instruction = "Extract all fields defined in the schema."

        
        # Helper to access attributes safely
        def get_attr(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        name = get_attr(model, "name", "Unknown Model")
        description = get_attr(model, "description", None)
        global_rules = get_attr(model, "global_rules", None)
        reference_data = get_attr(model, "reference_data", None)
        fields = active_fields # Use active_fields for the rest of the prompt construction
        
        # 1. Base Context
        prompt = f"""You are an advanced document intelligence AI.
Target Domain: {name}
Context: {description or 'General Document'}
"""

        # 2. Global Rules
        if global_rules:
            prompt += f"\nGLOBAL REFINEMENT RULES:\n{global_rules}\n"

        # 3. Reference Data (Filtered for validation only to prevent Vibe Dictionary token bloat)
        filtered_ref = {k: v for k, v in (reference_data or {}).items() if k in ("validation_rules", "unique_constraints")} if reference_data else None
        if filtered_ref:
            ref_json = json.dumps(filtered_ref, ensure_ascii=False, indent=2)
            # SAFETY: Truncate if massive (prevent 10K+ token bloat)
            MAX_REF_CHARS = getattr(settings, 'REFINER_MAX_REF_CHARS', 5000)
            if len(ref_json) > MAX_REF_CHARS:
                ref_json = ref_json[:MAX_REF_CHARS] + "\n... [TRUNCATED DUE TO SIZE]"
                logger.warning(f"[Refiner] Reference data truncated (size: {len(ref_json)} chars)")

            prompt += f"""
REFERENCE DATA (Validation Rules):
{ref_json}

INSTRUCTIONS FOR REFERENCE DATA:
- Apply validation rules specified in reference_data
- Reference data takes precedence over guessing
"""

        # 3. Field Instructions

        prompt += "\nREQUIRED EXTRACTION FIELDS:\n"
        for field in fields:
            # Indicate required status prominently
            req_marker = "[REQUIRED]" if field.required else "[OPTIONAL]"
            prompt += f"- {field.key} ({field.label}) {req_marker}:\n"
            
            desc = field.description
            if desc and desc.strip():
                prompt += f"  Description: {desc}\n"
            
            if field.rules:
                prompt += f"  Refinement Rule: {field.rules}\n"
                
            if getattr(field, 'validation_regex', None):
                prompt += f"  Validation Regex: MUST exactly match pattern `{field.validation_regex}`\n"
                
            prompt += f"  Type: {field.type}\n"
            
            # If sub-fields exist, list them out with their constraints
            if getattr(field, 'sub_fields', None):
                prompt += "  Sub-Fields (apply recursively):\n"
                for sf in field.sub_fields:
                    sf_req = "[REQUIRED]" if sf.get('required') else "[OPTIONAL]"
                    prompt += f"    - {sf.get('key')} ({sf.get('label')}) {sf_req}: Type {sf.get('type', 'string')}\n"
                    if sf.get('rules'):
                        prompt += f"      Rule: {sf.get('rules')}\n"
                    if sf.get('validation_regex'):
                        prompt += f"      Regex: MUST exactly match pattern `{sf.get('validation_regex')}`\n"

        # 4. Output Formatting — detect table from field types (data_structure manual selector deprecated)
        # data_structure = get_attr(model, 'data_structure', 'data')  # DEPRECATED
        def is_table_field(f):
            return getattr(f, 'type', '') in TABLE_FIELD_TYPES or bool(getattr(f, 'sub_fields', None))

        is_table = any(is_table_field(f) for f in fields)

        if is_table:
            # Unified TABLE MODE: Always use guide_extracted root key with actual field keys.
            # This prevents data loss from _legacy_rows key mismatch.
            non_table_fields = [f for f in fields if not is_table_field(f)]
            table_fields = [f for f in fields if is_table_field(f)]

            example_parts = []
            for f in non_table_fields:
                example_parts.append(f'    "{f.key}": {{"value": "extracted value or null", "confidence": 0.95, "source_text": "verbatim text from doc"}}')
            
            for f in table_fields:
                example_parts.append(f'    "{f.key}": [\n      {{ "col1": {{"value": "val1", "confidence": 0.9, "source_text": "val1 text"}}, "col2": {{"value": "val2", "confidence": 0.8, "source_text": "val2 text"}} }}\n    ]')

            example_json = "{\n  \"guide_extracted\": {\n" + ",\n".join(example_parts) + "\n  }\n}"

            prompt += f"""
OUTPUT INSTRUCTIONS (TABLE MODE):
You must extract ALL rows from the document. Do NOT truncate or sample.

**CRITICAL: MULTIPLE TABLES**
- If the document contains MULTIPLE separate physical tables that match the same table field (e.g., items continuing on the next page, or multiple distinct tables of the same type), you MUST extract rows from EVERY matching table and combine them all into the SINGLE array. DO NOT stop after extracting just the first table!

**CRITICAL: DENORMALIZE HIERARCHICAL DATA**
- If the table has merged cells or hierarchical headers (e.g., one 'Route' applies to multiple 'POL/POD' rows), **YOU MUST REPEAT** the parent value for EVERY child row.
- Every row object must be complete.

**CRITICAL: STRICT SCHEMA & FORMAT**
1. Output format MUST be:
{example_json}
2. Root key MUST be "guide_extracted".
3. **Single fields** (e.g. Invoice No, Date) go at the root of "guide_extracted".
4. **Table fields** (List type) go as JSON Arrays within "guide_extracted".
   - Inside the table array, each item is a row object with column keys.
5. **MAP HEADERS**: You must map document headers to the EXACT field keys defined above.
   - Example: If doc has "Charge_Type", map it to "charge_type".
   - **CRITICAL**: If a table field lacks an explicit list of sub-field column keys, you MUST infer the required column keys by reading the field's `Description` or `Refinement Rule`. Convert the requested column names to clean `snake_case`. DO NOT just blindly copy the exact document header text (like Excel headers) as the JSON key!

**CRITICAL: STRICT VALIDATION RULES**
- If a [REQUIRED] field's value is not explicitly present in the document, set "value": null and "confidence": 0.1. NEVER invent, guess, or infer a value.
- A missing value is ALWAYS better than a wrong value. Nulls can be corrected by users; hallucinated values cannot be detected.
- If a field has a **Validation Regex**, the extracted string MUST conform to that REGEX exactly. If it does not naturally conform, you must format or clean up the string so that it matches. Do not return failing strings.

**CRITICAL: DO NOT FLATTEN**
- Do NOT force header fields into every table row. Keep them separate at the root level.
- Do NOT output a single "rows" list unless the field type is explicitly a list.

**CRITICAL: CHECKBOXES & SELECTION MARKS**
- The document text may contain `:selected:` or `:unselected:` tokens representing checkboxes.
- `:selected:` means the checkbox/radio button is CHECKED (True/Yes).
- `:unselected:` means the checkbox/radio button is UNCHECKED (False/No).
- If your instruction asks to extract ONLY selected items, you MUST filter and extract only rows/values that have a `:selected:` mark next to them. If it has `:unselected:`, IGNORE it.
- If your instruction asks for the state of a checkbox, map `:selected:` to true/Yes and `:unselected:` to false/No.
"""
        else:
            prompt += f"""
OUTPUT INSTRUCTIONS:
You must extract the data into a valid JSON object with a specific structure.
Root key: "guide_extracted"

Format:
{{
  "guide_extracted": {{
    "FIELD_KEY": {{
      "value": "extracted value or null",
      "confidence": 0.0 to 1.0,
      "source_text": "exact substring from document used for extraction",
      "page_number": integer (1-based)
    }},
    ... (repeat for all required fields)
  }}
}}

CRITICAL RULES:
1. "source_text" MUST be the EXACT substring found in the document.
2. If a field is not found, set "value": null.
3. Do not add fields that are not in the REQUIRED EXTRACTION FIELDS list.
4. VALIDATION: If a [REQUIRED] field's value is not explicitly present in the document, set "value": null and "confidence": 0.1. NEVER invent or guess a value. If found, apply formatting adjustments so it strictly meets any **Validation Regex**.


LANGUAGE INSTRUCTION:
Extract the value exactly as it appears in the document (Original Language).
Do NOT translate unless the field rule explicitly mentions translation.
"""
        return prompt

    @staticmethod
    def post_process_result(llm_result: Dict[str, Any], ocr_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps extracted values back to bounding boxes using fuzzy matching against OCR words.
        Uses 'thefuzz' for robust string matching to handle OCR errors and multi-word phrases.
        """
        from thefuzz import fuzz, process

        # Build indexed words dict: {index: word_info}
        all_words_flat = []
        word_choices = {}  # {index: content_string} for process.extractOne
        for page in ocr_result.get("pages") or []:
            page_num_val = page.get("page_number", 1)
            for word in page.get("words", []):
                content = word.get("content", "")
                if not content:
                    continue  # Skip empty/missing content words
                idx = len(all_words_flat)
                all_words_flat.append({
                    "content": content,
                    "polygon": word.get("polygon"),
                    "page": page_num_val,
                })
                word_choices[idx] = content

        def _process_cell(cell: Any) -> Any:
            if not isinstance(cell, dict) or "value" not in cell:
                return cell

            value = cell.get("value")
            confidence = cell.get("confidence", 0.0)
            source_text = cell.get("source_text", "")

            bbox = None
            page_num = 1

            if source_text and word_choices:
                # For multi-word phrases, search the longest word for best match
                is_phrase = len(source_text.split()) > 1
                search_term = source_text if not is_phrase else max(source_text.split(), key=len)

                try:
                    # extractOne with dict returns (match_text, score, key)
                    extracted = process.extractOne(search_term, word_choices, scorer=fuzz.ratio)

                    if extracted and len(extracted) >= 3:
                        _match_text, score, match_idx = extracted
                        if score >= 85 and match_idx < len(all_words_flat):
                            best = all_words_flat[match_idx]
                            bbox = best.get("polygon")
                            page_num = best.get("page", 1)
                    elif extracted and len(extracted) >= 2:
                        _match_text, score = extracted[0], extracted[1]
                        if score >= 85:
                            for w in all_words_flat:
                                if w.get("content") == _match_text:
                                    bbox = w.get("polygon")
                                    page_num = w.get("page", 1)
                                    break
                except Exception as e:
                    logger.warning(f"[PostProcess] Fuzzy match error: {e}")

            return {
                "value": value,
                "confidence": confidence,
                "source_text": source_text,
                "bbox": bbox,
                "page": page_num
            }

        processed_data = {}
        has_guide_wrapper = "guide_extracted" in llm_result and isinstance(llm_result["guide_extracted"], dict)
        target_dict = llm_result["guide_extracted"] if has_guide_wrapper else llm_result

        for key, item in target_dict.items():
            if isinstance(item, list):
                # Process table rows
                processed_rows = []
                for row in item:
                    if isinstance(row, dict):
                        processed_row = {k: _process_cell(v) for k, v in row.items()}
                        processed_rows.append(processed_row)
                    else:
                        processed_rows.append(row)
                processed_data[key] = processed_rows
            elif isinstance(item, dict):
                processed_data[key] = _process_cell(item)
            else:
                processed_data[key] = item

        if has_guide_wrapper:
            # Preserve original outer structure
            llm_result["guide_extracted"] = processed_data
            return llm_result
        return processed_data

    # ========================================================================
    # Designer-Engineer Pipeline (Two-Phase LLM Architecture)
    # ========================================================================

    @staticmethod
    def construct_designer_prompt(model: ExtractionModel) -> str:
        """
        Phase ①: Generates the Designer LLM system prompt.
        Input: Model schema + calibration rules → Output: Work Order JSON.
        """
        def get_attr(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        name = get_attr(model, "name", "Unknown Model")
        description = get_attr(model, "description", None)
        global_rules = get_attr(model, "global_rules", None)
        reference_data = get_attr(model, "reference_data", None)
        # data_structure = get_attr(model, "data_structure", "data")  # DEPRECATED
        fields = model.fields

        TABLE_FIELD_TYPES = ('list', 'table', 'array')

        # Build fields JSON for the prompt
        fields_json = json.dumps([
            {
                "key": f.key,
                "label": f.label,
                "description": f.description,
                "rules": f.rules,
                "type": f.type,
                "sub_fields": f.sub_fields
            }
            for f in fields
        ], ensure_ascii=False, indent=2)

        filtered_ref = {k: v for k, v in (reference_data or {}).items() if k in ("validation_rules", "unique_constraints")} if reference_data else None
        ref_data_section = ""
        if filtered_ref:
            ref_json = json.dumps(filtered_ref, ensure_ascii=False, indent=2)
            MAX_REF_CHARS = getattr(settings, 'REFINER_MAX_REF_CHARS', 5000)
            if len(ref_json) > MAX_REF_CHARS:
                ref_json = ref_json[:MAX_REF_CHARS] + "\n... [TRUNCATED]"
            ref_data_section = f"\nREFERENCE DATA (Validation Constraints):\n{ref_json}\n"

        calibration_section = ""
        if global_rules:
            calibration_section = f"\nCALIBRATION RULES (from admin):\n{global_rules}\n"

        # Field type classification guidance
        common_keys = [f.key for f in fields if f.type not in TABLE_FIELD_TYPES]
        table_keys = [f.key for f in fields if f.type in TABLE_FIELD_TYPES]
        type_guidance = ""
        if common_keys:
            type_guidance += f"\nCOMMON FIELDS (single values): {', '.join(common_keys)}"
        if table_keys:
            type_guidance += f"\nTABLE FIELDS (list of rows): {', '.join(table_keys)}"

        prompt = f"""You are a Document Extraction Architect.

Given an extraction model schema and calibration rules, generate a WORK ORDER
that an extraction engineer will follow to extract data from a document.

MODEL: {name}
DOMAIN: {description or 'General Document'}
DATA STRUCTURE: auto (table fields detected from schema)
{type_guidance}

MODEL SCHEMA:
{fields_json}
{calibration_section}{ref_data_section}
OUTPUT: A JSON object with this structure:
{{
  "work_order": {{
    "document_type": "brief description",
    "extraction_mode": "data" or "table",
    "common_fields": [
      {{
        "key": "field_key", 
        "instruction": "Detailed extraction command incorporating the user description", 
        "rules": ["Verbatim rule 1 from schema", "Verbatim rule 2 from schema"],
        "expected_format": "type"
      }}
    ],
    "table_fields": [
      {{
        "key": "field_key",
        "instruction": "Detailed extraction command",
        "columns": {{
          "col_key": {{
            "instruction": "command", 
            "source_hint": "likely header variations",
            "rules": ["Verbatim column rule from schema"]
          }}
        }},
        "rules": ["table level rule from schema"]
      }}
    ],
    "integrity_rules": [
      "Copy values exactly as written. No conversion/calculation/translation.",
      "Missing values must be null.",
      "Extract in original language. Do NOT translate unless field rule says so."
    ]
  }}
}}

FIELD CLASSIFICATION RULES:
- Fields with type "list", "table", or "array" → table_fields (with columns)
- All other fields → common_fields (single values)
- table_fields MUST include a "columns" object with ALL sub-field keys.

CRITICAL PRECISION & RULE PRESERVATION:
- DO NOT SUMMARIZE OR CONDENSE the user's "description" and "rules" from the schema.
- You MUST explicitly copy the user's custom "rules" into the "rules" array of each field/column. Loss of rule details causes catastrophic extraction failures.
- If the schema has a rich description, the "instruction" must be detailed enough to capture all edge cases mentioned.

CRITICAL TABLE SUB-COLUMN EXTRACTION:
- For any field classified as "table_fields" (type: list, table, array), YOU MUST USE the provided "sub_fields" array if it exists to strictly define the columns.
- Create a distinct sub-key in the "columns" object for EVERY item in "sub_fields", using its "key". Incorporate its "label", "description", and "rules" into detailed column instructions.
- If "sub_fields" is empty or missing, fallback to reading the user's field description (e.g., "Extract POL, POD") to determine required column keys. Convert the names intended by the user into clean snake_case keys. DO NOT blindly copy the exact document header text (like Excel headers) as the JSON key!
- DO NOT use generic keys like "col1".

ROW CLASSIFICATION RULES PASSTHROUGH:
- If a table field has "include_when", "exclude_when", "group_row_behavior", or "field_inheritance" in its schema definition, copy them VERBATIM into the work order table_field entry.
- These are business-logic rules that define which rows belong to this table field. DO NOT summarize, modify, or omit them.
- Example: if schema has {{"key": "Basic_Rate_List", "include_when": ["row has freight amounts"]}},
  the work order table_field must have: {{"key": "Basic_Rate_List", "include_when": ["row has freight amounts"], ...}}

ZERO TOLERANCE — FIELD COVERAGE:
- You MUST generate exactly one instruction entry for EVERY field in the schema.
- Input schema has {len(fields)} fields → output MUST have exactly {len(fields)} entries
  across common_fields + table_fields combined.
- Skipping, merging, or omitting even ONE field is a critical failure.
- After all {len(fields)} schema fields, ALSO append the unmapped entry below.
  Total output = {len(fields)} schema entries + 1 unmapped entry.

ALWAYS APPEND THIS ENTRY to common_fields (after all schema fields):
{{
  "key": "unmapped_critical_info",
  "instruction": "Scan the entire document for text marked as 'Important', 'Note', '주의', '특약', '비고', 'Remark', or similar annotations that do NOT belong to any field above. Copy verbatim. If none found, return null.",
  "expected_format": "text",
  "rules": ["Do not duplicate data already extracted in other fields"]
}}

STYLE CONSTRAINTS:
- Do NOT write prose or rationale. Write explicit commands.
- Do NOT repeat generic integrity rules per field — use the shared integrity_rules array.
- COMPLETENESS over brevity: include ALL columns for every table field. The work order is cached and reused, so length is not a concern.
"""
        return prompt

    @staticmethod
    def construct_analyst_prompt(model: ExtractionModel) -> str:
        """
        Phase 1.5: Generates the Mapping Designer LLM system prompt.
        Analyzes document skeleton + model schema to produce a structured mapping plan.
        Input: Model schema + document skeleton → Output: mapping plan JSON.
        """
        schema_json = model.model_dump_json(include={'fields'}, indent=2)
        prompt = f"""You are a Senior Document Mapping Architect.

Your task is to analyze the 'document skeleton' (headers, table structures, section patterns) alongside the target extraction schema, and produce a MAPPING PLAN that tells the extraction engineer exactly how to map the source document's structure to the target schema.

TARGET EXTRACTION SCHEMA:
{schema_json}

YOUR JOB:
1. Examine the document skeleton to understand the actual structure: table headers, section headers, global metadata, notes.
2. Compare the source document's structure with the target schema fields.
3. Produce a mapping plan with the sections described below.

OUTPUT FORMAT — return ONLY valid JSON:
{{
  "dynamic_hints": [
    "Critical observation 1 about this document",
    "Critical observation 2"
  ],
  "field_mappings": [
    {{
      "target_key": "TableName.FieldKey",
      "source_selector": {{
        "type": "table_column",
        "table_index": 0,
        "column_name": "Original Column Header"
      }},
      "source_description": "Human-readable description of where to find this value",
      "rule": "Explanation of why this mapping is needed"
    }}
  ],
  "inheritance_rules": [
    {{
      "target_key": "FieldKey",
      "source": "nearest_preceding_section",
      "pattern": "Regex or text pattern to extract the value",
      "scope": "section",
      "applies_to": ["TableName1", "TableName2"],
      "rule": "Explanation"
    }}
  ],
  "table_structure": {{
    "carry_forward_columns": ["column_name"],
    "group_header_values": ["US IPI", "CA IPI"],
    "group_row_behavior": "context_label",
    "notes_location": "below_table"
  }}
}}

FIELD MAPPING GUIDELINES:
- source_selector.type values:
  - "table_column": Value comes from a specific column in a table. Include "table_index" and "column_name".
  - "global_text": Value is found in the document body via pattern matching (not in a table). Include "pattern".
  - "section_header": Value is in a section header (e.g., "Validity: 2024-01-01 ~ 2024-03-31"). Include "pattern".
  - "derived": Value must be computed or combined from other fields.
- Only include mappings where the source document structure does NOT directly match the target schema field name.
- applies_to: list of table field keys this rule affects. Use ["*"] to mean all tables.

INHERITANCE RULE GUIDELINES:
- scope: "section" = inherit from nearest preceding section header; "global" = one value for the entire document; "document" = from document metadata area
- applies_to: list of table field keys this rule affects. Use ["*"] for all tables.
- Use inheritance rules when a value is NOT present per-row but applies to groups of rows (e.g., Validity dates, Currency, Service Terms)

TABLE STRUCTURE GUIDELINES:
- carry_forward_columns: columns where blank cells mean "same as above" (common in shipping/logistics tables)
- group_header_values: specific text values that serve as section separators within a table, NOT as data rows
- group_row_behavior: "context_label" = preserve as context for child rows; "skip" = ignore entirely; "prefix_to_children" = prepend to a field in child rows
- notes_location: where supplementary notes/remarks appear relative to the table

ROW CLASSIFICATION RULES (for table/list fields ONLY):
- If a table field does NOT already have include_when/exclude_when in its schema definition, you MAY generate row_classification_rules.
- This helps the engineer decide which source rows belong to which target list field.
- Format:
  "row_classification_rules": [
    {{
      "table_field": "Basic_Rate_List",
      "include_when": ["row has freight amount in numeric columns"],
      "exclude_when": ["row is only a group header label"]
    }}
  ]
- ONLY generate these for table fields where it's genuinely ambiguous which rows belong.
- If the schema already defines include_when/exclude_when, do NOT generate row_classification_rules for that field.

RULES:
- ALL sections except "dynamic_hints" are OPTIONAL. If you cannot determine mappings or structure, omit that section entirely.
- dynamic_hints should contain 2-5 critical observations about this specific document.
- Do NOT invent mappings if you are unsure. Only map what you can clearly identify from the skeleton.
- Be specific: use actual column names, section text, and patterns from the document skeleton.
"""
        return prompt

    @staticmethod
    def construct_engineer_prompt(work_order: dict, reference_data: dict = None) -> str:
        """
        Phase ②: Generates the Engineer LLM system prompt.
        Input: Work Order + tagged text → Output: JSON with ref tags.
        Optionally includes reference_data for value mapping/validation.
        """
        work_order_json = json.dumps(work_order, ensure_ascii=False, indent=2)

        # Extract integrity rules from work order
        wo_inner = work_order.get("work_order", work_order)
        integrity_rules = wo_inner.get("integrity_rules", [])
        integrity_rules_str = "\n".join(f"- {r}" for r in integrity_rules) if integrity_rules else "- Extract values exactly as written."

        # Extract dynamic hints (added by Mapping Designer phase)
        dynamic_hints = wo_inner.get("dynamic_hints", [])
        dynamic_hints_str = ""
        if dynamic_hints:
            dynamic_hints_str = "\nDOCUMENT ANALYSIS HINTS (CRITICAL - FOR THIS SPECIFIC DOCUMENT):\n" + "\n".join(f"!!! {h}" for h in dynamic_hints) + "\n"

        # Build Mapping Plan section (from Mapping Designer)
        mapping_plan_str = ""
        field_mappings = wo_inner.get("field_mappings", [])
        inheritance_rules = wo_inner.get("inheritance_rules", [])
        table_structure = wo_inner.get("table_structure")

        if field_mappings or inheritance_rules or table_structure:
            mapping_plan_str = """
MAPPING PLAN (from document-specific analysis):
Follow the mapping plan as the PRIMARY interpretation guide for document structure and source-to-target mapping.
If the actual source text clearly contradicts the plan, prefer the source text and return null rather than forcing an incorrect mapping.
For unmapped fields, fall back to generic work order instructions.
"""
            if field_mappings:
                mapping_plan_str += "\nFIELD MAPPINGS (use source_selector to locate values):\n"
                for m in field_mappings:
                    selector = m.get("source_selector", {})
                    sel_type = selector.get("type", "unknown")
                    col_name = selector.get("column_name", "")
                    pattern = selector.get("pattern", "")
                    # Build procedural instruction based on selector type
                    if sel_type == "table_column":
                        procedure = f"Search table column '{col_name}' for this value."
                    elif sel_type == "section_header":
                        procedure = f"Do NOT search in table rows. Look in section headers" + (f" matching pattern '{pattern}'" if pattern else "") + "."
                    elif sel_type == "global_text":
                        procedure = f"Search document body (outside tables)" + (f" matching pattern '{pattern}'" if pattern else "") + "."
                    elif sel_type == "derived":
                        procedure = "Compute from other field values."
                    else:
                        procedure = m.get('source_description', '')
                    mapping_plan_str += f"- {m.get('target_key', '?')}: {procedure} {m.get('rule', '')}\n"

            if inheritance_rules:
                mapping_plan_str += "\nINHERITANCE RULES (PROCEDURAL — follow these steps):\n"
                for r in inheritance_rules:
                    scope = r.get("scope", "section")
                    applies = r.get("applies_to", ["*"])
                    applies_str = ", ".join(applies) if isinstance(applies, list) else str(applies)
                    pattern = r.get("pattern", "")
                    # Build step-by-step procedure
                    steps = f"- {r.get('target_key', '?')}:\n"
                    steps += f"  1. Do NOT extract this field from each row.\n"
                    if scope == "section":
                        steps += f"  2. Find the nearest preceding section header" + (f" matching '{pattern}'" if pattern else "") + ".\n"
                        steps += f"  3. Apply the extracted value to ALL rows in the following tables: {applies_str}.\n"
                        steps += f"  4. When a new section header appears, update the inherited value for subsequent rows.\n"
                    elif scope == "global":
                        steps += f"  2. Extract this value ONCE from the document header/metadata area" + (f" matching '{pattern}'" if pattern else "") + ".\n"
                        steps += f"  3. Apply the same value to ALL rows across tables: {applies_str}.\n"
                    elif scope == "document":
                        steps += f"  2. Look in the document metadata section" + (f" matching '{pattern}'" if pattern else "") + ".\n"
                        steps += f"  3. Apply to tables: {applies_str}.\n"
                    mapping_plan_str += steps

            if table_structure:
                mapping_plan_str += "\nTABLE STRUCTURE RULES (PROCEDURAL):\n"
                if cf := table_structure.get("carry_forward_columns"):
                    mapping_plan_str += f"- CARRY-FORWARD: For columns [{', '.join(cf)}], if a cell is blank, inherit the nearest previous non-empty value within the same group section. Do NOT carry forward across group headers.\n"
                if gh := table_structure.get("group_header_values"):
                    behavior = table_structure.get("group_row_behavior", "context_label")
                    if behavior == "context_label":
                        mapping_plan_str += f"- GROUP HEADERS: Rows containing only [{', '.join(gh)}] are section labels, NOT data rows. Do NOT extract them as data. Use them as context for the rows that follow.\n"
                    elif behavior == "skip":
                        mapping_plan_str += f"- GROUP HEADERS: Rows containing only [{', '.join(gh)}] must be SKIPPED entirely.\n"
                    elif behavior == "prefix_to_children":
                        mapping_plan_str += f"- GROUP HEADERS: Rows containing [{', '.join(gh)}] are group labels. Prefix their value to the appropriate field in each child row below them.\n"
                if nl := table_structure.get("notes_location"):
                    mapping_plan_str += f"- NOTES: Supplementary notes are located {nl}.\n"

        # Extract explicit ROW EXPANSION rules from field definitions
        expansion_str = ""
        for tf in wo_inner.get("table_fields", []):
            tf_key = tf.get("key", "?")
            
            # Check table-level rules
            for rule in tf.get("rules", []):
                if any(k in rule.lower() for k in ["split", "comma", "slash", "row", "separate"]):
                    expansion_str += f"- Table {tf_key}: {rule}\n"
            
            # Check column-level rules
            for col_key, col_data in tf.get("columns", {}).items():
                for rule in col_data.get("rules", []):
                     # Specifically target rules asking for split/expansion, e.g. "Split by / or , into unique rows"
                     if any(k in rule.lower() for k in ["split", "comma", "slash", "row", "separate"]):
                         expansion_str += f"- Column {tf_key}.{col_key}: {rule} (DUPLICATE the other column values for each new row!)\n"
                         
        if expansion_str:
            mapping_plan_str += f"\nROW EXPANSION RULES (CRITICAL MANDATORY):\n"
            mapping_plan_str += f"If any field contains multiple values separated by commas, slashes, or newlines, you MUST obey these rules and create SEPARATE rows for each value!\n"
            mapping_plan_str += expansion_str

        # Build ROW CLASSIFICATION RULES section from table_fields
        classification_str = ""
        for tf in wo_inner.get("table_fields", []):
            inc = tf.get("include_when", [])
            exc = tf.get("exclude_when", [])
            grb = tf.get("group_row_behavior")
            fi = tf.get("field_inheritance", {})
            if inc or exc or grb or fi:
                classification_str += f"\n- {tf.get('key', '?')}:\n"
                if inc:
                    for rule in inc:
                        classification_str += f"  INCLUDE when: {rule}\n"
                if exc:
                    for rule in exc:
                        classification_str += f"  EXCLUDE when: {rule}\n"
                if grb:
                    if grb == "context_label":
                        classification_str += f"  Group headers are context labels — do NOT extract as data rows, use as context for rows below.\n"
                    elif grb == "skip":
                        classification_str += f"  Group headers must be SKIPPED entirely.\n"
                    elif grb == "prefix_to_children":
                        classification_str += f"  Group header values should be prefixed to the appropriate field in each child row.\n"
                if fi:
                    classification_str += f"  FIELD INHERITANCE (do NOT extract these per-row):\n"
                    for sub_key, source in fi.items():
                        classification_str += f"    - {sub_key}: derive from {source}. If section not found, return null.\n"
        
        if classification_str:
            mapping_plan_str += f"\nROW CLASSIFICATION RULES (CRITICAL MANDATORY):\n"
            mapping_plan_str += f"You MUST STRICTLY classify rows according to these rules. If a row does NOT uniquely match the INCLUDE rules of a specific table_field, or if it matches EXCLUDE rules, DO NOT place it in that field!\n"
            mapping_plan_str += f"CRITICAL: Do not mix unrelated notes, freetimes, route add-ons, or generic remarks into monetary surcharge tables.\n"
            mapping_plan_str += f"{classification_str}"

        # Build dynamic output example from field keys in work_order
        example_parts = []
        for cf in wo_inner.get("common_fields", []):
            key = cf.get("key", "field")
            example_parts.append(f'    "{key}": {{"value": "...", "ref": "W1"}}')
        for tf in wo_inner.get("table_fields", []):
            key = tf.get("key", "table")
            cols = tf.get("columns", {})
            if cols:
                col_examples = ', '.join(f'"{ck}": {{"value": "...", "ref": "C1"}}' for ck in list(cols.keys())[:3])
                example_parts.append(f'    "{key}": [\n      {{{col_examples}}}\n    ]')
            else:
                example_parts.append(f'    "{key}": [\n      {{"col1": {{"value": "...", "ref": "C1"}}}}\n    ]')

        if example_parts:
            example_json = "{{\n  \"guide_extracted\": {{\n" + ",\n".join(example_parts) + "\n  }}\n}}"
        else:
            example_json = '{"guide_extracted": {"field": {"value": "...", "ref": "TAG"}}}'

        # Build field key list for schema anchoring
        all_keys = []
        for cf in wo_inner.get("common_fields", []):
            all_keys.append(cf.get("key", ""))
        for tf in wo_inner.get("table_fields", []):
            all_keys.append(tf.get("key", ""))
        field_key_list = ", ".join(f'"{k}"' for k in all_keys if k)

        prompt = f"""You are a Document Extraction Engineer.
Follow the WORK ORDER below EXACTLY. Do not deviate.

WORK ORDER:
{work_order_json}
{dynamic_hints_str}{mapping_plan_str}
TAG FORMAT GUIDE (Critical — read before processing document):
The document text contains inline tags that mark source locations:
- ^W{{id}} = Word tag. Example: "^W3 Invoice" means the word "Invoice" is tagged as W3.
- ^P{{id}} = Paragraph tag. Marks the start of a paragraph block.
- ^C{{id}} = Cell tag. Used inside markdown tables. Each cell value is preceded by its tag.

When you extract a value, find the tag nearest to that value and use its ID as "ref".
Example: If you see "^W7 2024-01-15" and extract the date, your output should be:
  {{"value": "2024-01-15", "ref": "W7"}}

For table cells: "| ^C5 KRPUS |" → {{"value": "KRPUS", "ref": "C5"}}

INSTRUCTIONS:
1. Extract values following each field's instruction in the work order.
2. For EVERY extracted value, include the ref tag ID as shown above.
3. For table fields, extract ALL rows. Do not truncate or sample.
4. If a value spans multiple tags, use the PRIMARY tag containing the core text.
5. Scan the document from START to END. Check every paragraph and every table row.
   Do NOT stop early. Footnotes, annotations, and small-print text are valid source data.
6. MULTIPLE TABLES (CRITICAL): If the document contains MULTIPLE separate physical tables that match the same table field (e.g., items continuing on page 2, or multiple distinct tables of the same type), you MUST extract rows from EVERY matching table and combine them all into the SINGLE array. DO NOT stop after extracting just the first table!

DENORMALIZATION (Table fields only):
- If the document has merged cells or hierarchical headers (one parent value
  spanning multiple child rows), REPEAT the parent value in EVERY child row.
- Every row object MUST be complete — no empty inherited fields.

NULL HANDLING (CRITICAL):
- If a field's value DOES NOT EXIST in the document, return {{"value": null, "ref": null}}.
- Do NOT guess, infer, or extrapolate from other rows or fields.
- A missing value is ALWAYS better than a wrong value.
- For table rows: if a cell is empty, return null. Do NOT copy from adjacent rows.

LANGUAGE:
- Extract values in the ORIGINAL language as they appear in the document.
- Do NOT translate unless the work order instruction explicitly says to translate.

CHECKBOXES & SELECTION MARKS (CRITICAL):
- The document text may contain `:selected:` or `:unselected:` tokens representing checkboxes.
- `:selected:` means the checkbox is CHECKED (True/Yes).
- `:unselected:` means the checkbox is UNCHECKED (False/No).
- If your instruction asks to extract ONLY selected items, you MUST filter and extract only rows/values that have a `:selected:` mark next to them. If it has `:unselected:`, IGNORE it.
- If your instruction asks for the state of a checkbox, map `:selected:` to true/Yes and `:unselected:` to false/No.

TOKEN EFFICIENCY (CRITICAL):
- Each cell MUST be ONLY: {{"value": "extracted value", "ref": "TAG_ID"}}
- Do NOT add confidence, source_text, is_uncertain, or warning_msg.
- Maximize the number of rows you output. Data COMPLETENESS is more important than verbosity.
- If a value is missing, return {{"value": null, "ref": null}}. Nothing more.

ALLOWED FIELD KEYS (output ONLY these keys, do not invent new ones):
{field_key_list}

OUTPUT FORMAT (use EXACT field keys from above):
{example_json}

INTEGRITY RULES:
{integrity_rules_str}
"""

        # Inject validation reference data if provided (Filter out terminology to save tokens)
        filtered_ref = {k: v for k, v in (reference_data or {}).items() if k in ("validation_rules", "unique_constraints")} if reference_data else None
        if filtered_ref:
            ref_json = json.dumps(filtered_ref, ensure_ascii=False, indent=2)
            MAX_REF_CHARS = getattr(settings, 'REFINER_MAX_REF_CHARS', 5000)
            if len(ref_json) > MAX_REF_CHARS:
                ref_json = ref_json[:MAX_REF_CHARS] + "\n... [TRUNCATED]"
            prompt += f"""
REFERENCE DATA (Validation Rules):
{ref_json}

INSTRUCTIONS FOR REFERENCE DATA:
- Check validation rules before outputting.
- If a field cannot be resolved even with contextual rules, return null.
"""
        return prompt

    @staticmethod
    def construct_aggregator_prompt(work_order: dict) -> str:
        """
        Phase ③: Generates the Aggregator LLM system prompt.
        Input: Work Order + Array of partial JSON results → Output: Merged JSON mapping CoT.
        """
        work_order_json = json.dumps(work_order, ensure_ascii=False, indent=2)

        prompt = f"""You are a Document Data Aggregator.
Your task is to consolidate partial data extractions from multiple workers into a single, unified JSON output.

WORK ORDER:
{work_order_json}

CONTEXT:
A massive document was split into chunks. Multiple workers extracted data from their requested chunk, producing partial JSON arrays.
You will receive a Python dictionary mapping chunk IDs to their partial `guide_extracted` JSON objects.
Example: {{ "chunk_0": {{ ... }}, "chunk_1": {{ ... }} }}

AGGREGATION RULES:
1. COMMON FIELDS (Single values):
   - Take the FIRST valid non-null value chronologically across chunks.
   - Example: If chunk_0 found "PO: 123" and chunk_1 found null, select "PO: 123".

2. TABLE FIELDS (Arrays):
   - You MUST merge all rows from all chunks into a single flat array per table field.
   - MULTI-TABLE CORRELATION: If the rows represent a continuous table split across pages, simply append them.
   - If chunk_0 extracted headers (e.g., POL, POD) but no data, and chunk_1 extracted data (e.g., KRPUS, USLAX), you MUST correlate and merge them into a single coherent row if they belong to the same logical table.
   - Remove exact duplicate rows (identical values AND identical ref tags).

3. TAG PRESERVATION (CRITICAL):
   - Every input value has a `"ref"` tag (e.g., `{{"value": "123", "ref": "W45"}}`).
   - YOU MUST PRESERVE THESE EXACT `ref` TAGS in your final output. DO NOT DROP OR CHANGE THEM.
   - If combining data artificially, keep the `ref` tag of the primary value.

4. CHAIN OF THOUGHT (REQUIRED):
   - You MUST write a `<thought_process>` before merging. 
   - State exactly why you are merging specific table rows across chunks (e.g., "Table A in chunk_0 ends at row 5, Table A in chunk_1 starts at row 6. Keys match. Appending.").

OUTPUT FORMAT:
Return ONLY a valid JSON object starting with exactly:
{{
  "thought_process": "Your step-by-step reasoning...",
  "guide_extracted": {{
    //... your merged fields
  }}
}}
"""
        return prompt

    @staticmethod
    def post_process_with_ref(engineer_output: dict, ref_map: dict) -> dict:
        """
        Phase ③: Exact bbox lookup via ref_map + uncertainty preservation.
        Replaces fuzzy matching with deterministic tag-based coordinate resolution.
        """
        def _resolve_ref(cell, ref_map):
            # 1. Handle Rich Object: { "value": "...", "ref": "^C123" }
            if isinstance(cell, dict) and "value" in cell:
                ref_id = cell.get("ref")
                value = cell.get("value")
                resolved = {"value": value}

                if ref_id and ref_id in ref_map:
                    ref_info = ref_map[ref_id]
                    resolved["bbox"] = ref_info.get("bbox")
                    conf_val = cell.get("confidence")
                    resolved["confidence"] = conf_val if conf_val is not None else (0.5 if cell.get("is_uncertain") else 1.0)
                    resolved["source_text"] = ref_info.get("text", "")
                    # If value is missing or empty, trust the ref source text?
                    # valid strategy: if LLM value is blank but ref exists, use ref text
                    if not value and ref_info.get("text"):
                         resolved["value"] = ref_info.get("text")
                elif ref_id:
                    # ref exists but not in ref_map (LLM hallucination)
                    resolved["bbox"] = None
                    resolved["page_number"] = None
                    conf_val = cell.get("confidence")
                    resolved["confidence"] = conf_val if conf_val is not None else 0.3
                else:
                    resolved["bbox"] = None
                    resolved["page_number"] = None
                    conf_val = cell.get("confidence")
                    resolved["confidence"] = conf_val if conf_val is not None else 0.0

                # Preserve uncertainty flags for UI
                if cell.get("is_uncertain"):
                    resolved["is_uncertain"] = True
                    resolved["warning_msg"] = cell.get("warning_msg", "")

                return resolved

            # 2. Handle Raw Ref String: "^C123" (LLM shortcut)
            elif isinstance(cell, str) and cell.strip().startswith("^C"):
                ref_id = cell.strip()
                if ref_id in ref_map:
                    ref_info = ref_map[ref_id]
                    return {
                        "value": ref_info.get("text", ""), # Use text from map
                        "bbox": ref_info.get("bbox"),
                        "page_number": ref_info.get("page_number"),
                        "confidence": 1.0,
                        "source_text": ref_info.get("text", ""),
                        "ref_id": ref_id # Keep trace
                    }
                else:
                     # Invalid ref string
                     return {"value": cell, "confidence": 0.2, "validation_status": "invalid_ref"}
            
            # 3. Handle Normal String / Other
            return cell

        result = {}
        guide = engineer_output.get("guide_extracted", {})

        for key, item in guide.items():
            if isinstance(item, list):
                # Table field
                rows = []
                for row in item:
                    if isinstance(row, dict):
                        processed_row = {}
                        for col_key, cell in row.items():
                            processed_row[col_key] = _resolve_ref(cell, ref_map)
                        rows.append(processed_row)
                    else:
                        rows.append(row)
                result[key] = rows
            elif isinstance(item, dict) and "value" in item:
                result[key] = _resolve_ref(item, ref_map)
            else:
                result[key] = item

        return {"guide_extracted": result}
