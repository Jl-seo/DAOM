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

        # 3. Reference Data (Phase 1: Structured JSON for mapping/validation)
        if reference_data:
            ref_json = json.dumps(reference_data, ensure_ascii=False, indent=2)
            # SAFETY: Truncate if massive (prevent 10K+ token bloat)
            MAX_REF_CHARS = settings.REFINER_MAX_REF_CHARS
            if len(ref_json) > MAX_REF_CHARS:
                ref_json = ref_json[:MAX_REF_CHARS] + "\n... [TRUNCATED DUE TO SIZE]"
                logger.warning(f"[Refiner] Reference data truncated (size: {len(ref_json)} chars)")

            prompt += f"""
REFERENCE DATA (Use for value mapping, validation, and context):
{ref_json}

INSTRUCTIONS FOR REFERENCE DATA:
- Use codes/mappings from reference_data for value transformation (e.g., customer code → name)
- Apply validation rules specified in reference_data
- If extracted value doesn't match reference_data patterns, flag with lower confidence
- Reference data takes precedence over guessing
"""

        # 3. Field Instructions

        prompt += "\nREQUIRED EXTRACTION FIELDS:\n"
        for field in fields:
            prompt += f"- {field.key} ({field.label}):\n"
            desc = field.description
            if desc and desc.strip():
                prompt += f"  Description: {desc}\n"
            else:
                # If description is missing, don't print "Description: None"
                pass
            if field.rules:
                prompt += f"  Refinement Rule: {field.rules}\n"
            prompt += f"  Type: {field.type}\n"

        # 4. Output Formatting — branched by data_structure for token efficiency
        data_structure = get_attr(model, 'data_structure', 'data')
        is_table = data_structure == 'table' or any(
            getattr(f, 'type', '') in TABLE_FIELD_TYPES for f in fields
        )

        if is_table:
            # Unified TABLE MODE: Always use guide_extracted root key with actual field keys.
            # This prevents data loss from _legacy_rows key mismatch.
            non_table_fields = [f for f in fields if getattr(f, 'type', 'text') not in TABLE_FIELD_TYPES]
            table_fields = [f for f in fields if getattr(f, 'type', 'text') in TABLE_FIELD_TYPES]

            example_parts = []
            for f in non_table_fields:
                example_parts.append(f'    "{f.key}": "value"')
            
            for f in table_fields:
                example_parts.append(f'    "{f.key}": [\n      {{ "col1": "val1", "col2": "val2" }}\n    ]')

            example_json = "{\n  \"guide_extracted\": {\n" + ",\n".join(example_parts) + "\n  }\n}"

            prompt += f"""
OUTPUT INSTRUCTIONS (TABLE MODE):
You must extract ALL rows from the document. Do NOT truncate or sample.

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
   - Do NOT invent new keys.

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

        processed_data = {}

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

        for key, item in llm_result.items():
            if not isinstance(item, dict):
                 processed_data[key] = item # Legacy or simple format
                 continue

            value = item.get("value")
            confidence = item.get("confidence", 0.0)
            source_text = item.get("source_text", "")

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
                    logger.warning(f"[PostProcess] Fuzzy match error for '{key}': {e}")

            processed_data[key] = {
                "value": value,
                "confidence": confidence,
                "source_text": source_text,
                "bbox": bbox,
                "page": page_num
            }

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
        data_structure = get_attr(model, "data_structure", "data")
        fields = model.fields

        # Build fields JSON for the prompt
        fields_json = json.dumps([
            {
                "key": f.key,
                "label": f.label,
                "description": f.description,
                "rules": f.rules,
                "type": f.type
            }
            for f in fields
        ], ensure_ascii=False, indent=2)

        ref_data_section = ""
        if reference_data:
            ref_json = json.dumps(reference_data, ensure_ascii=False, indent=2)
            MAX_REF_CHARS = settings.REFINER_MAX_REF_CHARS
            if len(ref_json) > MAX_REF_CHARS:
                ref_json = ref_json[:MAX_REF_CHARS] + "\n... [TRUNCATED]"
            ref_data_section = f"\nREFERENCE DATA:\n{ref_json}\n"

        calibration_section = ""
        if global_rules:
            calibration_section = f"\nCALIBRATION RULES (from admin):\n{global_rules}\n"

        prompt = f"""You are a Document Extraction Architect.

Given an extraction model schema and calibration rules, generate a WORK ORDER
that an extraction engineer will follow to extract data from a document.

MODEL: {name}
DOMAIN: {description or 'General Document'}
DATA STRUCTURE: {data_structure}

