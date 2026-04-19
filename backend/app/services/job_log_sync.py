"""
Helper for the recurring pattern of updating an extraction Job and its
linked Log in tandem.

Background: the orchestrator (extraction_orchestrator.py) and several
job-handling endpoints repeat ~6 times a block that:
  1. fetches the Job to check for `original_log_id`
  2. calls `extraction_jobs.update_job(job_id, ...)`
  3. if the job has `original_log_id`, also calls
     `extraction_logs.update_log_status(log_id, ...)`

This file consolidates that block into `sync_update(job_id, **fields)`.
Only fields relevant to the Log are forwarded — see LOG_FIELDS. All
behavior is preserved: if the job has no linked log, only the job is
touched; if the Cosmos fetch fails, we log but don't raise.
"""
from __future__ import annotations

import logging
from typing import Any

from app.services import extraction_jobs, extraction_logs

logger = logging.getLogger(__name__)


# Fields that update_log_status accepts. Any keyword passed to
# sync_update() that is not in this set is silently dropped when
# forwarding to the log (but still forwarded to the job).
LOG_FIELDS = frozenset({
    "status",
    "preview_data",
    "extracted_data",
    "debug_data",
    "error",
    "token_usage",
})


async def sync_update(job_id: str, **fields: Any) -> None:
    """Update the job and its linked log with the same field set.

    Args:
        job_id: The extraction job ID.
        **fields: Any fields accepted by `extraction_jobs.update_job`.
            Fields also in LOG_FIELDS are forwarded to
            `extraction_logs.update_log_status` via the job's
            `original_log_id`.

    Errors are logged but not raised — this helper is called from
    background tasks where a Cosmos failure should not kill the whole
    pipeline. Callers that need to know about failures should use the
    lower-level update functions directly.
    """
    try:
        job = await extraction_jobs.get_job(job_id)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[JobLogSync] Failed to fetch job {job_id}: {exc}")
        job = None

    try:
        await extraction_jobs.update_job(job_id, **fields)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[JobLogSync] Failed to update job {job_id}: {exc}")

    log_id = getattr(job, "original_log_id", None) if job else None
    if not log_id:
        return

    log_fields = {k: v for k, v in fields.items() if k in LOG_FIELDS}
    if not log_fields:
        return

    try:
        await extraction_logs.update_log_status(log_id=str(log_id), **log_fields)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            f"[JobLogSync] Failed to update log {log_id} "
            f"(linked to job {job_id}): {exc}"
        )
