"""
Pytest fixtures for DAOM backend tests.

Provides mocks for the external systems that extraction paths touch:
- Cosmos DB (in-memory dict-backed async container proxy)
- Azure Document Intelligence (deterministic OCR output)
- Azure OpenAI / AsyncAzureOpenAI (awaitable chat completion mock)
- Blob storage (in-memory bytes store + JSON cache)
- Auth (`get_current_user` dependency override)

Fixtures are composable — a test pulls only what it needs.
Golden OCR payloads live under `tests/fixtures/` and are loaded via
the `load_fixture` fixture.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app
from app.core.auth import CurrentUser, get_current_user


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    """ASGI transport client for FastAPI integration tests."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Fixture loader
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    """Return a callable that loads a JSON fixture by stem name.

    Usage:
        def test_something(load_fixture):
            ocr = load_fixture("ocr_invoice_single_page")
    """
    def _load(name: str) -> Any:
        path = FIXTURES_DIR / f"{name}.json"
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    return _load


# ---------------------------------------------------------------------------
# Cosmos DB mock (in-memory async container proxy)
# ---------------------------------------------------------------------------

class _InMemoryContainer:
    """Minimal async-compatible stand-in for azure.cosmos.aio.ContainerProxy.

    Backs its data with a plain dict keyed by `id`. Supports the subset of
    operations the service layer actually uses: read_item, upsert_item,
    delete_item, query_items (async iterator), read_all_items (async iterator).

    Callers can introspect `.items` for assertions and `.call_log` for counts.
    """

    def __init__(self, name: str, seed: Optional[Iterable[Dict[str, Any]]] = None):
        self.name = name
        self.items: Dict[str, Dict[str, Any]] = {}
        self.call_log: List[str] = []
        if seed:
            for item in seed:
                self.items[item["id"]] = dict(item)

    async def read_item(self, item: str, partition_key: Any = None) -> Dict[str, Any]:
        self.call_log.append(f"read_item:{item}")
        if item not in self.items:
            from azure.cosmos.exceptions import CosmosResourceNotFoundError
            raise CosmosResourceNotFoundError(status_code=404, message=f"{item} not found")
        return dict(self.items[item])

    async def upsert_item(self, body: Dict[str, Any]) -> Dict[str, Any]:
        self.call_log.append(f"upsert_item:{body.get('id')}")
        self.items[body["id"]] = dict(body)
        return dict(body)

    async def delete_item(self, item: str, partition_key: Any = None) -> None:
        self.call_log.append(f"delete_item:{item}")
        self.items.pop(item, None)

    async def read_all_items(self) -> AsyncIterator[Dict[str, Any]]:
        self.call_log.append("read_all_items")
        for item in list(self.items.values()):
            yield dict(item)

    async def query_items(
        self,
        query: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict[str, Any]]:
        self.call_log.append(f"query_items:{query}")
        # Naive filter: caller typically does `WHERE c.<field> = @param`.
        # We return all items; individual tests that need finer control
        # should replace this container with a tailored subclass.
        param_map = {p["name"]: p["value"] for p in (parameters or [])}
        for item in list(self.items.values()):
            if param_map.get("@model_id") and item.get("model_id") != param_map["@model_id"]:
                continue
            if param_map.get("@user_id") and item.get("user_id") != param_map["@user_id"]:
                continue
            if param_map.get("@tenant_id") and item.get("tenant_id") != param_map["@tenant_id"]:
                continue
            yield dict(item)


