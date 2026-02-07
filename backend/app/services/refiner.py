from typing import Optional, Dict, Any, List
import json
from app.schemas.model import ExtractionModel

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
        prompt += "\nREQUIRED EXTRACTION FIELDS:\n"
        for field in model_info.fields:
            prompt += f"- {field.key} ({field.label}):\n"
            prompt += f"  Description: {field.description}\n"
            if field.rules:
                prompt += f"  Refinement Rule: {field.rules}\n"
            prompt += f"  Type: {field.type}\n"

        # 4. Output Formatting & Language
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
        if ocr_result.get("pages"):
             for page in ocr_result["pages"]:
                for word in page.get("words", []):
                    idx = len(all_words_flat)
                    all_words_flat.append({
                        "content": word["content"],
                        "polygon": word["polygon"],
                        "page": page["page_number"]
                    })
                    word_choices[idx] = word["content"]
        
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
                best_match_word = None
                
                # Check for multi-word phrase
                is_phrase = len(source_text.split()) > 1
                search_term = source_text if not is_phrase else max(source_text.split(), key=len)
                
                try:
                    # extractOne with dict returns (match_text, score, key)
                    extracted = process.extractOne(search_term, word_choices, scorer=fuzz.ratio)
                    
                    if extracted and len(extracted) >= 3:
                        match_text, score, match_idx = extracted
                        if score >= 85:
                            best_match_word = all_words_flat[match_idx]
                            bbox = best_match_word["polygon"]
                            page_num = best_match_word["page"]
                    elif extracted and len(extracted) == 2:
                        # Fallback: (match_text, score) without index
                        match_text, score = extracted
                        if score >= 85:
                            # Find the matching word by content
                            for w in all_words_flat:
                                if w["content"] == match_text:
                                    bbox = w["polygon"]
                                    page_num = w["page"]
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
