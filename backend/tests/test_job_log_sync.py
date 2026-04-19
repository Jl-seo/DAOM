"""
Tests for job_log_sync.sync_update — the helper that replaces the
duplicated Job+Log update pattern.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def sync_env(monkeypatch):
    """Patch extraction_jobs and extraction_logs with AsyncMocks.

    Returns an object exposing the mocks and a helper to set the
    "linked log id" on the job returned by get_job.
    """
    from app.services import extraction_jobs as ej
    from app.services import extraction_logs as el

    state = {"job": SimpleNamespace(id="j1", original_log_id="log-1")}

    get_job = AsyncMock(side_effect=lambda jid: state["job"])
    update_job = AsyncMock(return_value=None)
    update_log = AsyncMock(return_value=True)

    monkeypatch.setattr(ej, "get_job", get_job)
    monkeypatch.setattr(ej, "update_job", update_job)
    monkeypatch.setattr(el, "update_log_status", update_log)

    return SimpleNamespace(
        get_job=get_job,
        update_job=update_job,
        update_log=update_log,
        set_job=lambda j: state.update(job=j),
    )


class TestSyncUpdate:
    @pytest.mark.asyncio
    async def test_updates_both_when_linked(self, sync_env):
        from app.services.job_log_sync import sync_update

        await sync_update("j1", status="S100", preview_data={"x": 1})

        sync_env.update_job.assert_awaited_once_with(
            "j1", status="S100", preview_data={"x": 1}
        )
        sync_env.update_log.assert_awaited_once_with(
            log_id="log-1", status="S100", preview_data={"x": 1}
        )

    @pytest.mark.asyncio
    async def test_skips_log_when_no_original_log_id(self, sync_env):
        sync_env.set_job(SimpleNamespace(id="j2", original_log_id=None))

        from app.services.job_log_sync import sync_update
        await sync_update("j2", status="E100", error="boom")

        sync_env.update_job.assert_awaited_once()
        sync_env.update_log.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_job_fetch_failure_still_updates_job(self, sync_env):
        # get_job raises; update_job still runs; log skipped.
        sync_env.get_job.side_effect = RuntimeError("cosmos down")

        from app.services.job_log_sync import sync_update
        await sync_update("j1", status="P300")

        sync_env.update_job.assert_awaited_once_with("j1", status="P300")
        sync_env.update_log.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_forwards_only_whitelisted_fields_to_log(self, sync_env):
        from app.services.job_log_sync import sync_update

        # Include a field not in LOG_FIELDS (say, a hypothetical "webhook_sent").
        await sync_update(
            "j1",
            status="S100",
            preview_data={"x": 1},
            # unknown field — should NOT leak into the log update
            debug_hint="some-flag",
        )

        sync_env.update_job.assert_awaited_once_with(
            "j1", status="S100", preview_data={"x": 1}, debug_hint="some-flag"
        )
        # Log only gets whitelisted fields
        assert sync_env.update_log.await_count == 1
        assert sync_env.update_log.await_args.kwargs == {
            "log_id": "log-1",
            "status": "S100",
            "preview_data": {"x": 1},
        }

    @pytest.mark.asyncio
    async def test_noop_log_when_no_log_fields_supplied(self, sync_env):
        # Only non-log fields → we still update job, skip log to avoid empty call.
        from app.services.job_log_sync import sync_update
        await sync_update("j1", some_job_only_field=42)

        sync_env.update_job.assert_awaited_once_with("j1", some_job_only_field=42)
        sync_env.update_log.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_failure_does_not_propagate(self, sync_env):
        sync_env.update_log.side_effect = RuntimeError("log write failed")

        from app.services.job_log_sync import sync_update
        # Should not raise
        await sync_update("j1", status="S100")

        sync_env.update_job.assert_awaited_once()
        sync_env.update_log.assert_awaited_once()
