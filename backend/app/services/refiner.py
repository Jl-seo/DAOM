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
            MAX_REF_CHARS = settings.REFINER_MAX_REF_CHARS
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
        is_table = any(
            getattr(f, 'type', '') in TABLE_FIELD_TYPES for f in fields
        )

        if is_table:
            # Unified TABLE MODE: Always use guide_extracted root key with actual field keys.
            # This prevents data loss from _legacy_rows key mismatch.
            non_table_fields = [f for f in fields if getattr(f, 'type', 'text') not in TABLE_FIELD_TYPES]
            table_fields = [f for f in fields if getattr(f, 'type', 'text') in TABLE_FIELD_TYPES]

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
- If a field is marked **[REQUIRED]**, it must NOT be null. If the value cannot be found, make your best absolute guess or infer it.
- If a field has a **Validation Regex**, the extracted string MUST conform to that REGEX exactly. If it does not naturally conform, you must format or clean up the string so that it matches. Do not return failing strings.

**CRITICAL: DO NOT FLATTEN**
- Do NOT force header fields into every table row. Keep them separate at the root level.
- Do NOT output a single "rows" list unless the field type is explicitly a list.
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
4. VALIDATION: If a field is marked **[REQUIRED]**, you must do your best to find it. Make formatting adjustments so it strictly meets any **Validation Regex**.


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
            MAX_REF_CHARS = settings.REFINER_MAX_REF_CHARS
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
      "Copy values exactly as written, UNLESS explicitly instructed to calculate, transform, or translate by the user's field rule.",
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
- Target: entire work_order JSON under 3000 tokens.
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

SELF-VERIFICATION RULES (CRITICAL):
When extracting a value, if ANY of these conditions apply,
add "is_uncertain": true and "warning_msg": "reason" to that field:

1. AMBIGUITY: 2+ candidate values. State both candidates in warning_msg.
2. DATA CORRUPTION: Text truncated, garbled, or OCR errors (0 vs O, 1 vs l).
   Copy raw text as-is but flag it.
3. FORMAT MISMATCH: Work order expects format X but document has format Y.
4. LOW CONFIDENCE: Not fully certain for any reason. When in doubt, flag it.

If certain, do NOT include is_uncertain or warning_msg.

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
                    resolved["page_number"] = ref_info.get("page_number")
                    resolved["confidence"] = 0.5 if cell.get("is_uncertain") else 1.0
                    resolved["source_text"] = ref_info.get("text", "")
                    # If value is missing or empty, trust the ref source text?
                    # valid strategy: if LLM value is blank but ref exists, use ref text
                    if not value and ref_info.get("text"):
                         resolved["value"] = ref_info.get("text")
                elif ref_id:
                    # ref exists but not in ref_map (LLM hallucination)
                    resolved["bbox"] = None
                    resolved["page_number"] = None
                    resolved["confidence"] = 0.3
                else:
                    resolved["bbox"] = None
                    resolved["page_number"] = None
                    resolved["confidence"] = 0.0

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
