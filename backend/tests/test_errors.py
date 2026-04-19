"""
Contract tests for app.core.errors — ensures the legacy error-dict
shape survives the consolidation.
"""
from __future__ import annotations

import logging

import pytest

from app.core.errors import error_response, log_and_wrap


class TestErrorResponse:
    def test_basic_shape_matches_legacy(self):
        try:
            raise ValueError("bad input")
        except ValueError as exc:
            out = error_response("OCR", exc)

        assert set(out.keys()) == {"error"}
        assert out["error"] == "OCR failed: bad input"

    def test_include_tb_appends_traceback_block(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            out = error_response("Pipeline", exc, include_tb=True)

        assert out["error"].startswith("Pipeline failed: boom")
        assert "\n\nTraceback:\n" in out["error"]
        assert "RuntimeError: boom" in out["error"]

    def test_logs_the_failure(self, caplog):
        caplog.set_level(logging.ERROR)
        try:
            raise ValueError("oops")
        except ValueError as exc:
            error_response("Stage", exc)

        assert any(
            "[Stage] oops" in rec.getMessage()
            for rec in caplog.records
        )


class TestLogAndWrap:
    @pytest.mark.asyncio
    async def test_returns_value_on_success(self):
        @log_and_wrap("Stage")
        async def ok():
            return {"guide_extracted": {}, "other_data": []}

        result = await ok()
        assert result == {"guide_extracted": {}, "other_data": []}

    @pytest.mark.asyncio
    async def test_returns_error_dict_on_exception(self):
        @log_and_wrap("Stage")
        async def bad():
            raise RuntimeError("fail")

        result = await bad()
        assert result == {"error": "Stage failed: fail"}

    @pytest.mark.asyncio
    async def test_include_tb_passes_through(self):
        @log_and_wrap("Stage", include_tb=True)
        async def bad():
            raise ValueError("v")

        result = await bad()
        assert "Traceback:" in result["error"]
        assert "ValueError: v" in result["error"]
