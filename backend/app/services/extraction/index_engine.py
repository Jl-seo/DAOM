"""
Index Engine — Auto-Scan Normalization
Scans all extracted string values against registered dictionaries and adds _code fields.
"""
import logging
from typing import Optional, List

from app.services.dictionary_service import DictionaryService, get_dictionary_service

logger = logging.getLogger(__name__)

# Minimum confidence score to accept a dictionary match
MATCH_THRESHOLD = 3.0  # Azure AI Search relevance score (not 0-1 normalized)


class IndexEngine:
    """
    Auto-scans extraction results against registered dictionaries.
    For each string value, checks all registered dictionary categories.
    If a match is found above threshold, adds a `_<key>_dict` metadata field.
    """
    
    def __init__(self, dict_service: Optional[DictionaryService] = None):
        self.dict_service = dict_service or get_dictionary_service()
    
    async def normalize(self, guide_extracted: dict, dict_categories: List[str]) -> dict:
        """
        Auto-scan all string values in guide_extracted against registered dictionaries.
        
        Args:
            guide_extracted: The LLM extraction result (flat or nested)
            dict_categories: List of dictionary categories to check (e.g., ["port", "charge"])
        
        Returns:
            guide_extracted with _dict metadata fields added where matches found.
        """
        if not self.dict_service.is_available or not dict_categories:
            return guide_extracted
        
        for key, val in list(guide_extracted.items()):
            # Skip internal/metadata keys
            if key.startswith("_"):
                continue
            
            if isinstance(val, list):
                # Table field — scan each row
                for row in val:
                    if not isinstance(row, dict):
                        continue
                    await self._normalize_row(row, dict_categories)
            elif isinstance(val, dict) and "value" in val:
                # Scalar field with {value, bbox, ...} structure
                cell = val.get("value")
                if isinstance(cell, str) and len(cell) >= 2:
                    match = await self._best_match(cell, dict_categories)
                    if match:
                        val["_dict"] = {
                            "code": match["code"],
                            "name": match["name"],
                            "category": match["category"],
                            "score": match["score"]
                        }
            elif isinstance(val, str) and len(val) >= 2:
                # Plain string value
                match = await self._best_match(val, dict_categories)
                if match:
                    guide_extracted[f"_{key}_dict"] = {
                        "code": match["code"],
                        "name": match["name"],
                        "category": match["category"],
                        "score": match["score"]
                    }
        
        return guide_extracted
    
    async def _normalize_row(self, row: dict, dict_categories: List[str]):
        """Normalize a single table row's string values."""
        additions = {}
        for col_key, cell_val in row.items():
            if col_key.startswith("_"):
                continue
            
            # Extract string value from cell (could be raw string or {value, bbox} dict)
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
            
            match = await self._best_match(cell_str, dict_categories)
            if match:
                additions[f"_{col_key}_dict"] = {
                    "code": match["code"],
                    "name": match["name"],
                    "category": match["category"],
                    "score": match["score"]
                }
        
        row.update(additions)
    
    async def _best_match(self, query: str, categories: List[str]) -> Optional[dict]:
        """Search across all categories and return the best match above threshold."""
        best = None
        best_score = 0.0
        
        for cat in categories:
            matches = await self.dict_service.search(query, category=cat, top_k=1)
            if matches and matches[0].score > best_score:
                best = {
                    "code": matches[0].code,
                    "name": matches[0].name,
                    "category": matches[0].category,
                    "score": matches[0].score
                }
                best_score = matches[0].score
        
        if best and best_score >= MATCH_THRESHOLD:
            return best
        return None
