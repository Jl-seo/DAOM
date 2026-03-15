"""
Vibe Dictionary Background Service — AI synonym auto-discovery.

Uses the unified reference_data container (entry_type='synonym') instead of
the deprecated vibe_dictionaries container.
"""
import logging
import json
import hashlib
from typing import Dict, Any, List, Set, Optional
from datetime import datetime

from app.services.llm_service import AzureOpenAIService
from app.schemas.model import VibeDictionarySource
from app.services.models import get_model_by_id
from app.db.cosmos import get_reference_data_container

logger = logging.getLogger(__name__)

async def generate_vibe_dictionary_async(model_id: str, raw_extracted: Dict[str, Any]):
    """
    Background Task: Evaluates raw extracted data against the Model's Vibe Dictionary Persona.
    If it finds valid synonyms for existing standard codes, it writes them into the
    reference_data container as unverified AI_GENERATED synonym entries for Admin review.
    """
    try:
        model = await get_model_by_id(model_id)
        if not model or not getattr(model, "vibe_dictionary", None):
            return
            
        vibe_config = model.vibe_dictionary
        if isinstance(vibe_config, dict):
            vibe_config_enabled = vibe_config.get("enabled", False)
            target_fields = vibe_config.get("target_fields", [])
            persona_prompt = vibe_config.get("persona_prompt", "")
        else:
            vibe_config_enabled = vibe_config.enabled
            target_fields = vibe_config.target_fields
            persona_prompt = vibe_config.persona_prompt
            
        if not vibe_config_enabled or not target_fields or not persona_prompt:
            return

        container = get_reference_data_container()
        if not container:
            logger.error("[VibeDictionary] reference_data container not configured.")
            return

        # 1. Fetch existing synonym entries for this model from reference_data
        query = "SELECT * FROM c WHERE c.entry_type = 'synonym' AND c.model_id IN (@model_id, '__global__')"
        parameters = [{"name": "@model_id", "value": model_id}]
        
        try:
            existing_entries = [v async for v in container.query_items(
                query=query, parameters=parameters
            )]
        except Exception as e:
            logger.error(f"[VibeDictionary] Failed to fetch synonym entries: {e}")
            existing_entries = []

        # Build a lookup map to collect existing standards and prevent duplicates
        ref_data: Dict[str, Dict[str, Any]] = {}
        for entry in existing_entries:
            field = entry.get("field_name")
            raw_val = entry.get("raw_val")
            standard_val = entry.get("value")
            
            if not field or not raw_val or not standard_val:
                continue
                
            if field not in ref_data:
                ref_data[field] = {}
            ref_data[field][raw_val] = entry
        
        # 2. Collect Raw Data that isn't already mapped
        unmapped_candidates: Dict[str, Set[str]] = {}
        _collect_unmapped(raw_extracted, target_fields, ref_data, unmapped_candidates)
        
        candidates_json = {k: list(v) for k, v in unmapped_candidates.items() if v}
        
        if not candidates_json:
            logger.info(f"[VibeDictionary] No new unmapped candidates found for model {model_id}.")
            return
            
        # 3. Call LLM to evaluate candidates
        llm = AzureOpenAIService(deployment_name=getattr(model, "extractor_llm", "gpt-4o") or "gpt-4o")
        
        standard_codes_map = _get_standard_codes(ref_data, target_fields)
        
        system_prompt = f"""{persona_prompt}
        
You are the Vibe Dictionary Generator. 
Your job is to look at UNMAPPED RAW text extracted via OCR, and reasonably deduce if they are typos, abbreviations, or synonyms of existing STANDARD CODES.

Existing Standard Codes per field (Your Dictionary Target Values):
{json.dumps(standard_codes_map, ensure_ascii=False, indent=2)}

Unmapped Candidates found in the recent document:
{json.dumps(candidates_json, ensure_ascii=False, indent=2)}

Respond ONLY with a JSON dictionary of NEW MAPPINGS you are confident about.
If the candidate is clearly garbage or unrelated, do not map it.
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
            user_prompt="Evaluate the candidates against the standard codes and return the JSON mapping.",
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        try:
            new_mappings = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"[VibeDictionary] LLM returned invalid JSON: {response}")
            return
        
        if not new_mappings:
            logger.info(f"[VibeDictionary] LLM found no valid mappings for candidates: {candidates_json}")
            return
            
        # 4. Upsert evaluated new mappings into unified reference_data container
        updates_made = False
        for field, mappings in new_mappings.items():
            if not isinstance(mappings, dict): continue
            if field not in target_fields: continue
            
            for raw_val, standard_code in mappings.items():
                if field in ref_data and raw_val in ref_data[field]:
                    # Synonym already mapped — increment hit count
                    existing = ref_data[field][raw_val]
                    existing["hit_count"] = existing.get("hit_count", 0) + 1
                    try:
                        await container.upsert_item(body=existing)
                        logger.info(f"[VibeDictionary] Hit count incremented: {field} | '{raw_val}' -> {existing['hit_count']} hits")
                        updates_made = True
                    except Exception as e:
                        logger.error(f"[VibeDictionary] Failed to update hit_count for '{raw_val}': {e}")
                else:
                    # Brand new synonym candidate — store as entry_type=synonym
                    doc_id = hashlib.md5(
                        f"{model_id}_synonym_{field}_{raw_val}".encode()
                    ).hexdigest()
                    
                    doc = {
                        "id": doc_id,
                        "model_id": model_id,
                        "category": "vibe",
                        "entry_type": "synonym",
                        "field_name": field,
                        "raw_val": raw_val,
                        "value": standard_code,
                        "standard_code": standard_code,
                        "standard_label": raw_val,
                        "aliases": [raw_val.lower()],
                        "source": VibeDictionarySource.AI_GENERATED.value,
                        "is_verified": False,
                        "hit_count": 1,
                        "extra": {},
                        "created_at": datetime.utcnow().isoformat()
                    }
                    try:
                        await container.upsert_item(body=doc)
                        logger.info(f"[VibeDictionary] Auto-Learned synonym saved: {field} | '{raw_val}' -> '{standard_code}'")
                        updates_made = True
                    except Exception as e:
                        logger.error(f"[VibeDictionary] Failed to insert new synonym '{raw_val}': {e}")

        if updates_made:
            logger.info(f"[VibeDictionary] Successfully processed pipeline for model {model_id}")
            
    except Exception as e:
        logger.error(f"[VibeDictionary] Background generation failed: {e}")

def _collect_unmapped(data: Any, target_fields: List[str], ref_data: Dict[str, Dict[str, Any]], results: Dict[str, Set[str]]):
    """Recursively identify raw extracted values that belong to target_fields but missed the existing dictionary."""
    if isinstance(data, dict):
        for key, node in data.items():
            if isinstance(node, dict) and "value" in node:
                if isinstance(node["value"], list):
                    for row in node["value"]:
                        _collect_unmapped(row, target_fields, ref_data, results)
                else:
                    if key in target_fields:
                        is_modified = node.get("_modifier", "").startswith("Vibe Dictionary") or node.get("_modifier", "") == "Dictionary"
                        raw_val = str(node.get("value", "")).strip()
                        if not is_modified and raw_val:
                            if key not in ref_data or raw_val not in ref_data[key]:
                                if key not in results:
                                    results[key] = set()
                                results[key].add(raw_val)
            elif isinstance(node, dict):
                _collect_unmapped(node, target_fields, ref_data, results)
    elif isinstance(data, list):
        for item in data:
            _collect_unmapped(item, target_fields, ref_data, results)

def _get_standard_codes(ref_data: Dict[str, Dict[str, Any]], target_fields: List[str]) -> Dict[str, List[str]]:
    """Extract standard target values (codes) from the current fetched dictionary items."""
    standards = {}
    for field in target_fields:
        if field in ref_data:
            field_dict = ref_data[field]
            vals = set()
            for k, entry in field_dict.items():
                if "value" in entry:
                    vals.add(entry["value"])
            standards[field] = list(vals)
    return standards
