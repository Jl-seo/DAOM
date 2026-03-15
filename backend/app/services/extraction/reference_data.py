"""
Reference Data Service — Cosmos DB + In-Memory Fuzzy Matching
Unified dictionary/normalization service that replaces Azure AI Search.

Architecture:
  1. Admin uploads Excel → data stored in Cosmos DB (reference_data container)
  2. At extraction time, data is loaded into memory once per model+category
  3. In-memory fuzzy matching via thefuzz (no external API calls)
  
Performance: 
  - 1 Cosmos read per category (cached), then pure CPU string matching
  - 10K entries matched in ~0.3s vs Azure AI Search at ~37s
"""
import logging
import io
import hashlib
import asyncio
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

import pandas as pd
from thefuzz import fuzz

logger = logging.getLogger(__name__)

# Minimum similarity ratio (0-1) to accept a fuzzy match
FUZZY_MATCH_THRESHOLD = 0.6


class ReferenceEntry:
    """A single reference data entry with multiple matchable aliases."""
    def __init__(self, id: str, model_id: str, category: str, 
                 standard_code: str, standard_label: str,
                 aliases: List[str], source: str = "ADMIN",
                 is_verified: bool = True, hit_count: int = 0, 
                 extra: Dict[str, str] = None):
        self.id = id
        self.model_id = model_id
        self.category = category
        self.standard_code = standard_code
        self.standard_label = standard_label
        self.aliases = aliases  # All matchable values (including code and label)
        self.source = source
        self.is_verified = is_verified
        self.hit_count = hit_count
        self.extra = extra or {}


class MatchResult:
    """Result of a reference data match."""
    def __init__(self, standard_code: str, standard_label: str, 
                 category: str, score: float, matched_alias: str,
                 extra: Dict[str, str] = None):
        self.standard_code = standard_code
        self.standard_label = standard_label
        self.category = category
        self.score = score
        self.matched_alias = matched_alias
        self.extra = extra or {}