@pytest.fixture
def mock_cosmos(monkeypatch):
    """Patch app.db.cosmos getters to return in-memory containers.

    Returns a dict keyed by container name so tests can seed and inspect
    each container individually.

    Usage:
        def test_x(mock_cosmos):
            mock_cosmos["DocumentModels"].items["m1"] = {"id": "m1", "name": "..."}
            # ... exercise code ...
            assert "read_item:m1" in mock_cosmos["DocumentModels"].call_log
    """
    from app.db import cosmos as cosmos_module

    containers: Dict[str, _InMemoryContainer] = {
        cosmos_module.MODELS_CONTAINER: _InMemoryContainer(cosmos_module.MODELS_CONTAINER),
        cosmos_module.EXTRACTIONS_CONTAINER: _InMemoryContainer(cosmos_module.EXTRACTIONS_CONTAINER),
        cosmos_module.AUDIT_CONTAINER: _InMemoryContainer(cosmos_module.AUDIT_CONTAINER),
        cosmos_module.USERS_CONTAINER: _InMemoryContainer(cosmos_module.USERS_CONTAINER),
        cosmos_module.GROUPS_CONTAINER: _InMemoryContainer(cosmos_module.GROUPS_CONTAINER),
        cosmos_module.MENUS_CONTAINER: _InMemoryContainer(cosmos_module.MENUS_CONTAINER),
        cosmos_module.PROMPTS_CONTAINER: _InMemoryContainer(cosmos_module.PROMPTS_CONTAINER),
        cosmos_module.VIBE_DICTIONARY_CONTAINER: _InMemoryContainer(cosmos_module.VIBE_DICTIONARY_CONTAINER),
        cosmos_module.CONFIG_CONTAINER: _InMemoryContainer(cosmos_module.CONFIG_CONTAINER),
    }

    monkeypatch.setattr(cosmos_module, "_containers", containers)
    monkeypatch.setattr(cosmos_module, "get_models_container", lambda: containers[cosmos_module.MODELS_CONTAINER])
    monkeypatch.setattr(cosmos_module, "get_extractions_container", lambda: containers[cosmos_module.EXTRACTIONS_CONTAINER])
    monkeypatch.setattr(cosmos_module, "get_audit_container", lambda: containers[cosmos_module.AUDIT_CONTAINER])
    monkeypatch.setattr(cosmos_module, "get_users_container", lambda: containers[cosmos_module.USERS_CONTAINER])
    monkeypatch.setattr(cosmos_module, "get_groups_container", lambda: containers[cosmos_module.GROUPS_CONTAINER])
    monkeypatch.setattr(cosmos_module, "get_config_container", lambda: containers[cosmos_module.CONFIG_CONTAINER])
    monkeypatch.setattr(cosmos_module, "get_vibe_dictionary_container", lambda: containers[cosmos_module.VIBE_DICTIONARY_CONTAINER])

    return containers


# ---------------------------------------------------------------------------
# Auth / current-user dependency override
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_user() -> CurrentUser:
    return CurrentUser(
        id="user-oid-001",
        email="tester@example.com",
        name="Test User",
        tenant_id="tenant-001",
        roles=[],
        groups=[],
    )


@pytest.fixture
def sample_admin() -> CurrentUser:
    return CurrentUser(
        id="admin-oid-001",
        email="admin@example.com",
        name="Admin User",
        tenant_id="tenant-001",
        roles=["admin"],
        groups=["admin-group"],
    )


