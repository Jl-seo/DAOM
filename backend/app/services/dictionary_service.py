"""
Dictionary Service — Azure AI Search via Foundry Connection
Manages dictionary indexes (port, charge, etc.) using Azure AI Search.
Search credentials are resolved from Foundry project connections or env vars as fallback.
"""
import logging
import io
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

# Single unified index — all dictionary categories share one index
DICTIONARY_INDEX_NAME = "daom-dictionary"


class DictionaryMatch:
    """Result of a dictionary search."""
    def __init__(self, code: str, name: str, category: str, score: float):
        self.code = code
        self.name = name
        self.category = category
        self.score = score


def _resolve_search_credentials() -> tuple:
    """
    Resolve Azure AI Search endpoint and key.
    Priority: env vars > Foundry project connection discovery.
    """
    # 1. Direct env vars (explicit override)
    if settings.AZURE_SEARCH_ENDPOINT and settings.AZURE_SEARCH_KEY:
        logger.info("[DictionaryService] Using explicit AZURE_SEARCH_ENDPOINT/KEY from env.")
        return settings.AZURE_SEARCH_ENDPOINT, settings.AZURE_SEARCH_KEY

    # 2. Try to discover from Foundry project connections
    if settings.AZURE_AIPROJECT_ENDPOINT:
        try:
            from azure.ai.projects import AIProjectClient
            from azure.identity import DefaultAzureCredential

            client = AIProjectClient(
                endpoint=settings.AZURE_AIPROJECT_ENDPOINT,
                credential=DefaultAzureCredential()
            )
            # List connections and find AI Search type
            connections = client.connections.list()
            for conn in connections:
                # Azure AI Search connections have type "CognitiveSearch" or "AzureAISearch"
                conn_type = getattr(conn, "connection_type", "") or ""
                if "search" in conn_type.lower() or "cognitive" in conn_type.lower():
                    # Get connection details with credentials
                    full_conn = client.connections.get(connection_name=conn.name, include_credentials=True)
                    endpoint = getattr(full_conn, "endpoint_url", "") or getattr(full_conn, "target", "")
                    key = getattr(full_conn, "key", "") or ""
                    if endpoint:
                        logger.info(f"[DictionaryService] Discovered AI Search from Foundry connection: {conn.name}")
                        return endpoint, key
        except Exception as e:
            logger.warning(f"[DictionaryService] Foundry connection discovery failed: {e}")

    return "", ""


