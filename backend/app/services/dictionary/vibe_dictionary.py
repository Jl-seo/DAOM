import logging
import json
from typing import Dict, Any, List, Set

from app.services.llm_service import AzureOpenAIService
from app.schemas.model import VibeDictionarySource
from app.services.models import get_model_by_id, update_model

logger = logging.getLogger(__name__)

async def generate_vibe_dictionary_async(model_id: str, raw_extracted: Dict[str, Any]):
    """
    Background Task: Evaluates raw extracted data against the Model's Vibe Dictionary Persona.
    If it finds valid synonyms for existing standard codes, it updates the Model's reference_data.
    """
    try:
        model = await get_model_by_id(model_id)
        if not model or not getattr(model, "vibe_dictionary", None):
            return
            
        vibe_config = model.vibe_dictionary
        # Need to handle dict conversion if vibe_dictionary is a raw dict from DB
        if isinstance(vibe_config, dict):
            # Convert to object-like access for convenience, or just use dict logic
            vibe_config_enabled = vibe_config.get("enabled", False)
            target_fields = vibe_config.get("target_fields", [])
            persona_prompt = vibe_config.get("persona_prompt", "")
        else:
            vibe_config_enabled = vibe_config.enabled
            target_fields = vibe_config.target_fields
            persona_prompt = vibe_config.persona_prompt
            
        if not vibe_config_enabled or not target_fields or not persona_prompt:
            return

        ref_data = getattr(model, "reference_data", {}) or {}
        
        # 1. Collect Raw Data that isn't already mapped
        unmapped_candidates: Dict[str, Set[str]] = {}
        _collect_unmapped(raw_extracted, target_fields, ref_data, unmapped_candidates)
        
        # Standardize iterables for JSON serialization
        candidates_json = {k: list(v) for k, v in unmapped_candidates.items() if v}
        
        if not candidates_json:
            logger.info(f"[VibeDictionary] No new unmapped candidates found for model {model_id}.")
            return
            
        # 2. Call LLM to evaluate candidates
        llm = AzureOpenAIService(deployment_name=getattr(model, "extractor_llm", "gpt-4o") or "gpt-4o")
        
        system_prompt = f"""{persona_prompt}
        
You are the Vibe Dictionary Generator. 
Your job is to look at UNMAPPED RAW text extracted via OCR, and reasonably deduce if they are typos, abbreviations, or synonyms of existing STANDARD CODES.

Existing Standard Codes per field (Your Dictionary):
{json.dumps(_get_standard_codes(ref_data, target_fields), ensure_ascii=False, indent=2)}

Unmapped Candidates found in the recent document:
{json.dumps(candidates_json, ensure_ascii=False, indent=2)}

Respond ONLY with a JSON dictionary of NEW MAPPINGS you are confident about.
If the candidate is clearly garbage, do not map it.
Format:
{{
    "FIELD_NAME": {{
        "RAW_TYPO": "STANDARD_CODE"
    }}
}}
If no matches are found, return {{}}.
"""
        
        response = await llm.generate_response(
            system_prompt=system_prompt,
            user_prompt="Evaluate the candidates and return the JSON mapping.",
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        new_mappings = json.loads(response)
        
        if not new_mappings:
            logger.info(f"[VibeDictionary] LLM found no valid mappings for candidates: {candidates_json}")
            return
            
        # 3. Update Model in Cosmos DB
        updates_made = False
        for field, mappings in new_mappings.items():
            if not isinstance(mappings, dict): continue
            if field not in target_fields: continue
            
            if field not in ref_data:
                ref_data[field] = {}
                
            for raw_val, standard_code in mappings.items():
                if raw_val not in ref_data[field]:
                    ref_data[field][raw_val] = {
                        "value": standard_code,
                        "source": VibeDictionarySource.AI_GENERATED.value,
                        "is_verified": False
                    }
                    updates_made = True
                    logger.info(f"[VibeDictionary] Auto-Learned synonym: {field} | '{raw_val}' -> '{standard_code}'")

        if updates_made:
            await update_model(model_id, {"reference_data": ref_data})
            logger.info(f"[VibeDictionary] Successfully updated DB dictionary for model {model_id}")
            
    except Exception as e:
        logger.error(f"[VibeDictionary] Background generation failed: {e}")

def _collect_unmapped(data: Any, target_fields: List[str], ref_data: Dict[str, Any], results: Dict[str, Set[str]]):
    """Recursively identify raw extracted values that belong to target_fields but missed the dictionary."""
    if isinstance(data, dict):
        for key, node in data.items():
            if isinstance(node, dict) and "value" in node:
                if isinstance(node["value"], list):
                    for row in node["value"]:
                        _collect_unmapped(row, target_fields, ref_data, results)
                else:
                    if key in target_fields:
                        # Check if it was modified by the dictionary
                        is_modified = node.get("_modifier", "").startswith("Vibe Dictionary") or node.get("_modifier", "") == "Dictionary"
                        if not is_modified:
                            # It's an unmapped raw value
                            raw_val = str(node.get("value", "")).strip()
                            if raw_val:
                                if key not in results:
                                    results[key] = set()
                                results[key].add(raw_val)
            elif isinstance(node, dict):
                _collect_unmapped(node, target_fields, ref_data, results)

def _get_standard_codes(ref_data: Dict[str, Any], target_fields: List[str]) -> Dict[str, List[str]]:
    """Extract standard target values (codes) from the current dictionary structure."""
    standards = {}
    for field in target_fields:
        if field in ref_data:
            field_dict = ref_data[field]
            vals = set()
            for k, v in field_dict.items():
                if isinstance(v, dict) and "value" in v:
                    vals.add(v["value"])
                else:
                    vals.add(str(v))
            standards[field] = list(vals)
    return standards
