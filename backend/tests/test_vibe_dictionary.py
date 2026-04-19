"""
Regression tests for Vibe Dictionary N+1 prevention.

The `GET /vibe-dictionary/` handler previously fetched the parent model
name once per vibe entry (N+1). The current impl pre-fetches all model
names in a single query (vibe_dictionary.py:27-30). These tests pin that
behavior so a future refactor can't regress it.

Strategy: use the mock_cosmos fixture to count query_items invocations
per container, then assert exactly 1 models-query regardless of entry count.
"""
from __future__ import annotations

import pytest
from app.db import cosmos as cosmos_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_vibe_data(mock_cosmos, *, model_count: int, entries_per_model: int):
    """Populate the mock cosmos with `model_count` models and
    `entries_per_model` vibe entries per model."""
    models = mock_cosmos[cosmos_module.MODELS_CONTAINER]
    vibes = mock_cosmos[cosmos_module.VIBE_DICTIONARY_CONTAINER]

    for i in range(model_count):
        mid = f"model-{i}"
        models.items[mid] = {
            "id": mid,
            "name": f"Model {i}",
            "model_type": "extraction",
            "is_active": True,
        }
        for j in range(entries_per_model):
            eid = f"{mid}-entry-{j}"
            vibes.items[eid] = {
                "id": eid,
                "model_id": mid,
                "field_name": f"field_{j}",
                "raw_val": f"raw_{j}",
                "value": f"standard_{j}",
                "source": "MANUAL",
                "hit_count": entries_per_model - j,
                "is_verified": False,
            }


# ---------------------------------------------------------------------------
# N+1 regression
# ---------------------------------------------------------------------------

class TestVibeDictionaryN1:
    @pytest.mark.asyncio
    async def test_list_does_one_models_query_regardless_of_entry_count(
        self,
        async_client,
        mock_cosmos,
        override_current_user,
    ):
        # 2 models × 5 entries = 10 vibe rows. An N+1 impl would issue
        # 10 models-container queries; the correct impl issues exactly 1.
        _seed_vibe_data(mock_cosmos, model_count=2, entries_per_model=5)

        resp = await async_client.get("/api/v1/vibe-dictionary/")
        assert resp.status_code == 200

        models_queries = [
            entry for entry in mock_cosmos[cosmos_module.MODELS_CONTAINER].call_log
            if entry.startswith("query_items")
        ]
        assert len(models_queries) == 1, (
            f"Expected exactly 1 models-query (N+1 prevention); got "
            f"{len(models_queries)}: {models_queries}"
        )

    @pytest.mark.asyncio
    async def test_list_returns_correct_entry_count_and_shape(
        self,
        async_client,
        mock_cosmos,
        override_current_user,
    ):
        _seed_vibe_data(mock_cosmos, model_count=3, entries_per_model=4)

        resp = await async_client.get("/api/v1/vibe-dictionary/")
        assert resp.status_code == 200
        data = resp.json()

        # 3 * 4 = 12 entries
        assert len(data) == 12

        # Each entry has the expected keys
        expected_keys = {
            "model_id", "model_name", "field_name",
            "raw_val", "standard_val", "source",
            "hit_count", "is_verified",
        }
        assert all(expected_keys == set(entry.keys()) for entry in data)

    @pytest.mark.asyncio
    async def test_list_joins_model_name_into_each_entry(
        self,
        async_client,
        mock_cosmos,
        override_current_user,
    ):
        _seed_vibe_data(mock_cosmos, model_count=2, entries_per_model=1)

        resp = await async_client.get("/api/v1/vibe-dictionary/")
        assert resp.status_code == 200
        data = resp.json()

        # Each vibe entry should carry the parent model's name.
        for entry in data:
            if entry["model_id"] == "model-0":
                assert entry["model_name"] == "Model 0"
            elif entry["model_id"] == "model-1":
                assert entry["model_name"] == "Model 1"

    @pytest.mark.asyncio
    async def test_entries_from_inactive_model_are_filtered(
        self,
        async_client,
        mock_cosmos,
        override_current_user,
    ):
        # Seed one active + one inactive model, each with entries.
        models = mock_cosmos[cosmos_module.MODELS_CONTAINER]
        vibes = mock_cosmos[cosmos_module.VIBE_DICTIONARY_CONTAINER]

        models.items["active"] = {
            "id": "active", "name": "Active", "model_type": "extraction", "is_active": True,
        }
        models.items["inactive"] = {
            "id": "inactive", "name": "Inactive", "model_type": "extraction", "is_active": False,
        }
        vibes.items["v1"] = {
            "id": "v1", "model_id": "active", "field_name": "f", "raw_val": "r",
            "value": "s", "source": "MANUAL", "hit_count": 1, "is_verified": False,
        }
        vibes.items["v2"] = {
            "id": "v2", "model_id": "inactive", "field_name": "f", "raw_val": "r",
            "value": "s", "source": "MANUAL", "hit_count": 1, "is_verified": False,
        }

        # The handler pulls models via
        # "SELECT ... WHERE c.model_type = 'extraction' AND c.is_active = true"
        # Our in-memory mock can't parse that, but we can verify filtering
        # by making the models container yield only active model rows via
        # a subclass-style query override.
        original_query = models.query_items

        async def _filtered_query(query, parameters=None, **kwargs):
            async for item in original_query(query, parameters, **kwargs):
                if item.get("is_active"):
                    yield item

        models.query_items = _filtered_query

        resp = await async_client.get("/api/v1/vibe-dictionary/")
        assert resp.status_code == 200
        data = resp.json()

        assert all(entry["model_id"] == "active" for entry in data)
        assert not any(entry["model_id"] == "inactive" for entry in data)
