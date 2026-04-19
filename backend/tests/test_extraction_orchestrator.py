"""
Tests for extraction_orchestrator.run_pipeline_job.

Pins the Job + Log dual-update behavior that Phase 4b's `sync_update`
helper must reproduce exactly. These tests monkeypatch the collaborator
modules (extraction_jobs, extraction_logs, extraction_service, storage,
models) so each test runs in isolation without Cosmos / Blob calls.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.enums import ExtractionStatus


# ---------------------------------------------------------------------------
# Shared orchestrator fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def orchestrator_env(monkeypatch):
    """Patch every collaborator of run_pipeline_job so we can assert on the
    orchestration order and argument wiring.

    Returns a SimpleNamespace of the installed mocks.
    """
    from app.services import extraction_orchestrator as orch
    from app.services import extraction_jobs as ej
    from app.services import extraction_logs as el
    from app.services import extraction_service as es
    from app.services import storage
    from app.services import models as mdl

    # Track all updates in order so tests can verify sequence.
    update_history = []

    update_job_mock = AsyncMock(
        side_effect=lambda job_id, **kwargs: update_history.append(("job", job_id, kwargs))
    )
    update_log_mock = AsyncMock(
        side_effect=lambda log_id, **kwargs: update_history.append(("log", log_id, kwargs))
    )

    # Default job: has original_log_id so dual-update path is exercised.
    default_job = SimpleNamespace(id="job-1", original_log_id="log-1")
    get_job_mock = AsyncMock(return_value=default_job)

    monkeypatch.setattr(ej, "update_job", update_job_mock)
    monkeypatch.setattr(ej, "get_job", get_job_mock)
    monkeypatch.setattr(el, "update_log_status", update_log_mock)

    # Extraction service returns a controllable payload.
    pipeline_result = {"guide_extracted": {"ok": {"value": "v"}}, "other_data": []}
    pipeline_mock = AsyncMock(return_value=pipeline_result)
    monkeypatch.setattr(
        es.extraction_service, "run_extraction_pipeline", pipeline_mock
    )

    # Download stub — non-empty bytes so the orchestrator proceeds.
    download_mock = AsyncMock(return_value=b"fake-file-content")
    monkeypatch.setattr(storage, "download_blob_to_bytes", download_mock, raising=False)

    # Model stub — non-comparison model so we hit the extraction branch.
    sample_model = SimpleNamespace(
        id="model-1",
        model_type="extraction",
        beta_features={},
        reference_data=None,
        dictionaries=None,
    )
    get_model_mock = AsyncMock(return_value=sample_model)
    monkeypatch.setattr(orch, "get_model_by_id", get_model_mock)

    # Suppress the Vibe Dictionary fire-and-forget side effect.
    async def _noop(*args, **kwargs):
        return None
    try:
        from app.services.dictionary import vibe_dictionary as vd
        monkeypatch.setattr(vd, "generate_vibe_dictionary_async", _noop, raising=False)
    except ImportError:
        pass

    return SimpleNamespace(
        update_job=update_job_mock,
        update_log=update_log_mock,
        get_job=get_job_mock,
        get_model=get_model_mock,
        pipeline=pipeline_mock,
        download=download_mock,
        history=update_history,
        default_job=default_job,
        pipeline_result=pipeline_result,
    )


# ---------------------------------------------------------------------------
# Success path: both job and log get PREVIEW_READY
# ---------------------------------------------------------------------------

class TestOrchestratorSuccess:
    @pytest.mark.asyncio
    async def test_success_updates_both_job_and_log(self, orchestrator_env):
        from app.services.extraction_orchestrator import run_pipeline_job

        await run_pipeline_job(
            job_id="job-1",
            model_id="model-1",
            file_url="mock://blob/x.pdf",
        )

        # Expect at least 2 updates: ANALYZING first, then PREVIEW_READY
        job_updates = [h for h in orchestrator_env.history if h[0] == "job"]
        log_updates = [h for h in orchestrator_env.history if h[0] == "log"]

        # First job update → ANALYZING
        assert job_updates[0][2]["status"] == ExtractionStatus.ANALYZING.value

        # Final job + log updates → PREVIEW_READY with preview_data
        final_job = job_updates[-1]
        assert final_job[2]["status"] == ExtractionStatus.PREVIEW_READY.value
        assert final_job[2]["preview_data"] == orchestrator_env.pipeline_result

        assert len(log_updates) == 1
        final_log = log_updates[0]
        assert final_log[1] == "log-1"
        assert final_log[2]["status"] == ExtractionStatus.PREVIEW_READY.value
        assert final_log[2]["preview_data"] == orchestrator_env.pipeline_result

    @pytest.mark.asyncio
    async def test_success_calls_pipeline_with_downloaded_bytes(self, orchestrator_env):
        from app.services.extraction_orchestrator import run_pipeline_job

        await run_pipeline_job(
            job_id="job-1",
            model_id="model-1",
            file_url="mock://blob/invoice.pdf",
        )

        orchestrator_env.pipeline.assert_awaited_once()
        kwargs = orchestrator_env.pipeline.await_args.kwargs
        assert kwargs["file_content"] == b"fake-file-content"
        assert kwargs["model_id"] == "model-1"
        assert kwargs["filename"] == "invoice.pdf"


# ---------------------------------------------------------------------------
# No original_log_id: only the job gets updated
# ---------------------------------------------------------------------------

class TestOrchestratorNoLogId:
    @pytest.mark.asyncio
    async def test_missing_log_id_skips_log_update(self, orchestrator_env):
        # Swap the default job for one without an original_log_id.
        orchestrator_env.get_job.return_value = SimpleNamespace(
            id="job-no-log", original_log_id=None
        )

        from app.services.extraction_orchestrator import run_pipeline_job

        await run_pipeline_job(
            job_id="job-no-log",
            model_id="model-1",
            file_url="mock://blob/x.pdf",
        )

        # Job still updated; log never touched.
        assert any(h[0] == "job" for h in orchestrator_env.history)
        assert not any(h[0] == "log" for h in orchestrator_env.history)


# ---------------------------------------------------------------------------
# Failure path: pipeline returns error → both marked ERROR
# ---------------------------------------------------------------------------

class TestOrchestratorPipelineError:
    @pytest.mark.asyncio
    async def test_error_result_marks_both_error(self, orchestrator_env):
        orchestrator_env.pipeline.return_value = {"error": "LLM crashed"}

        from app.services.extraction_orchestrator import run_pipeline_job

        await run_pipeline_job(
            job_id="job-1",
            model_id="model-1",
            file_url="mock://blob/x.pdf",
        )

        job_updates = [h for h in orchestrator_env.history if h[0] == "job"]
        log_updates = [h for h in orchestrator_env.history if h[0] == "log"]

        # Final job state = ERROR with error message
        error_job = job_updates[-1]
        assert error_job[2]["status"] == ExtractionStatus.ERROR.value
        assert error_job[2]["error"] == "LLM crashed"

        assert len(log_updates) == 1
        assert log_updates[0][2]["status"] == ExtractionStatus.ERROR.value
        assert log_updates[0][2]["error"] == "LLM crashed"


# ---------------------------------------------------------------------------
# Download failure path
# ---------------------------------------------------------------------------

class TestOrchestratorDownloadFailure:
    @pytest.mark.asyncio
    async def test_download_raise_triggers_error_path(self, orchestrator_env):
        orchestrator_env.download.side_effect = RuntimeError("blob 404")

        from app.services.extraction_orchestrator import run_pipeline_job

        await run_pipeline_job(
            job_id="job-1",
            model_id="model-1",
            file_url="mock://blob/x.pdf",
        )

        # Pipeline never ran
        orchestrator_env.pipeline.assert_not_awaited()

        # Both job and log marked ERROR with a download-failure message
        job_error = [h for h in orchestrator_env.history if h[0] == "job"][-1]
        log_error = [h for h in orchestrator_env.history if h[0] == "log"][-1]
        assert job_error[2]["status"] == ExtractionStatus.ERROR.value
        assert "download" in job_error[2]["error"].lower()
        assert log_error[2]["status"] == ExtractionStatus.ERROR.value


# ---------------------------------------------------------------------------
# Model not found path
# ---------------------------------------------------------------------------

class TestOrchestratorModelNotFound:
    @pytest.mark.asyncio
    async def test_missing_model_marks_error_and_returns(self, orchestrator_env):
        orchestrator_env.get_model.return_value = None

        from app.services.extraction_orchestrator import run_pipeline_job

        await run_pipeline_job(
            job_id="job-1",
            model_id="missing",
            file_url="mock://blob/x.pdf",
        )

        # Pipeline never ran
        orchestrator_env.pipeline.assert_not_awaited()

        job_updates = [h for h in orchestrator_env.history if h[0] == "job"]
        final = job_updates[-1]
        assert final[2]["status"] == ExtractionStatus.ERROR.value
        assert "missing" in final[2]["error"].lower() or "not found" in final[2]["error"].lower()
