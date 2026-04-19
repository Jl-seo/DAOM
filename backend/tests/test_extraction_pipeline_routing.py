"""
Pipeline dispatch tests — the safety net for Phase 4 refactoring.

`ExtractionService.run_extraction_pipeline` contains 5 logical routes.
These tests assert which downstream pipeline is invoked for each combination
of model flags and file type, without exercising the real pipelines.

When run_extraction_pipeline is refactored into a strategy-pattern dispatcher,
these tests must continue to pass unchanged — that's how we prove behavior
preservation.

Routes asserted:
1. Excel file (mime or extension) → sql_extraction.run_sql_extraction
2. use_vision_extraction=True    → VisionExtractionPipeline.execute
3. use_multi_table_analyzer=True → AdvancedTablePipeline.execute
4. use_optimized_prompt=True     → BetaPipeline.execute
5. General mode, small payload   → direct LLM call (no pipeline class)
6. General mode, large payload   → BetaPipeline.execute (auto-switch)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.model import ExtractionModel
from app.services.extraction_service import ExtractionService
from app.services.extraction.core import ExtractionResult, TokenUsage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_standard_result(guide: Optional[Dict[str, Any]] = None) -> ExtractionResult:
    return ExtractionResult(
        guide_extracted=guide or {},
        raw_content="",
        token_usage=TokenUsage(),
        other_data=[],
    )


@pytest.fixture
def patch_get_model(monkeypatch, make_model):
    """Patch ExtractionService's `get_model_by_id` import to return a test model.

    Returns a setter the test can use to swap which model is returned.
    """
    from app.services import extraction_service as es_module

    state: Dict[str, Any] = {"model": make_model()}

    async def _get(model_id: str):
        return state["model"]

    monkeypatch.setattr(es_module, "get_model_by_id", _get)

    def set_model(**overrides):
        state["model"] = make_model(**overrides)

    return set_model


@pytest.fixture
def patch_ocr(monkeypatch, load_fixture):
    """Patch analyze_document_layout to return a controllable OCR payload.

    `extraction_service.run_extraction_pipeline` re-imports the function
    inline (`from app.services.doc_intel import analyze_document_layout`)
    so we must patch the source module, not just the caller.
    """
    from app.services import doc_intel as di_module
    from app.services import extraction_service as es_module

    state: Dict[str, Any] = {"ocr": load_fixture("ocr_invoice_single_page")}
    state["ocr"].setdefault("pages", [{"page_number": 1, "width": 612, "height": 792}])

    async def _analyze(*args, **kwargs):
        return state["ocr"]

    monkeypatch.setattr(di_module, "analyze_document_layout", _analyze)
    monkeypatch.setattr(es_module, "analyze_document_layout", _analyze)

    def set_ocr(payload: Dict[str, Any]):
        state["ocr"] = payload

    return set_ocr


@pytest.fixture
def extraction_service(mock_azure_openai):
    return ExtractionService()


# ---------------------------------------------------------------------------
# Route 1: Excel file → SQL extraction
# ---------------------------------------------------------------------------

class TestExcelRoute:
    @pytest.mark.asyncio
    async def test_xlsx_extension_triggers_sql_extraction(
        self, extraction_service, patch_get_model
    ):
        with patch(
            "app.services.extraction.sql_extraction.run_sql_extraction",
            new=AsyncMock(return_value={"guide_extracted": {}, "other_data": []}),
        ) as sql_mock, patch(
            "app.services.extraction.excel_parser.ExcelParser.from_bytes",
            return_value=[{"content": "Sheet1 md"}],
        ):
            result = await extraction_service.run_extraction_pipeline(
                file_content=b"fake-xlsx",
                model_id="model-test-001",
                filename="sales.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        assert sql_mock.await_count == 1
        assert result.get("_meta", {}).get("pipeline_mode") == "python-excel-engine"

    @pytest.mark.asyncio
    async def test_csv_mime_triggers_sql_extraction(
        self, extraction_service, patch_get_model
    ):
        with patch(
            "app.services.extraction.sql_extraction.run_sql_extraction",
            new=AsyncMock(return_value={"guide_extracted": {}, "other_data": []}),
        ) as sql_mock, patch(
            "app.services.extraction.excel_parser.ExcelParser.from_bytes",
            return_value=[{"content": "csv md"}],
        ):
            await extraction_service.run_extraction_pipeline(
                file_content=b"a,b,c\n1,2,3",
                model_id="model-test-001",
                filename="data.csv",
                mime_type="text/csv",
            )

        assert sql_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_excel_route_crash_returns_error_dict(
        self, extraction_service, patch_get_model
    ):
        with patch(
            "app.services.extraction.sql_extraction.run_sql_extraction",
            new=AsyncMock(side_effect=RuntimeError("engine down")),
        ), patch(
            "app.services.extraction.excel_parser.ExcelParser.from_bytes",
            return_value=[{"content": "x"}],
        ):
            result = await extraction_service.run_extraction_pipeline(
                file_content=b"fake",
                model_id="model-test-001",
                filename="broken.xlsx",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        assert "error" in result
        assert "engine down" in result["error"]


# ---------------------------------------------------------------------------
# Route 2: Vision mode
# ---------------------------------------------------------------------------

class TestVisionRoute:
    @pytest.mark.asyncio
    async def test_vision_flag_triggers_vision_pipeline(
        self, extraction_service, patch_get_model
    ):
        patch_get_model(beta_features={"use_vision_extraction": True})

        vision_instance = MagicMock()
        vision_instance.execute = AsyncMock(return_value=_make_standard_result())

        with patch(
            "app.services.extraction.vision_extraction.VisionExtractionPipeline",
            return_value=vision_instance,
        ) as cls_mock:
            result = await extraction_service.run_extraction_pipeline(
                file_content=b"img",
                model_id="model-test-001",
                filename="page.png",
                mime_type="image/png",
            )

        assert cls_mock.call_count == 1
        assert vision_instance.execute.await_count == 1
        assert result.get("_meta", {}).get("pipeline_mode") == "vision-extraction"

    @pytest.mark.asyncio
    async def test_vision_skips_ocr_call(self, extraction_service, patch_get_model, monkeypatch):
        patch_get_model(beta_features={"use_vision_extraction": True})

        vision_instance = MagicMock()
        vision_instance.execute = AsyncMock(return_value=_make_standard_result())

        analyze_calls = []

        async def _tracking_analyze(*args, **kwargs):
            analyze_calls.append(True)
            return {"content": "", "pages": []}

        from app.services import extraction_service as es_module
        monkeypatch.setattr(es_module, "analyze_document_layout", _tracking_analyze)

        with patch(
            "app.services.extraction.vision_extraction.VisionExtractionPipeline",
            return_value=vision_instance,
        ):
            await extraction_service.run_extraction_pipeline(
                file_content=b"img",
                model_id="model-test-001",
                filename="page.png",
                mime_type="image/png",
            )

        assert analyze_calls == [], "OCR must be skipped in Vision mode"


# ---------------------------------------------------------------------------
# Routes 3-5: OCR + LLM subroutes
# ---------------------------------------------------------------------------

class TestOCRLLMRoutes:
    @pytest.mark.asyncio
    async def test_multi_table_flag_triggers_advanced_pipeline(
        self, extraction_service, patch_get_model, patch_ocr
    ):
        patch_get_model(beta_features={"use_multi_table_analyzer": True})

        adv_instance = MagicMock()
        adv_instance.execute = AsyncMock(return_value=_make_standard_result())

        beta_instance = MagicMock()
        beta_instance.execute = AsyncMock(return_value=_make_standard_result())

        with patch(
            "app.services.extraction.advanced_table_pipeline.AdvancedTablePipeline",
            return_value=adv_instance,
        ) as adv_cls, patch(
            "app.services.extraction.beta_pipeline.BetaPipeline",
            return_value=beta_instance,
        ) as beta_cls:
            await extraction_service.run_extraction_pipeline(
                file_content=b"pdf",
                model_id="model-test-001",
                filename="doc.pdf",
                mime_type="application/pdf",
            )

        assert adv_cls.call_count == 1
        assert adv_instance.execute.await_count == 1
        assert beta_instance.execute.await_count == 0

    @pytest.mark.asyncio
    async def test_beta_flag_triggers_beta_pipeline(
        self, extraction_service, patch_get_model, patch_ocr
    ):
        patch_get_model(beta_features={"use_optimized_prompt": True})

        beta_instance = MagicMock()
        beta_instance.execute = AsyncMock(return_value=_make_standard_result())

        with patch(
            "app.services.extraction.beta_pipeline.BetaPipeline",
            return_value=beta_instance,
        ):
            await extraction_service.run_extraction_pipeline(
                file_content=b"pdf",
                model_id="model-test-001",
                filename="doc.pdf",
                mime_type="application/pdf",
            )

        assert beta_instance.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_general_small_payload_does_not_use_beta(
        self, extraction_service, patch_get_model, patch_ocr, mock_azure_openai
    ):
        # No beta flags; small payload (well under 40K chars, 1 page).
        # Should NOT auto-switch to BetaPipeline.
        beta_instance = MagicMock()
        beta_instance.execute = AsyncMock(return_value=_make_standard_result())

        # Stub the legacy single-shot path used by _extract_general_mode so we
        # don't depend on its full implementation.
        with patch(
            "app.services.extraction.beta_pipeline.BetaPipeline",
            return_value=beta_instance,
        ), patch.object(
            ExtractionService,
            "_extract_general_mode",
            new=AsyncMock(return_value={
                "guide_extracted": {},
                "raw_content": "",
                "raw_tables": [],
                "pages": [],
                "other_data": [],
            }),
        ) as general_stub:
            await extraction_service.run_extraction_pipeline(
                file_content=b"pdf",
                model_id="model-test-001",
                filename="doc.pdf",
                mime_type="application/pdf",
            )

        assert general_stub.await_count == 1
        assert beta_instance.execute.await_count == 0

    @pytest.mark.asyncio
    async def test_general_large_payload_auto_switches_to_beta(
        self, extraction_service, patch_get_model, patch_ocr
    ):
        # Large OCR payload forces _extract_general_mode → BetaPipeline auto-switch.
        # Trigger: payload_len > 40000 OR page_count > 2.
        patch_ocr({
            "content": "x" * 50000,
            "pages": [{"page_number": 1, "width": 612, "height": 792}],
            "tables": [],
        })

        beta_instance = MagicMock()
        beta_instance.execute = AsyncMock(return_value=_make_standard_result())

        with patch(
            "app.services.extraction.beta_pipeline.BetaPipeline",
            return_value=beta_instance,
        ):
            await extraction_service.run_extraction_pipeline(
                file_content=b"pdf",
                model_id="model-test-001",
                filename="doc.pdf",
                mime_type="application/pdf",
            )

        assert beta_instance.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_general_many_pages_auto_switches_to_beta(
        self, extraction_service, patch_get_model, patch_ocr
    ):
        patch_ocr({
            "content": "small text",
            "pages": [
                {"page_number": 1, "width": 612, "height": 792},
                {"page_number": 2, "width": 612, "height": 792},
                {"page_number": 3, "width": 612, "height": 792},
            ],
            "tables": [],
        })

        beta_instance = MagicMock()
        beta_instance.execute = AsyncMock(return_value=_make_standard_result())

        with patch(
            "app.services.extraction.beta_pipeline.BetaPipeline",
            return_value=beta_instance,
        ):
            await extraction_service.run_extraction_pipeline(
                file_content=b"pdf",
                model_id="model-test-001",
                filename="doc.pdf",
                mime_type="application/pdf",
            )

        assert beta_instance.execute.await_count == 1


# ---------------------------------------------------------------------------
# Model not found
# ---------------------------------------------------------------------------

class TestModelLookupFailure:
    @pytest.mark.asyncio
    async def test_model_not_found_returns_error(
        self, extraction_service, monkeypatch
    ):
        from app.services import extraction_service as es_module

        async def _raise(_id):
            raise RuntimeError("cosmos down")

        monkeypatch.setattr(es_module, "get_model_by_id", _raise)

        result = await extraction_service.run_extraction_pipeline(
            file_content=b"",
            model_id="missing",
            filename="x.pdf",
            mime_type="application/pdf",
        )
        assert "error" in result
        assert "missing" in result["error"]