class ReferenceDataService:
    """
    Unified reference data service using Cosmos DB for storage
    and in-memory fuzzy matching for normalization.
    
    Replaces:
      - DictionaryService (Azure AI Search) — storage + search
      - IndexEngine (dead code) — in-memory fuzzy matching
    
    Keeps:
      - VibeDictionary — auto-learning (separate concern, uses its own container)
    """
    
    def __init__(self):
        self._cache: Dict[str, List[ReferenceEntry]] = {}  # "model_id:category" -> entries
        self._cache_loaded: Set[str] = set()
    
    def _cache_key(self, model_id: str, category: str) -> str:
        return f"{model_id}:{category}"
    
    def _get_container(self):
        """Get the Cosmos DB reference_data container."""
        from app.db.cosmos import get_reference_data_container
        container = get_reference_data_container()
        if not container:
            logger.warning("[ReferenceData] Container 'reference_data' not available")
        return container
    
    @property
    def is_available(self) -> bool:
        return self._get_container() is not None

    # ──────────────────────────────────────────────
    # CRUD Operations
    # ──────────────────────────────────────────────

    async def upload_from_excel(self, file_bytes: bytes, model_id: str, 
                                 category: str, filename: str = "") -> dict:
        """
        Upload Excel/CSV to Cosmos DB as reference data entries.
        First column = standard_code, second column = standard_label,
        remaining columns = additional aliases for matching.
        """
        container = self._get_container()
        if not container:
            return {"error": "Reference data service not configured", "count": 0}

        # 1. Parse Excel
        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_bytes))
            else:
                df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return {"error": f"파일 파싱 실패: {e}", "count": 0}

        if df.empty or len(df.columns) < 1:
            return {"error": "빈 파일이거나 열이 부족합니다", "count": 0}

        # 2. Map columns: col[0]=code, col[1]=label, rest=aliases
        col_names = list(df.columns)
        code_col = col_names[0]
        label_col = col_names[1] if len(col_names) > 1 else code_col
        alias_cols = col_names[2:] if len(col_names) > 2 else []

        # 3. Build documents
        documents = []
        for idx, row in df.iterrows():
            code = str(row.get(code_col, "")).strip()
            if not code:
                continue
                
            label = str(row.get(label_col, code)).strip()
            
            # Collect all aliases (code + label + extra columns)
            aliases = {code.lower(), label.lower()}
            for ac in alias_cols:
                val = row.get(ac)
                if pd.notna(val) and str(val).strip():
                    aliases.add(str(val).strip().lower())
            
            row_str = "|".join(str(v) for v in row.values)
            doc_id = hashlib.md5(f"{model_id}_{category}_{idx}_{row_str}".encode()).hexdigest()
            
            # Build extra fields from remaining columns
            extra = {}
            for col in col_names:
                val = row.get(col)
                if pd.notna(val):
                    extra[str(col)] = str(val).strip()
            
            doc = {
                "id": doc_id,
                "model_id": model_id,
                "entry_type": "reference",
                "category": category,
                "standard_code": code,
                "standard_label": label,
                "aliases": list(aliases),
                "source": "ADMIN",
                "is_verified": True,
                "hit_count": 0,
                "extra": extra,
                "created_at": datetime.utcnow().isoformat()
            }
            documents.append(doc)

        if not documents:
            return {"error": "유효한 행이 없습니다", "count": 0}

        # 4. Upload to Cosmos DB
        total = 0
        for doc in documents:
            try:
                await container.upsert_item(body=doc)
                total += 1
            except Exception as e:
                logger.error(f"[ReferenceData] Upload failed for '{doc.get('standard_code')}': {e}")

        # 5. Invalidate cache
        cache_key = self._cache_key(model_id, category)
        self._cache.pop(cache_key, None)
        self._cache_loaded.discard(cache_key)

        logger.info(f"[ReferenceData] Uploaded {total}/{len(documents)} entries to '{category}' for model {model_id}")
        return {
            "count": total,
            "category": category,
            "columns": col_names
        }

    async def list_entries(self, model_id: str, category: str,
                           offset: int = 0, limit: int = 100,
                           search: str = "") -> dict:
        """List entries in a category with pagination and optional search."""
        container = self._get_container()
        if not container:
            return {"entries": [], "total": 0}

        try:
            type_filter = "(c.entry_type = 'reference' OR NOT IS_DEFINED(c.entry_type))"
            
            if model_id in ('__global__', '__all__'):
                where = f"WHERE c.category = @cat AND {type_filter}"
                params = [{"name": "@cat", "value": category}]
            else:
                where = f"WHERE c.model_id IN (@model_id, '__global__') AND c.category = @cat AND {type_filter}"
                params = [
                    {"name": "@model_id", "value": model_id},
                    {"name": "@cat", "value": category}
                ]

            if search:
                where += " AND (CONTAINS(LOWER(c.standard_code), @search) OR CONTAINS(LOWER(c.standard_label), @search))"
                params.append({"name": "@search", "value": search.lower()})

            # Get total count
            count_query = f"SELECT VALUE COUNT(1) FROM c {where}"
            counts = [c async for c in container.query_items(
                query=count_query, parameters=params
            )]
            total = counts[0] if counts else 0

            # Get paginated entries
            query = f"SELECT c.id, c.model_id, c.category, c.standard_code, c.standard_label, c.aliases, c.source, c.hit_count, c.is_verified, c.extra FROM c {where} OFFSET @offset LIMIT @limit"
            params.extend([
                {"name": "@offset", "value": offset},
                {"name": "@limit", "value": limit}
            ])
            entries = [item async for item in container.query_items(
                query=query, parameters=params
            )]

            return {"entries": entries, "total": total}
        except Exception as e:
            logger.error(f"[ReferenceData] list_entries failed: {e}")
            return {"entries": [], "total": 0}

    async def update_entry(self, entry_id: str, model_id: str, updates: dict) -> dict:
        """Update a single reference data entry."""
        container = self._get_container()
        if not container:
            raise Exception("Reference data service not configured")

        try:
            item = await container.read_item(item=entry_id, partition_key=model_id)
            for key in ['standard_code', 'standard_label', 'aliases', 'is_verified']:
                if key in updates:
                    item[key] = updates[key]
            item["updated_at"] = datetime.utcnow().isoformat()
            await container.upsert_item(body=item)
            # Invalidate cache
            self.invalidate_cache(model_id, item.get("category", ""))
            return item
        except Exception as e:
            logger.error(f"[ReferenceData] update_entry failed: {e}")
            raise

    async def delete_entry(self, entry_id: str, model_id: str) -> bool:
        """Delete a single reference data entry."""
        container = self._get_container()
        if not container:
            raise Exception("Reference data service not configured")

        try:
            # Read first to get category for cache invalidation
            item = await container.read_item(item=entry_id, partition_key=model_id)
            category = item.get("category", "")
            await container.delete_item(item=entry_id, partition_key=model_id)
            self.invalidate_cache(model_id, category)
            return True
        except Exception as e:
            logger.error(f"[ReferenceData] delete_entry failed: {e}")
            return False

    async def list_categories(self, model_id: str) -> List[dict]:
        """List all reference data categories for the given model.
        When model_id is '__global__' or '__all__', lists ALL categories across all models.
        Includes both entry_type='reference' and legacy docs without entry_type.
        """
        container = self._get_container()
        if not container:
            logger.warning("[ReferenceData] list_categories: container is None")
            return []

        # Filter: entry_type='reference' OR entry_type is missing (legacy)
        type_filter = "(c.entry_type = 'reference' OR NOT IS_DEFINED(c.entry_type))"

        try:
            if model_id in ('__global__', '__all__'):
                query = f"SELECT DISTINCT VALUE c.category FROM c WHERE {type_filter}"
                params = []
            else:
                query = f"SELECT DISTINCT VALUE c.category FROM c WHERE c.model_id IN (@model_id, '__global__') AND {type_filter}"
                params = [{"name": "@model_id", "value": model_id}]
            
            logger.info(f"[ReferenceData] list_categories query: {query}")
            categories = [cat async for cat in container.query_items(
                query=query, parameters=params
            )]
            logger.info(f"[ReferenceData] list_categories found {len(categories)} categories: {categories}")
            
            result = []
            for cat in categories:
                if model_id in ('__global__', '__all__'):
                    count_query = f"SELECT VALUE COUNT(1) FROM c WHERE c.category = @cat AND {type_filter}"
                    count_params = [{"name": "@cat", "value": cat}]
                else:
                    count_query = f"SELECT VALUE COUNT(1) FROM c WHERE c.model_id IN (@model_id, '__global__') AND c.category = @cat AND {type_filter}"
                    count_params = [
                        {"name": "@model_id", "value": model_id},
                        {"name": "@cat", "value": cat}
                    ]
                counts = [c async for c in container.query_items(
                    query=count_query, parameters=count_params
                )]
                result.append({"category": cat, "count": counts[0] if counts else 0})
            
            return result
        except Exception as e:
            logger.error(f"[ReferenceData] list_categories failed: {type(e).__name__}: {e}", exc_info=True)
            return []

    async def delete_category(self, model_id: str, category: str) -> int:
        """Delete all entries in a category for a model."""
        container = self._get_container()
        if not container:
            raise Exception("Reference data service not configured")

        query = "SELECT c.id FROM c WHERE c.model_id = @model_id AND c.category = @cat"
        params = [
            {"name": "@model_id", "value": model_id},
            {"name": "@cat", "value": category}
        ]
        
        deleted = 0
        try:
            items = [item async for item in container.query_items(
                query=query, parameters=params
            )]
            for item in items:
                await container.delete_item(item=item["id"], partition_key=item["id"])
                deleted += 1
        except Exception as e:
            logger.error(f"[ReferenceData] delete_category failed: {e}")

        # Invalidate cache
        cache_key = self._cache_key(model_id, category)
        self._cache.pop(cache_key, None)
        self._cache_loaded.discard(cache_key)

        return deleted

    # ──────────────────────────────────────────────
    # Matching Operations (In-Memory)
    # ──────────────────────────────────────────────

    async def _load_category(self, model_id: str, category: str):
        """Load all entries for a category into memory cache."""
        cache_key = self._cache_key(model_id, category)
        if cache_key in self._cache_loaded:
            return
        
        container = self._get_container()
        if not container:
            return

        try:
            # Load model-specific entries + global entries
            query = "SELECT * FROM c WHERE c.model_id IN (@model_id, '__global__') AND c.category = @cat"
            params = [
                {"name": "@model_id", "value": model_id},
                {"name": "@cat", "value": category}
            ]
            entries = []
            async for item in container.query_items(
                query=query, parameters=params
            ):
                entries.append(ReferenceEntry(
                    id=item["id"],
                    model_id=item["model_id"],
                    category=item["category"],
                    standard_code=item.get("standard_code", ""),
                    standard_label=item.get("standard_label", ""),
                    aliases=item.get("aliases", []),
                    source=item.get("source", "ADMIN"),
                    is_verified=item.get("is_verified", True),
                    hit_count=item.get("hit_count", 0),
                    extra=item.get("extra", {})
                ))
            
            self._cache[cache_key] = entries
            self._cache_loaded.add(cache_key)
            logger.info(f"[ReferenceData] Loaded {len(entries)} entries for '{category}' (model {model_id})")
        except Exception as e:
            logger.error(f"[ReferenceData] Failed to load category '{category}': {e}")
            self._cache[cache_key] = []
            self._cache_loaded.add(cache_key)

    async def match(self, query: str, model_id: str, category: str, 
                    threshold: float = FUZZY_MATCH_THRESHOLD) -> Optional[MatchResult]:
        """
        Find the best matching reference entry for a query string.
        Uses exact match first, then fuzzy matching.
        """
        if not query or len(query.strip()) < 2:
            return None

        await self._load_category(model_id, category)
        
        cache_key = self._cache_key(model_id, category)
        entries = self._cache.get(cache_key, [])
        
        query_lower = query.lower().strip()
        best_match = None
        best_score = 0.0
        best_alias = ""
        
        for entry in entries:
            # Phase 1: Exact match (fastest)
            if query_lower == entry.standard_code.lower() or query_lower == entry.standard_label.lower():
                return MatchResult(
                    standard_code=entry.standard_code,
                    standard_label=entry.standard_label,
                    category=category,
                    score=1.0,
                    matched_alias=query,
                    extra=entry.extra
                )
            
            # Phase 2: Alias exact match
            for alias in entry.aliases:
                if query_lower == alias.lower():
                    return MatchResult(
                        standard_code=entry.standard_code,
                        standard_label=entry.standard_label,
                        category=category,
                        score=1.0,
                        matched_alias=alias,
                        extra=entry.extra
                    )
            
            # Phase 3: Fuzzy match
            # Check against code
            code_score = fuzz.ratio(query_lower, entry.standard_code.lower()) / 100.0
            # Check against label
            label_score = max(
                fuzz.token_set_ratio(query_lower, entry.standard_label.lower()) / 100.0,
                fuzz.ratio(query_lower, entry.standard_label.lower()) / 100.0
            )
            # Check against all aliases
            alias_score = 0.0
            best_alias_candidate = ""
            for alias in entry.aliases:
                a_score = max(
                    fuzz.ratio(query_lower, alias.lower()) / 100.0,
                    fuzz.token_set_ratio(query_lower, alias.lower()) / 100.0
                )
                if a_score > alias_score:
                    alias_score = a_score
                    best_alias_candidate = alias
            
            score = max(code_score, label_score, alias_score)
            
            if score > best_score:
                best_score = score
                best_match = entry
                best_alias = best_alias_candidate or entry.standard_code
        
        if best_match and best_score >= threshold:
            return MatchResult(
                standard_code=best_match.standard_code,
                standard_label=best_match.standard_label,
                category=category,
                score=best_score,
                matched_alias=best_alias,
                extra=best_match.extra
            )
        
        return None

    async def normalize_extracted_data(self, guide_extracted: dict, model_id: str,
                                        field_dict_map: Dict[str, str]) -> dict:
        """
        Normalize all string values in extracted data using reference data matching.
        
        Args:
            guide_extracted: The LLM extraction result
            model_id: Model ID for scoping reference data
            field_dict_map: Mapping of "field_key" or "parent.sub_key" -> category
        
        Returns:
            guide_extracted with matched values replaced and _dict_evidence added.
        """
        if not field_dict_map or not self.is_available:
            return guide_extracted

        # Pre-load all needed categories
        categories = set(field_dict_map.values())
        await asyncio.gather(*[
            self._load_category(model_id, cat) for cat in categories
        ])

        evidence = {}
        # Cache to avoid redundant fuzzy matching
        match_cache: Dict[str, Optional[MatchResult]] = {}

        async def _match_cached(value: str, category: str) -> Optional[MatchResult]:
            key = f"{value}|{category}"
            if key not in match_cache:
                match_cache[key] = await self.match(value, model_id, category)
            return match_cache[key]

        # Process top-level fields and table rows
        for key, item in guide_extracted.items():
            if key.startswith("_"):
                continue

            if isinstance(item, dict) and "value" in item:
                val = item["value"]
                
                if isinstance(val, str) and len(val.strip()) >= 2:
                    cat = field_dict_map.get(key)
                    if cat:
                        result = await _match_cached(val, cat)
                        if result:
                            item["raw_value"] = val
                            item["value"] = result.standard_code
                            item["_modifier"] = "Reference Data"
                            evidence[key] = {
                                "original": val,
                                "matched_code": result.standard_code,
                                "matched_label": result.standard_label,
                                "category": result.category,
                                "score": result.score
                            }
                
                elif isinstance(val, list):
                    for row_idx, row in enumerate(val):
                        if not isinstance(row, dict):
                            continue
                        for sub_key, sub_node in row.items():
                            if sub_key.startswith("_"):
                                continue
                            if isinstance(sub_node, dict) and "value" in sub_node:
                                sub_val = sub_node["value"]
                                if isinstance(sub_val, str) and len(sub_val.strip()) >= 2:
                                    # Skip numeric values
                                    try:
                                        float(sub_val.replace(",", ""))
                                        continue
                                    except (ValueError, AttributeError):
                                        pass
                                    
                                    cat = field_dict_map.get(f"{key}.{sub_key}")
                                    if cat:
                                        result = await _match_cached(sub_val, cat)
                                        if result:
                                            sub_node["raw_value"] = sub_val
                                            sub_node["value"] = result.standard_code
                                            sub_node["_modifier"] = "Reference Data"
                                            evidence[f"{key}[{row_idx}].{sub_key}"] = {
                                                "original": sub_val,
                                                "matched_code": result.standard_code,
                                                "matched_label": result.standard_label,
                                                "category": result.category,
                                                "score": result.score
                                            }

        if evidence:
            guide_extracted["_dict_evidence"] = evidence

        return guide_extracted

    # ──────────────────────────────────────────────
    # Synonym Operations (replaces vibe_dictionaries)
    # ──────────────────────────────────────────────

    async def list_synonyms(self, model_id: str = None) -> list:
        """List all synonym entries, optionally filtered by model_id."""
        container = self._get_container()
        if not container:
            return []

        try:
            if model_id:
                query = "SELECT * FROM c WHERE c.entry_type = 'synonym' AND c.model_id IN (@model_id, '__global__')"
                params = [{"name": "@model_id", "value": model_id}]
            else:
                query = "SELECT * FROM c WHERE c.entry_type = 'synonym'"
                params = []
            
            entries = []
            async for item in container.query_items(
                query=query, parameters=params
            ):
                entries.append(item)
            # Sort in Python to avoid Cosmos composite index requirement
            entries.sort(key=lambda x: x.get("hit_count", 0), reverse=True)
            return entries
        except Exception as e:
            logger.error(f"[ReferenceData] list_synonyms failed: {e}")
            return []

    async def upsert_synonym(self, model_id: str, field_name: str,
                              raw_val: str, standard_val: str,
                              source: str = "MANUAL", is_verified: bool = True) -> dict:
        """Create or update a synonym entry."""
        container = self._get_container()
        if not container:
            raise Exception("Reference data service not configured")

        doc_id = hashlib.md5(
            f"{model_id}_synonym_{field_name}_{raw_val}".encode()
        ).hexdigest()

        doc = {
            "id": doc_id,
            "model_id": model_id,
            "category": "vibe",
            "entry_type": "synonym",
            "field_name": field_name,
            "raw_val": raw_val,
            "value": standard_val,
            "standard_code": standard_val,
            "standard_label": raw_val,
            "aliases": [raw_val.lower()],
            "source": source,
            "is_verified": is_verified,
            "hit_count": 0,
            "extra": {},
            "created_at": datetime.utcnow().isoformat()
        }

        await container.upsert_item(body=doc)
        # Invalidate synonym cache
        self.invalidate_cache(model_id, "vibe")
        return doc

    async def update_synonym(self, model_id: str, field_name: str,
                              raw_val: str, updates: dict) -> dict:
        """Update specific fields of a synonym entry."""
        container = self._get_container()
        if not container:
            raise Exception("Reference data service not configured")

        doc_id = hashlib.md5(
            f"{model_id}_synonym_{field_name}_{raw_val}".encode()
        ).hexdigest()

        try:
            item = await container.read_item(item=doc_id, partition_key=model_id)
            for key, val in updates.items():
                if key in ("value", "standard_val"):
                    item["value"] = val
                    item["standard_code"] = val
                elif key in ("is_verified", "hit_count", "source"):
                    item[key] = val
            await container.upsert_item(body=item)
            self.invalidate_cache(model_id, "vibe")
            return item
        except Exception as e:
            logger.error(f"[ReferenceData] update_synonym failed: {e}")
            raise

    async def delete_synonym(self, model_id: str, field_name: str, raw_val: str) -> bool:
        """Delete a synonym entry."""
        container = self._get_container()
        if not container:
            raise Exception("Reference data service not configured")

        doc_id = hashlib.md5(
            f"{model_id}_synonym_{field_name}_{raw_val}".encode()
        ).hexdigest()

        try:
            await container.delete_item(item=doc_id, partition_key=model_id)
            self.invalidate_cache(model_id, "vibe")
            return True
        except Exception as e:
            logger.error(f"[ReferenceData] delete_synonym failed: {e}")
            return False

    async def apply_synonyms(self, result: dict, model_id: str) -> dict:
        """
        Apply synonym corrections to extraction result (replaces apply_vibe_dictionary).
        Queries entry_type='synonym' from reference_data container.
        """
        container = self._get_container()
        if not container:
            return result

        try:
            query = (
                "SELECT * FROM c WHERE c.entry_type = 'synonym' "
                "AND c.model_id IN (@model_id, '__global__') "
                "AND c.is_verified = true"
            )
            params = [{"name": "@model_id", "value": model_id}]
            
            entries = []
            async for item in container.query_items(
                query=query, parameters=params
            ):
                entries.append(item)
        except Exception as e:
            logger.error(f"[ReferenceData] Failed to fetch synonyms: {e}")
            return result

        if not entries:
            return result

        # Build lookup: { "field_name": { "raw_val": "standard_val" } }
        lookup = {}
        for entry in entries:
            field = entry.get("field_name", "default")
            raw_val = entry.get("raw_val")
            std_val = entry.get("value")
            if not raw_val or not std_val:
                continue
            if field not in lookup:
                lookup[field] = {}
            lookup[field][raw_val] = std_val

        guide = result.get("guide_extracted", {})
        if not isinstance(guide, dict):
            return result

        from typing import Any

        def _apply(cell: Any, field_name: str) -> Any:
            if not isinstance(cell, dict) or "value" not in cell:
                return cell
            val = cell.get("value")
            if not isinstance(val, str) or not val:
                return cell
            
            # Check field-specific, then "default"
            for fn in [field_name, "default"]:
                field_dict = lookup.get(fn, {})
                std = field_dict.get(val)
                if std:
                    cell["raw_value"] = val
                    cell["value"] = std
                    cell["_modifier"] = "Vibe Dictionary"
                    return cell
            return cell

        for key, item in guide.items():
            if key.startswith("_"):
                continue
            if isinstance(item, dict) and "value" in item:
                val = item["value"]
                if isinstance(val, str):
                    _apply(item, key)
                elif isinstance(val, list):
                    for row in val:
                        if isinstance(row, dict):
                            for sub_key, sub_node in row.items():
                                if not sub_key.startswith("_"):
                                    _apply(sub_node, sub_key)

        return result

    def invalidate_cache(self, model_id: str = None, category: str = None):
        """Invalidate cache for specific model/category or all."""
        if model_id and category:
            key = self._cache_key(model_id, category)
            self._cache.pop(key, None)
            self._cache_loaded.discard(key)
        elif model_id:
            to_remove = [k for k in self._cache if k.startswith(f"{model_id}:")]
            for k in to_remove:
                self._cache.pop(k, None)
                self._cache_loaded.discard(k)
        else:
            self._cache.clear()
            self._cache_loaded.clear()


# Singleton
_reference_data_service: Optional[ReferenceDataService] = None

def get_reference_data_service() -> ReferenceDataService:
    global _reference_data_service
    if _reference_data_service is None:
        _reference_data_service = ReferenceDataService()
    return _reference_data_service