MODEL SCHEMA:
{fields_json}
{calibration_section}{ref_data_section}
OUTPUT: A JSON object with this structure:
{{
  "work_order": {{
    "document_type": "brief description",
    "extraction_mode": "data" or "table",
    "common_fields": [
      {{"key": "field_key", "instruction": "1-2 sentence extraction command", "expected_format": "type"}}
    ],
    "table_fields": [
      {{
        "key": "field_key",
        "instruction": "1-2 sentence extraction command",
        "columns": {{
          "col_key": {{"instruction": "command", "source_hint": "likely header variations"}}
        }},
        "rules": ["rule1"]
      }}
    ],
    "integrity_rules": [
      "Copy values exactly as written. No conversion/calculation/translation.",
      "Missing values must be null."
    ]
  }}
}}

CRITICAL:
- Column keys MUST use the EXACT field keys from the schema. Do NOT rename.
- The work order is for an AI engineer, not a human. Be precise and unambiguous.

STYLE CONSTRAINTS (MANDATORY):
- Be CONCISE. Each instruction MUST be 1-2 sentences max.
- Do NOT write prose or rationale. Write commands.
- Do NOT add examples beyond what the schema provides.
- Do NOT repeat integrity rules per field — use the shared integrity_rules array.
- Target: entire work_order JSON under 2000 tokens.
"""
        return prompt

    @staticmethod
    def construct_engineer_prompt(work_order: dict) -> str:
        """
        Phase ②: Generates the Engineer LLM system prompt.
        Input: Work Order + tagged text → Output: JSON with ref tags.
        """
        work_order_json = json.dumps(work_order, ensure_ascii=False, indent=2)

        # Extract integrity rules from work order
        integrity_rules = work_order.get("work_order", work_order).get("integrity_rules", [])
        integrity_rules_str = "\n".join(f"- {r}" for r in integrity_rules) if integrity_rules else "- Extract values exactly as written."

        prompt = f"""You are a Document Extraction Engineer.
Follow the WORK ORDER below EXACTLY. Do not deviate.

WORK ORDER:
{work_order_json}

INSTRUCTIONS:
1. Extract values following each field's instruction in the work order.
2. For EVERY extracted value, include the tag ID (e.g., ^C5 → "ref": "C5")
   that corresponds to the source location in the document.
3. For table fields, extract ALL rows. Do not truncate.
4. If a value spans multiple tags, use the PRIMARY tag containing the most relevant text.

NULL HANDLING (CRITICAL):
- If a field's value DOES NOT EXIST in the document, return {{"value": null, "ref": null}}.
- Do NOT guess, infer, or extrapolate from other rows or fields.
- A missing value is ALWAYS better than a wrong value.
- For table rows: if a cell is empty, return null. Do NOT copy from adjacent rows.

SELF-VERIFICATION RULES (CRITICAL):
When extracting a value, if ANY of these conditions apply,
add "is_uncertain": true and "warning_msg": "reason" to that field:

1. AMBIGUITY: 2+ candidate values. State both candidates in warning_msg.
2. DATA CORRUPTION: Text truncated, garbled, or OCR errors (0 vs O, 1 vs l).
   Copy raw text as-is but flag it.
3. FORMAT MISMATCH: Work order expects format X but document has format Y.
4. LOW CONFIDENCE: Not fully certain for any reason. When in doubt, flag it.

If certain, do NOT include is_uncertain or warning_msg.

OUTPUT FORMAT:
{{
  "guide_extracted": {{
    "field_key": {{"value": "v", "ref": "TAG_ID"}},
    "uncertain_field": {{"value": "v", "ref": "TAG", "is_uncertain": true, "warning_msg": "reason"}},
    "table_key": [
      {{"col1": {{"value": "v", "ref": "TAG"}}, "col2": {{"value": "v", "ref": "TAG"}}}}
    ]
  }}
}}

INTEGRITY RULES:
{integrity_rules_str}
"""
        return prompt

    @staticmethod
    def post_process_with_ref(engineer_output: dict, ref_map: dict) -> dict:
        """
        Phase ③: Exact bbox lookup via ref_map + uncertainty preservation.
        Replaces fuzzy matching with deterministic tag-based coordinate resolution.
        """
        def _resolve_ref(cell, ref_map):
            if not isinstance(cell, dict) or "value" not in cell:
                return cell

            ref_id = cell.get("ref")
            value = cell.get("value")
            resolved = {"value": value}

            if ref_id and ref_id in ref_map:
                ref_info = ref_map[ref_id]
                resolved["bbox"] = ref_info.get("bbox")
                resolved["page_number"] = ref_info.get("page_number")
                resolved["confidence"] = 0.5 if cell.get("is_uncertain") else 1.0
                resolved["source_text"] = ref_info.get("text", "")
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