class DictionaryService:
    """
    Manages dictionary data in Azure AI Search.
    Uses a single index with 'category' field to support multiple dictionary types.
    """

    def __init__(self):
        self._search_endpoint, self._search_key = _resolve_search_credentials()
        self._initialized = False

        if not self._search_endpoint:
            logger.warning("[DictionaryService] Azure Search not configured. Dictionary features disabled.")
            return

        try:
            self._index_client = SearchIndexClient(
                endpoint=self._search_endpoint,
                credential=AzureKeyCredential(self._search_key)
            )
            self._initialized = True
            logger.info(f"[DictionaryService] Initialized with endpoint: {self._search_endpoint}")
        except Exception as e:
            logger.error(f"[DictionaryService] Failed to initialize: {e}")

    @property
    def is_available(self) -> bool:
        return self._initialized

    async def ensure_index(self):
        """Create the unified dictionary index if it doesn't exist."""
        if not self._initialized:
            return

        try:
            self._index_client.get_index(DICTIONARY_INDEX_NAME)
        except Exception:
            logger.info(f"[DictionaryService] Creating index '{DICTIONARY_INDEX_NAME}'...")
            index = SearchIndex(
                name=DICTIONARY_INDEX_NAME,
                fields=[
                    SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                    SimpleField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
                    SimpleField(name="code", type=SearchFieldDataType.String, filterable=True),
                    SearchableField(name="name", type=SearchFieldDataType.String),
                    SearchableField(name="aliases", type=SearchFieldDataType.String),
                    SimpleField(name="country", type=SearchFieldDataType.String, filterable=True),
                    SimpleField(name="region", type=SearchFieldDataType.String, filterable=True),
                    SimpleField(name="extra", type=SearchFieldDataType.String),
                ]
            )
            self._index_client.create_or_update_index(index)
            logger.info(f"[DictionaryService] Index created.")

    def _get_search_client(self) -> SearchClient:
        return SearchClient(
            endpoint=self._search_endpoint,
            index_name=DICTIONARY_INDEX_NAME,
            credential=AzureKeyCredential(self._search_key)
        )

    async def upload_from_excel(self, file_bytes: bytes, category: str, filename: str = "") -> dict:
        """Parse Excel/CSV and upsert into the search index."""
        if not self._initialized:
            return {"error": "Dictionary service not configured", "count": 0}

        await self.ensure_index()

        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(file_bytes))
            else:
                df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return {"error": f"Failed to parse file: {e}", "count": 0}

        required = {"code", "name"}
        if not required.issubset(set(df.columns)):
            return {"error": f"Missing required columns: {required - set(df.columns)}", "count": 0}

        documents = []
        for _, row in df.iterrows():
            code = str(row["code"]).strip()
            name = str(row["name"]).strip()
            aliases = str(row.get("aliases", "")).strip()
            doc = {
                "id": f"{category}_{code}",
                "category": category,
                "code": code,
                "name": name,
                "aliases": aliases,
                "country": str(row.get("country", "")).strip(),
                "region": str(row.get("region", "")).strip(),
                "extra": str(row.get("extra", "")).strip(),
            }
            documents.append(doc)

        if not documents:
            return {"error": "No valid rows found", "count": 0}

        client = self._get_search_client()
        total = 0
        batch_size = 1000
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            try:
                result = client.upload_documents(documents=batch)
                total += len([r for r in result if r.succeeded])
            except Exception as e:
                logger.error(f"[DictionaryService] Upload batch {i} failed: {e}")

        logger.info(f"[DictionaryService] Uploaded {total}/{len(documents)} items to '{category}'")
        return {"count": total, "category": category}

    async def search(self, query: str, category: Optional[str] = None, top_k: int = 3) -> List[DictionaryMatch]:
        """Search the dictionary index with keyword + category filter."""
        if not self._initialized or not query or len(query.strip()) < 2:
            return []

        client = self._get_search_client()
        filter_expr = f"category eq '{category}'" if category else None

        try:
            results = client.search(
                search_text=query, filter=filter_expr,
                top=top_k, include_total_count=True
            )
            return [
                DictionaryMatch(
                    code=r.get("code", ""), name=r.get("name", ""),
                    category=r.get("category", ""), score=r.get("@search.score", 0.0)
                ) for r in results
            ]
        except Exception as e:
            logger.error(f"[DictionaryService] Search failed: {e}")
            return []

    async def add_alias(self, category: str, code: str, new_alias: str):
        """Auto-learning: add a new alias to an existing dictionary entry."""
        if not self._initialized:
            return
        client = self._get_search_client()
        doc_id = f"{category}_{code}"
        try:
            existing = client.get_document(key=doc_id)
            current_aliases = existing.get("aliases", "")
            alias_list = [a.strip() for a in current_aliases.split(",") if a.strip()]
            if new_alias not in alias_list:
                alias_list.append(new_alias)
                existing["aliases"] = ", ".join(alias_list)
                client.upload_documents(documents=[existing])
                logger.info(f"[DictionaryService] Added alias '{new_alias}' to {doc_id}")
        except Exception as e:
            logger.error(f"[DictionaryService] add_alias failed: {e}")

    async def list_categories(self) -> List[dict]:
        """List all registered dictionary categories with item counts."""
        if not self._initialized:
            return []
        client = self._get_search_client()
        try:
            results = client.search(search_text="*", facets=["category"], top=0)
            facets = results.get_facets()
            return [
                {"category": f["value"], "count": f["count"]}
                for f in facets.get("category", [])
            ]
        except Exception as e:
            logger.error(f"[DictionaryService] list_categories failed: {e}")
            return []

    async def delete_category(self, category: str) -> int:
        """Delete all entries for a given category."""
        if not self._initialized:
            return 0
        client = self._get_search_client()
        try:
            results = client.search(
                search_text="*", filter=f"category eq '{category}'",
                top=5000, select=["id"]
            )
            ids = [{"id": r["id"]} for r in results]
            if ids:
                client.delete_documents(documents=ids)
            logger.info(f"[DictionaryService] Deleted {len(ids)} items from '{category}'")
            return len(ids)
        except Exception as e:
            logger.error(f"[DictionaryService] delete_category failed: {e}")
            return 0


# Singleton
_dictionary_service: Optional[DictionaryService] = None


def get_dictionary_service() -> DictionaryService:
    global _dictionary_service
    if _dictionary_service is None:
        _dictionary_service = DictionaryService()
    return _dictionary_service
