"""
Tests for the Beta-pipeline → job.debug_data wiring.

Before this feature, the Designer-Engineer pipeline generated rich
diagnostic artifacts (Work Order, Engineer prompts, raw LLM response,
tagged text) and then discarded them. The frontend debug modal was
therefore empty in every case.

These tests pin two contracts:

1.  Orchestrator contract: when the pipeline returns a dict containing
    `_debug`, `run_pipeline_job` must split it off and call
    `sync_update(preview_data=<rest>, debug_data=<_debug>)`. The
    `_debug` key MUST NOT leak into preview_data (which would bloat
    the UI payload).

2.  BetaPipeline contract: `BetaPipeline.execute` must attach a
    `_debug` bundle to `ExtractionResult.beta_metadata` with the
    keys the frontend modal expects (work_order,
    engineer_raw_response, engineer_prompts).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


# ---------------------------------------------------------------------------
# 1. Orchestrator: _debug split-off + sync_update wiring
# ---------------------------------------------------------------------------

@pytest.fixture
def debug_orch_env(monkeypatch):
    """Minimal orchestrator env with collaborators mocked."""
    from app.services import extraction_orchestrator as orch
    from app.services import extraction_jobs as ej
    from app.services import extraction_logs as el
    from app.services import extraction_service as es
    from app.services import storage

    update_history = []

    update_job = AsyncMock(
        side_effect=lambda job_id, **kwargs: update_history.append(("job", job_id, kwargs))
    )
    update_log = AsyncMock(
        side_effect=lambda log_id, **kwargs: update_history.append(("log", log_id, kwargs))
    )
    get_job = AsyncMock(return_value=SimpleNamespace(id="j1", original_log_id="log-1"))

    monkeypatch.setattr(ej, "update_job", update_job)
    monkeypatch.setattr(ej, "get_job", get_job)
    monkeypatch.setattr(el, "update_log_status", update_log)

    # Storage stub
    monkeypatch.setattr(
        storage, "download_blob_to_bytes",
        AsyncMock(return_value=b"fake"), raising=False
    )

    # Non-comparison model
    sample_model = SimpleNamespace(
        id="model-1", model_type="extraction",
        beta_features={}, reference_data=None, dictionaries=None,
    )
    monkeypatch.setattr(orch, "get_model_by_id", AsyncMock(return_value=sample_model))

    # Silence the fire-and-forget vibe-dictionary spawn
    try:
        from app.services.dictionary import vibe_dictionary as vd
        monkeypatch.setattr(
            vd, "generate_vibe_dictionary_async",
            AsyncMock(return_value=None), raising=False,
        )
    except ImportError:
        pass

    # pipeline_mock: caller controls what run_extraction_pipeline returns
    pipeline_mock = AsyncMock()
    monkeypatch.setattr(es.extraction_service, "run_extraction_pipeline", pipeline_mock)

    return SimpleNamespace(
        history=update_history,
        update_job=update_job,
        update_log=update_log,
        pipeline=pipeline_mock,
    )


class TestDebugDataSplitOff:
    @pytest.mark.asyncio
    async def test_debug_key_is_moved_from_preview_to_debug_data(self, debug_orch_env):
        """Happy path: pipeline returns result with `_debug`. Orchestrator
        must pass `debug_data=<_debug>` to sync_update and NOT include
        `_debug` inside `preview_data`."""
        debug_orch_env.pipeline.return_value = {
            "guide_extracted": {"invoice": {"value": "INV-1"}},
            "other_data": [],
            "_debug": {
                "work_order": {"w": 1},
                "engineer_raw_response": {"guide_extracted": {"invoice": "INV-1"}},
            },
        }

        from app.services.extraction_orchestrator import run_pipeline_job
        await run_pipeline_job(
            job_id="j1",
            model_id="model-1",
            file_url="mock://blob/x.pdf",
        )

        # Find the PREVIEW_READY job update
        preview_updates = [
            h for h in debug_orch_env.history
            if h[0] == "job" and h[2].get("status") == "S100"
            or (h[0] == "job" and "preview_data" in h[2])
        ]
        assert preview_updates, "No final preview-ready update recorded"
        final = preview_updates[-1][2]

        # debug_data is populated
        assert final.get("debug_data") is not None
        assert final["debug_data"]["work_order"] == {"w": 1}

        # preview_data does NOT still carry _debug
        assert "_debug" not in final["preview_data"]

    @pytest.mark.asyncio
    async def test_missing_debug_key_yields_none_debug_data(self, debug_orch_env):
        """When the pipeline returns no `_debug`, `debug_data` must be
        passed as None (not omitted), so callers can distinguish 'no debug
        captured' from 'not updated yet'."""
        debug_orch_env.pipeline.return_value = {
            "guide_extracted": {"x": {"value": "y"}},
            "other_data": [],
        }

        from app.services.extraction_orchestrator import run_pipeline_job
        await run_pipeline_job(
            job_id="j1",
            model_id="model-1",
            file_url="mock://blob/x.pdf",
        )

        preview_updates = [
            h for h in debug_orch_env.history
            if h[0] == "job" and "preview_data" in h[2]
        ]
        assert preview_updates
        final = preview_updates[-1][2]
        # Key is explicitly present with None, not absent.
        assert "debug_data" in final
        assert final["debug_data"] is None

    @pytest.mark.asyncio
    async def test_debug_data_is_forwarded_to_linked_log(self, debug_orch_env):
        """When the job has an original_log_id, the same debug_data must
        also reach the log (via sync_update's LOG_FIELDS whitelist)."""
        debug_orch_env.pipeline.return_value = {
            "guide_extracted": {},
            "other_data": [],
            "_debug": {"work_order": {"cache_hit": True}},
        }

        from app.services.extraction_orchestrator import run_pipeline_job
        await run_pipeline_job(
            job_id="j1",
            model_id="model-1",
            file_url="mock://blob/x.pdf",
        )

        log_updates = [h for h in debug_orch_env.history if h[0] == "log"]
        assert log_updates, "Expected linked log to be updated"
        final_log = log_updates[-1][2]
        assert final_log.get("debug_data") == {"work_order": {"cache_hit": True}}


