from typing import Dict, Any
import json
import logging
from app.schemas.model import ExtractionModel
from app.core.config import settings

logger = logging.getLogger(__name__)

class RefinerEngine:
    """
    Constructs dynamic prompts based on natural language rules defined in the Studio.
    """

    @staticmethod
    def construct_prompt(model_info: Any, language: str = "en") -> str:
        """
        Builds a comprehensive system prompt incorporating:
        1. Model Context (Description)
        2. Field-level Definitions & Rules
        3. Global Output Rules
        4. Reference Data (Phase 1)
        5. Output Format Instructions
        Robust to both Pydantic model and Dict input.
        """
        # Helper to access attributes safely
        def get_attr(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        name = get_attr(model_info, "name", "Unknown Model")
        description = get_attr(model_info, "description", None)
        global_rules = get_attr(model_info, "global_rules", None)
        reference_data = get_attr(model_info, "reference_data", None)
        fields = get_attr(model_info, "fields", [])

        # 1. Base Context
        prompt = f"""You are an advanced document intelligence AI.
Target Domain: {name}
Context: {description or 'General Document'}
"""

        # 2. Global Rules
        if global_rules:
            prompt += f"\nGLOBAL REFINEMENT RULES:\n{global_rules}\n"

        # 3. Reference Data (Phase 1: Structured JSON for mapping/validation)
        if model_info.reference_data:
            ref_json = json.dumps(model_info.reference_data, ensure_ascii=False, indent=2)
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
        for field in model_info.fields:
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
        data_structure = getattr(model_info, 'data_structure', 'data')
        is_table = data_structure == 'table' or any(
            getattr(f, 'type', '') == 'table' for f in model_info.fields
        )

        if is_table:
            # TABLE MODE: Compact format to maximize row count within token budget.
            # Per-cell {value, confidence, source_text} wrappers waste ~80% of tokens.
            prompt += f"""
OUTPUT INSTRUCTIONS (TABLE MODE):
You must extract ALL rows from the document. Do NOT truncate or sample.

Return a JSON object where the output key is "rows" (list of objects).
Each object in the list must represent a row.
**CRITICAL**: Use the exact keys defined in the 'REQUIRED EXTRACTION FIELDS' section above.
Do NOT wrap each cell in {{"value": ..., "confidence": ...}} — output flat values directly.

Example format:
{{
  "rows": [
    {{"field_key_1": "value1", "field_key_2": "value2"}},
    ...
  ]
}}

CRITICAL: Extract EVERY row. Missing rows is unacceptable.

LANGUAGE: Translate values to {language} unless the field rule says otherwise.
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
Translate "value" to {language} unless the field rule says otherwise.
Do NOT translate "source_text".
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
