from typing import Optional, Dict, Any, List
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
        4. Output Format Instructions
        """
        
        # 1. Base Context
        prompt = f"""You are an advanced document intelligence AI.
Target Domain: {model_info.name}
Context: {model_info.description or 'General Document'}
"""

        # 2. Global Rules
        if model_info.global_rules:
            prompt += f"\nGLOBAL REFINEMENT RULES:\n{model_info.global_rules}\n"

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
        
        # Helper to flatten all words for global search if needed (optimization: only do this if local search fails)
        all_words_flat = []
        if ocr_result.get("pages"):
             for page in ocr_result["pages"]:
                for word in page.get("words", []):
                    all_words_flat.append({
                        "content": word["content"],
                        "polygon": word["polygon"],
                        "page": page["page_number"]
                    })
        
        for key, item in llm_result.items():
            if not isinstance(item, dict):
                 processed_data[key] = item # Legacy or simple format
                 continue
                 
            value = item.get("value")
            confidence = item.get("confidence", 0.0)
            source_text = item.get("source_text", "")
            
            bbox = None
            page_num = 1
            
            if source_text and all_words_flat:
                # Strategy 1: Direct Token Match (Best for single words)
                # Find best match in all words
                best_match_word = None
                best_score = 0
                
                # Check for multi-word phrase
                is_phrase = len(source_text.split()) > 1
                
                if not is_phrase:
                    # Single word matching
                    # Create a list of content strings for extraction
                    choices = [w["content"] for w in all_words_flat]
                    extracted = process.extractOne(source_text, choices, scorer=fuzz.ratio)
                    
                    if extracted:
                        match_text, score, index = extracted
                        if score >= 85: # High confidence threshold
                            best_match_word = all_words_flat[index]
                            bbox = best_match_word["polygon"]
                            page_num = best_match_word["page"]
                
                else:
                    # Strategy 2: Phrase Matching (Simple approach)
                    # We look for the first word and check if subsequent words roughly match
                    # This is complex to do perfectly without a full n-gram search, 
                    # but we can try to find the "best containing line" or similar.
                    # For MVP, we stick to finding the most significant token or using the full string check
                    
                    # Try finding the best match for the whole string against "lines" if we had them.
                    # Since we only have words, let's try to match the longest word in the phrase
                    words_in_source = source_text.split()
                    longest_word = max(words_in_source, key=len)
                    
                    choices = [w["content"] for w in all_words_flat]
                    extracted = process.extractOne(longest_word, choices, scorer=fuzz.ratio)
                    
                    if extracted:
                         match_text, score, index = extracted
                         if score >= 85:
                            # We found the "anchor" word. Use its bbox.
                            # Ideally we would expand this bbox to cover the whole phrase.
                            best_match_word = all_words_flat[index]
                            bbox = best_match_word["polygon"]
                            page_num = best_match_word["page"]

            processed_data[key] = {
                "value": value,
                "confidence": confidence,
                "source_text": source_text,
                "bbox": bbox,
                "page": page_num
            }
            
        return processed_data