# ---------------------------------------------------------------------------
# 2. BetaPipeline: execute() attaches _debug to beta_metadata
# ---------------------------------------------------------------------------

@pytest.fixture
def beta_pipeline_env(monkeypatch, make_model):
    """Patch the BetaPipeline's Designer and Engineer LLM calls so we can
    drive execute() end-to-end without touching Azure OpenAI."""
    from app.services.extraction import beta_pipeline as bp

    # Clear the global work-order cache so each test gets a fresh Designer call
    bp._work_order_cache.clear()

    # Fake Designer output (what _run_designer would return)
    designer_work_order = {
        "work_order": {
            "common_fields": [{"key": "invoice_number", "type": "string"}],
            "table_fields": [],
        }
    }

    async def fake_designer(self, model):
        return designer_work_order

    # Fake Engineer output — must contain guide_extracted + _debug_prompts
    # (the latter is added by the real _run_engineer; stubbing bypasses it,
    # so we include it manually to simulate the real path)
    engineer_output = {
        "guide_extracted": {"invoice_number": {"value": "INV-42", "ref": "[#5]"}},
        "_token_usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        "_debug_prompts": {
            "mode": "single-shot",
            "system": "ENGINEER_SYSTEM_PROMPT",
            "user_preview": "DOCUMENT DATA ...",
        },
    }

    async def fake_engineer(self, work_order, tagged_text, model=None):
        return engineer_output

    monkeypatch.setattr(bp.BetaPipeline, "_run_designer", fake_designer)
    monkeypatch.setattr(bp.BetaPipeline, "_run_engineer", fake_engineer)

    # Also stub post_process_with_ref so we don't need real ref maps
    from app.services.refiner import RefinerEngine
    monkeypatch.setattr(
        RefinerEngine, "post_process_with_ref",
        staticmethod(lambda out, ref_map: {"guide_extracted": out.get("guide_extracted", {})}),
    )

    return SimpleNamespace(
        designer_work_order=designer_work_order,
        engineer_output=engineer_output,
    )


class TestBetaPipelineDebugBundle:
    @pytest.mark.asyncio
    async def test_execute_attaches_debug_bundle(self, beta_pipeline_env, make_model):
        from app.services.extraction.beta_pipeline import BetaPipeline

        model = make_model(fields=[
            {"key": "invoice_number", "label": "Invoice", "type": "string"},
        ])

        # Small synthetic OCR payload so LayoutParser picks a quick path.
        ocr_data = {
            "content": "Invoice Number: INV-42",
            "pages": [{"page_number": 1, "width": 612, "height": 792}],
            "tables": [],
            "paragraphs": [],
            "_is_direct_markdown": True,  # Skip LayoutParser
        }

        pipeline = BetaPipeline(azure_client=None)
        result = await pipeline.execute(model, ocr_data)

        # beta_metadata carries the diagnostic bundle
        assert result.beta_metadata is not None
        debug = result.beta_metadata.get("_debug")
        assert debug is not None, "BetaPipeline must attach _debug to beta_metadata"

        # Keys the frontend debug modal relies on
        assert "work_order" in debug
        assert "engineer_raw_response" in debug
        assert "engineer_prompts" in debug
        assert "tagged_text_preview" in debug
        assert "token_usage" in debug

        # Work order is the real Designer output
        assert debug["work_order"] == beta_pipeline_env.designer_work_order

        # Engineer prompts include system + user preview
        assert debug["engineer_prompts"]["mode"] == "single-shot"
        assert debug["engineer_prompts"]["system"] == "ENGINEER_SYSTEM_PROMPT"
