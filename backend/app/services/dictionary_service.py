"""
Dictionary Service — Azure AI Search
Manages dictionary indexes for auto-normalization.
Dynamically indexes any Excel columns — no fixed schema required.
"""
import asyncio
import logging
import io
import hashlib
from typing import List, Optional

import pandas as pd
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchFieldDataType,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


class DictionaryMatch:
    """Result of a dictionary search."""
    def __init__(self, code: str, name: str, category: str, score: float, extra: dict = None):
        self.code = code
        self.name = name
        self.category = category
        self.score = score
        self.extra = extra or {}


def _get_index_name(category: str) -> str:
    """Each category gets its own index: daom-dict-{category}"""
    safe = category.lower().replace(" ", "-").replace("_", "-")
    return f"daom-dict-{safe}"


class DictionaryService:
    """
    Manages dictionary data in Azure AI Search.
    Each category becomes a separate index with dynamically-created fields
    based on the uploaded Excel columns.
    """

    def __init__(self):
        endpoint = settings.AZURE_SEARCH_ENDPOINT
        key = settings.AZURE_SEARCH_KEY

        self._initialized = False
        if not endpoint or not key:
            logger.warning("[DictionaryService] AZURE_SEARCH_ENDPOINT/KEY not set. Dictionary features disabled.")
            return

        try:
            self._endpoint = endpoint
            self._key = key
            self._index_client = SearchIndexClient(
                endpoint=endpoint,
                credential=AzureKeyCredential(key)
            )
            self._initialized = True
            logger.info(f"[DictionaryService] Connected to {endpoint}")
        except Exception as e:
            logger.error(f"[DictionaryService] Init failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._initialized

    def _search_client(self, category: str) -> SearchClient:
        return SearchClient(
            endpoint=self._endpoint,
            index_name=_get_index_name(category),
            credential=AzureKeyCredential(self._key)
        )

    async def upload_from_excel(self, file_bytes: bytes, category: str, filename: str = "") -> dict:
        """
        Upload Excel/CSV to AI Search.
        Dynamically creates index fields from the Excel column headers.
        Non-ASCII column names (Korean, etc.) are mapped to safe field names.
        """
        if not self._initialized:
            return {"error": "Dictionary service not configured", "count": 0}

        # 1. Parse Excel
        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_bytes))
            else:
                df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return {"error": f"파일 파싱 실패: {e}", "count": 0}

        if df.empty:
            return {"error": "빈 파일입니다", "count": 0}

        # 2. Create safe field names (Azure AI Search: ASCII letters, digits, underscore only)
        col_mapping = {}  # original_name -> safe_name
        safe_columns = []
        for i, col in enumerate(df.columns):
            original = str(col).strip()
            # Try to make a safe name from ASCII chars
            safe = "".join(c for c in original.replace(" ", "_").replace("-", "_") if c.isascii() and (c.isalnum() or c == "_"))
            if not safe or safe[0].isdigit():
                safe = f"field_{i}"
            # Avoid duplicates
            base = safe
            counter = 2
            while safe in safe_columns:
                safe = f"{base}_{counter}"
                counter += 1
            col_mapping[original] = safe
            safe_columns.append(safe)

        df.columns = safe_columns

        # 3. Create/update index with dynamic fields
        index_name = _get_index_name(category)
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True),
        ]
        for col in safe_columns:
            fields.append(
                SearchableField(name=col, type=SearchFieldDataType.String)
            )

        try:
            index = SearchIndex(name=index_name, fields=fields)
            await asyncio.to_thread(self._index_client.create_or_update_index, index)
            logger.info(f"[DictionaryService] Index '{index_name}' created/updated with {len(safe_columns)} fields")
        except Exception as e:
            return {"error": f"인덱스 생성 실패: {e}", "count": 0}

        # 4. Upload metadata document (original column names mapping)
        client = self._search_client(category)
        meta_doc = {
            "id": "__meta__",
            "doc_type": "meta",
        }
        # Store original names in the first field slots
        for orig, safe in col_mapping.items():
            meta_doc[safe] = orig  # safe field stores original column name
        try:
            await asyncio.to_thread(client.upload_documents, documents=[meta_doc])
        except Exception as e:
            logger.warning(f"[DictionaryService] Meta document upload failed: {e}")

        # 5. Upload data documents
        documents = []
        for idx, row in df.iterrows():
            row_str = "|".join(str(v) for v in row.values)
            doc_id = hashlib.md5(f"{category}_{idx}_{row_str}".encode()).hexdigest()

            doc = {"id": doc_id, "doc_type": "data"}
            for col in safe_columns:
                val = row.get(col)
                doc[col] = str(val).strip() if pd.notna(val) else ""
            documents.append(doc)

        if not documents:
            return {"error": "유효한 행이 없습니다", "count": 0}

        total = 0
        batch_size = 1000
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            try:
                result = await asyncio.to_thread(client.upload_documents, documents=batch)
                total += len([r for r in result if r.succeeded])
            except Exception as e:
                logger.error(f"[DictionaryService] Upload batch {i} failed: {e}")

        logger.info(f"[DictionaryService] Uploaded {total}/{len(documents)} items to '{category}'")
        return {
            "count": total,
            "category": category,
            "fields": list(col_mapping.keys()),  # original names
            "field_mapping": col_mapping  # original -> safe
        }

    async def search(self, query: str, category: Optional[str] = None, top_k: int = 5) -> List[DictionaryMatch]:
        """Search dictionary entries by keyword."""
        if not self._initialized or not query or len(query.strip()) < 2:
            return []

        if not category:
            # Search all category indexes
            results = []
            for cat_info in await self.list_categories():
                results.extend(await self.search(query, cat_info["category"], top_k))
            # Sort by score, take top_k
            results.sort(key=lambda m: m.score, reverse=True)
            return results[:top_k]

        try:
            client = self._search_client(category)
            filter_expr = "doc_type eq 'data'"
            search_results = await asyncio.to_thread(
                client.search,
                search_text=query, filter=filter_expr,
                top=top_k, include_total_count=True
            )
            matches = []
            for r in search_results:
                # Use first two non-id fields as code/name for display
                fields = {k: v for k, v in r.items() if k not in ("id", "@search.score", "@search.reranker_score")}
                field_keys = list(fields.keys())
                code = fields.get(field_keys[0], "") if field_keys else ""
                name = fields.get(field_keys[1], "") if len(field_keys) > 1 else code
                matches.append(DictionaryMatch(
                    code=str(code), name=str(name),
                    category=category, score=r.get("@search.score", 0.0),
                    extra=fields
                ))
            return matches
        except Exception as e:
            logger.error(f"[DictionaryService] Search failed for '{category}': {e}")
            return []

    async def list_categories(self) -> List[dict]:
        """List all dictionary categories by listing indexes prefixed with 'daom-dict-'."""
        if not self._initialized:
            return []
        try:
            indexes = await asyncio.to_thread(lambda: list(self._index_client.list_indexes()))
            categories = []
            for idx in indexes:
                if idx.name.startswith("daom-dict-"):
                    cat_name = idx.name.replace("daom-dict-", "")
                    # Get document count
                    try:
                        client = self._search_client(cat_name)
                        results = await asyncio.to_thread(
                            client.search, search_text="*", top=0, include_total_count=True
                        )
                        count = results.get_count() or 0
                    except Exception:
                        count = 0
                    categories.append({"category": cat_name, "count": count})
            return categories
        except Exception as e:
            logger.error(f"[DictionaryService] list_categories failed: {e}")
            return []

    async def delete_category(self, category: str) -> int:
        """Delete a dictionary category (drops the index)."""
        if not self._initialized:
            raise Exception("Dictionary service not configured")
        index_name = _get_index_name(category)
        try:
            await asyncio.to_thread(self._index_client.delete_index, index_name)
            logger.info(f"[DictionaryService] Deleted index '{index_name}'")
            return 1
        except Exception as e:
            logger.error(f"[DictionaryService] delete_category failed: {e}")
            raise e


# Singleton
_dictionary_service: Optional[DictionaryService] = None


def get_dictionary_service() -> DictionaryService:
    global _dictionary_service
    if _dictionary_service is None:
        _dictionary_service = DictionaryService()
    return _dictionary_service
