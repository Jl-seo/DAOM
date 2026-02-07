from typing import Dict, Any
import json
import logging
from app.schemas.model import ExtractionModel

logger = logging.getLogger(__name__)

class RefinerEngine:
    """
    Constructs dynamic prompts based on natural language rules defined in the Studio.
    """

    @staticmethod
    def construct_prompt(model_info: ExtractionModel, language: str = "en") -> str:
        """
        Builds a comprehensive system prompt incorporating:
        1. Model Context (Description)
        2. Field-level Definitions & Rules
        3. Global Output Rules
        4. Reference Data (Phase 1)
        5. Output Format Instructions
        """

        # 1. Base Context
        prompt = f"""You are an advanced document intelligence AI.
Target Domain: {model_info.name}
Context: {model_info.description or 'General Document'}
"""

        # 2. Global Rules
        if model_info.global_rules:
            prompt += f"\nGLOBAL REFINEMENT RULES:\n{model_info.global_rules}\n"

        # 3. Reference Data (Phase 1: Structured JSON for mapping/validation)
        if model_info.reference_data:
            prompt += f"""
REFERENCE DATA (Use for value mapping, validation, and context):
{json.dumps(model_info.reference_data, ensure_ascii=False, indent=2)}

INSTRUCTIONS FOR REFERENCE DATA:
- Use codes/mappings from reference_data for value transformation (e.g., customer code → name)
- Apply validation rules specified in reference_data
- If extracted value doesn't match reference_data patterns, flag with lower confidence
- Reference data takes precedence over guessing
"""

        # 3. Field Instructions
        is_table = getattr(model_info, 'data_structure', 'data') == 'table'

        prompt += "\nREQUIRED EXTRACTION FIELDS:\n"
        for field in model_info.fields:
            prompt += f"- {field.key} ({field.label}):\n"
            prompt += f"  Description: {field.description}\n"
            if field.rules:
                prompt += f"  Refinement Rule: {field.rules}\n"
            prompt += f"  Type: {field.type}\n"

        # 4. Output Formatting & Language — branched by data_structure
        if is_table:
            # Table mode: LLM returns array of row objects
            field_keys = [f.key for f in model_info.fields]
            prompt += f"""
OUTPUT FORMAT (TABLE MODE):
This document contains TABULAR/REPEATING data. Extract ALL rows from the document.
Return a JSON object with a single key "rows" containing an array of row objects.

Each row object MUST have:
- One key per field listed above, where the value is the extracted cell value.
- "_confidence": A number 0-1 for the overall row confidence.
- "_source_text": A brief excerpt from the document identifying this row.

Extract EVERY row you find — do NOT skip rows even if some cells are empty.
For empty cells, use null as the value.

LANGUAGE INSTRUCTION:
Translate values to {language} unless the field rule says otherwise.
Do not translate '_source_text'.

Example JSON Output:
{{
  "rows": [
    {{ "{field_keys[0] if field_keys else 'col1'}": "value1", "{field_keys[1] if len(field_keys) > 1 else 'col2'}": "value2", "_confidence": 0.95, "_source_text": "Row 1 source" }},
    {{ "{field_keys[0] if field_keys else 'col1'}": "value3", "{field_keys[1] if len(field_keys) > 1 else 'col2'}": "value4", "_confidence": 0.90, "_source_text": "Row 2 source" }}
  ]
}}
"""
        else:
            # Standard mode: field-by-field extraction
            prompt += f"""
OUTPUT FORMAT:
Return a valid JSON object where keys match the field keys above.
For each field, return an object with:
- "value": The extracted and refined value.
- "confidence": A number between 0 and 1 indicating your confidence (1.0 = certain).
- "source_text": The exact text found in the document that justifies this value (for coordinate mapping).

LANGUAGE INSTRUCTION:
Translate 'value' to {language} unless the field rule says otherwise.
Do not translate 'source_text'.

Example JSON Output:
{{
  "biz_name": {{ "value": "company", "confidence": 0.95, "source_text": "Company Inc." }},
  "amount": {{ "value": 100, "confidence": 0.9, "source_text": "100.00" }}
}}
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