@pytest.fixture
def override_current_user(sample_user):
    """Override the get_current_user FastAPI dependency with a fixed user.

    Yields a setter the test can call to swap to a different user mid-test.
    Cleans up the override on teardown.
    """
    def _setter(user: CurrentUser) -> None:
        app.dependency_overrides[get_current_user] = lambda: user

    _setter(sample_user)
    try:
        yield _setter
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Azure OpenAI mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_azure_openai(monkeypatch):
    """Mock AsyncAzureOpenAI client used by app.services.llm.

    `chat.completions.create` is an AsyncMock returning a structured response
    matching the real SDK shape. Callers can override `.return_value` or
    `.side_effect` for per-test behavior.

    Returns the MagicMock so tests can assert call args and set responses.
    """
    from app.services import llm as llm_module

    response = SimpleNamespace(
        id="chatcmpl-test",
        model="gpt-4-test",
        choices=[
            SimpleNamespace(
                index=0,
                message=SimpleNamespace(role="assistant", content='{"result": "ok"}'),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    monkeypatch.setattr(llm_module, "_openai_client", client)
    monkeypatch.setattr(llm_module, "get_openai_client", lambda: client)
    return client


# ---------------------------------------------------------------------------
# Document Intelligence mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_doc_intel(monkeypatch, load_fixture):
    """Mock app.services.doc_intel.extract_with_strategy.

    Default return: `ocr_invoice_single_page.json` fixture.
    Tests can override by calling `mock_doc_intel.set_result(payload)`.
    """
    from app.services import doc_intel as di_module

    state: Dict[str, Any] = {"result": load_fixture("ocr_invoice_single_page")}

    async def _extract(*args, **kwargs):
        return state["result"]

    async def _analyze_document_layout(*args, **kwargs):
        return state["result"]

    monkeypatch.setattr(di_module, "extract_with_strategy", _extract)
    monkeypatch.setattr(di_module, "analyze_document_layout", _analyze_document_layout)

    # Also patch where extraction_service imports analyze_document_layout
    try:
        from app.services import extraction_service as es_module
        monkeypatch.setattr(es_module, "analyze_document_layout", _analyze_document_layout)
    except (ImportError, AttributeError):
        pass

    controller = SimpleNamespace(
        set_result=lambda payload: state.__setitem__("result", payload),
    )
    return controller


# ---------------------------------------------------------------------------
# Blob storage mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_blob_storage(monkeypatch):
    """Mock app.services.storage upload/download/cache helpers.

    Backs storage with an in-memory dict keyed by blob name. Returns the store
    dict so tests can seed inputs and assert writes.
    """
    from app.services import storage as storage_module

    store: Dict[str, bytes] = {}
    json_cache: Dict[str, Any] = {}

    async def _upload_bytes_to_blob(content: bytes, filename: str, folder: str = "connector") -> str:
        key = f"{folder}/{filename}"
        store[key] = content
        return f"mock://blob/{key}"

    async def _download_blob_to_bytes(url: str) -> bytes:
        key = url.replace("mock://blob/", "")
        return store.get(key, b"")

    async def _save_json_to_blob(blob_name: str, data: Any) -> None:
        json_cache[blob_name] = data

    async def _load_json_from_blob(blob_name: str) -> Optional[Any]:
        return json_cache.get(blob_name)

    monkeypatch.setattr(storage_module, "upload_bytes_to_blob", _upload_bytes_to_blob, raising=False)
    monkeypatch.setattr(storage_module, "download_blob_to_bytes", _download_blob_to_bytes, raising=False)
    monkeypatch.setattr(storage_module, "save_json_to_blob", _save_json_to_blob, raising=False)
    monkeypatch.setattr(storage_module, "load_json_from_blob", _load_json_from_blob, raising=False)

    return SimpleNamespace(store=store, json_cache=json_cache)


# ---------------------------------------------------------------------------
# Sample extraction model factory
# ---------------------------------------------------------------------------

@pytest.fixture
def make_model():
    """Factory for building `ExtractionModel` instances for tests.

    Returns a callable; call it with kwargs to override defaults.
    """
    from app.schemas.model import ExtractionModel

    def _make(**overrides) -> ExtractionModel:
        base: Dict[str, Any] = {
            "id": "model-test-001",
            "name": "Test Invoice Model",
            "description": "Test fixture model",
            "fields": [
                {"key": "invoice_number", "label": "Invoice Number", "type": "string"},
                {"key": "total", "label": "Total", "type": "number"},
            ],
            "data_structure": "data",
            "beta_features": {},
        }
        base.update(overrides)
        return ExtractionModel(**base)

    return _make


# ---------------------------------------------------------------------------
# Asyncio event loop policy for Windows/macOS consistency
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default policy; declaring the fixture silences pytest-asyncio
    deprecation warnings about implicit policy usage."""
    return asyncio.get_event_loop_policy()
