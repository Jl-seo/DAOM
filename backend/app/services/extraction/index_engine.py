"""
Index Engine — Auto-Scan Normalization (v2: Pre-load + In-Memory Match)
Scans all extracted string values against registered dictionaries.
When a match is found, REPLACES the original value with the matched code in-place.
Match metadata (_dict_evidence) is stored separately for UI tooltip/evidence display.

Performance: Pre-loads entire dictionary per category ONCE, then matches in-memory.
  Before: 50 rows × 5 cols × 3 categories = 750 API calls (~37s)
  After:  3 API calls (1 per category) + in-memory matching (~0.3s)
"""
import logging
from typing import Optional, List, Dict
from thefuzz import fuzz

from app.services.dictionary_service import DictionaryService, get_dictionary_service

logger = logging.getLogger(__name__)

# Minimum similarity ratio (0-1) to accept a dictionary match
MATCH_THRESHOLD = 0.6


class IndexEngine:
    """
    Auto-scans extraction results against registered dictionaries.
    Pre-loads all dictionary entries into memory, then matches in-place.
    """

    def __init__(self, dict_service: Optional[DictionaryService] = None):
        self.dict_service = dict_service or get_dictionary_service()
        self._cache: Dict[str, List[dict]] = {}  # category -> [{code, name, extra}, ...]

    async def _preload_categories(self, model_id: str, categories: List[str]):
        """Pre-load all dictionary entries for given categories into memory."""
        for cat in categories:
            if cat in self._cache:
                continue
            try:
                # Single API call: fetch ALL entries for this category (removed top_k limit)
                matches = await self.dict_service.search("*", model_id=model_id, category=cat, top_k=100000)
                self._cache[cat] = [
                    {"code": m.code, "name": m.name, "extra": m.extra}
                    for m in matches
                ]
                logger.info(f"[IndexEngine] Pre-loaded {len(self._cache[cat])} entries for category '{cat}'")
            except Exception as e:
                logger.error(f"[IndexEngine] Failed to pre-load category '{cat}': {e}")
                self._cache[cat] = []

    async def normalize(self, guide_extracted: dict, model_id: str, dict_categories: List[str]) -> dict:
        """
        Auto-scan all string values in guide_extracted against registered dictionaries.

        Args:
            guide_extracted: The LLM extraction result (flat or nested)
            model_id: Model ID for scoping dictionaries
            dict_categories: List of dictionary categories to check (e.g., ["port", "charge"])

        Returns:
            guide_extracted with values replaced by matched codes where found.
            A _dict_evidence key is added with match details.
        """
        if not self.dict_service.is_available or not dict_categories:
            return guide_extracted

        # Step 1: Pre-load ALL dictionary entries (1 API call per category)
        await self._preload_categories(model_id, dict_categories)

        # Step 2: Thread-pool processing to avoid blocking asyncio event loop
        import asyncio
        
        def _cpu_bound_normalization():
            evidence = {}
            # Cache unique cell strings to avoid redundant O(N^2) fuzzy matching
            matched_cache = {} 
            
            # Helper inside thread
            def _get_match_from_cache(query: str):
                if query not in matched_cache:
                    matched_cache[query] = self._best_match_memory(query, dict_categories)
                return matched_cache[query]

            def _normalize_row_local(row_dict: dict, row_path: str):
                for col_key in list(row_dict.keys()):
                    if col_key.startswith("_"):
                        continue
                    cell_val = row_dict[col_key]
                    
                    if isinstance(cell_val, dict):
                        cell_str = str(cell_val.get("value", ""))
                    elif isinstance(cell_val, str):
                        cell_str = cell_val
                    else:
                        continue
                        
                    if len(cell_str) < 2:
                        continue
                        
                    # Skip obviously numeric values
                    try:
                        float(cell_str.replace(",", ""))
                        continue
                    except (ValueError, AttributeError):
                        pass

                    match = _get_match_from_cache(cell_str)
                    if match:
                        original = cell_str
                        if isinstance(cell_val, dict):
                            cell_val["value"] = match["code"]
                        else:
                            row_dict[col_key] = match["code"]

                        evidence[f"{row_path}.{col_key}"] = {
                            "original": original,
                            "matched_code": match["code"],
                            "matched_name": match["name"],
                            "category": match["category"],
                            "score": match["score"]
                        }

            for key, val in list(guide_extracted.items()):
                if key.startswith("_"):
                    continue

                if isinstance(val, list):
                    # Table field — scan each row
                    for row_idx, row in enumerate(val):
                        if not isinstance(row, dict):
                            continue
                        _normalize_row_local(row, f"{key}[{row_idx}]")
                elif isinstance(val, dict) and "value" in val:
                    cell = val.get("value")
                    if isinstance(cell, str) and len(cell) >= 2:
                        match = _get_match_from_cache(cell)
                        if match:
                            original = val["value"]
                            val["value"] = match["code"]
                            evidence[key] = {
                                "original": original,
                                "matched_code": match["code"],
                                "matched_name": match["name"],
                                "category": match["category"],
                                "score": match["score"]
                            }
                elif isinstance(val, str) and len(val) >= 2:
                    match = _get_match_from_cache(val)
                    if match:
                        original = val
                        guide_extracted[key] = match["code"]
                        evidence[key] = {
                            "original": original,
                            "matched_code": match["code"],
                            "matched_name": match["name"],
                            "category": match["category"],
                            "score": match["score"]
                        }

            if evidence:
                guide_extracted["_dict_evidence"] = evidence
                
            return guide_extracted

        # Run CPU heavy fuzzy matching in background thread
        guide_extracted = await asyncio.to_thread(_cpu_bound_normalization)

        return guide_extracted

    def _best_match_memory(self, query: str, categories: List[str]) -> Optional[dict]:
        """
        In-memory fuzzy match against pre-loaded dictionary entries.
        No API calls — pure CPU string comparison.
        """
        best = None
        best_score = 0.0
        query_lower = query.lower().strip()

        for cat in categories:
            entries = self._cache.get(cat, [])
            for entry in entries:
                # Check exact match first (fastest)
                code_lower = entry["code"].lower().strip()
                name_lower = entry["name"].lower().strip()

                if query_lower == code_lower or query_lower == name_lower:
                    return {
                        "code": entry["code"],
                        "name": entry["name"],
                        "category": cat,
                        "score": 1.0
                    }

                # Check containment
                if query_lower in name_lower or name_lower in query_lower:
                    score = 0.85
                elif query_lower in code_lower or code_lower in query_lower:
                    score = 0.8
                else:
                    # Fuzzy match using thefuzz token_set_ratio + ratio
                    score_name = max(
                        fuzz.token_set_ratio(query_lower, name_lower) / 100.0,
                        fuzz.ratio(query_lower, name_lower) / 100.0
                    )
                    score_code = fuzz.ratio(query_lower, code_lower) / 100.0
                    score = max(score_name, score_code)

                if score > best_score:
                    best = {
                        "code": entry["code"],
                        "name": entry["name"],
                        "category": cat,
                        "score": score
                    }
                    best_score = score

        if best and best_score >= MATCH_THRESHOLD:
            return best
        return None
