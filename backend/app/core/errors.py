"""
Shared error-handling utilities for service and endpoint code.

Consolidates the repeated try/except → logger.error → `return {"error": ...}`
pattern that appears ~11 times across the extraction services. The output
shape is byte-compatible with the legacy pattern so downstream callers
(including the frontend) see no contract change.

Two entry points:

1. `error_response(context, exc, *, include_tb=False)` — build the legacy
   error dict after catching an exception. Use this inside an `except`
   block.

2. `@log_and_wrap(context, include_tb=False)` — decorator that wraps an
   async function: on exception, logs + returns `error_response(...)`.
   Use when the whole function body should share the same handling.

Both preserve the existing "error" key and message format, including the
optional "\\n\\nTraceback:\\n..." suffix that some callers relied on.
"""
from __future__ import annotations

import functools
import logging
import traceback
from typing import Any, Awaitable, Callable, Dict, Optional


def error_response(
    context: str,
    exc: BaseException,
    *,
    include_tb: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """Build an error-payload dict and log the failure.

    Args:
        context: Short phrase identifying the stage that failed, used in
            both the log line and the returned message. Examples:
            "Native Python Excel Engine", "Vision extraction".
        exc: The caught exception.
        include_tb: When True, append a formatted traceback to the
            returned message — matches the historic behavior of several
            call sites that surfaced raw tracebacks to the frontend for
            debugging.
        logger: Optional logger; defaults to the module logger of this
            file. Callers typically pass their own so the log line shows
            the right origin.

    Returns:
        {"error": "<context> failed: <exc>\\n\\nTraceback:\\n<tb>"} when
        include_tb is True, else {"error": "<context> failed: <exc>"}.
    """
    log = logger or _default_logger
    log.error(f"[{context}] {exc}", exc_info=include_tb)

    msg = f"{context} failed: {exc}"
    if include_tb:
        tb = traceback.format_exc()
        msg = f"{msg}\n\nTraceback:\n{tb}"
    return {"error": msg}


def log_and_wrap(
    context: str,
    *,
    include_tb: bool = False,
    logger: Optional[logging.Logger] = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator: wrap an async function so uncaught exceptions become
    error dicts instead of propagating.

    Example:
        @log_and_wrap("OCR", include_tb=True, logger=logger)
        async def run_ocr(...): ...

    The wrapped function still returns its normal result on success.
    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — broad by design
                return error_response(context, exc, include_tb=include_tb, logger=logger)
        return wrapper
    return decorator


_default_logger = logging.getLogger(__name__)
