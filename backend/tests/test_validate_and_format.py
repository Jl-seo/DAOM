"""
Output-shape contract tests for `ExtractionService._validate_and_format`.

Every Phase-4 refactor branch must preserve the existing output schema.
These tests pin down the canonical output structure for 3 representative
input shapes so any accidental contract drift shows up as a failing test.
"""
from __future__ import annotations

import pytest

from app.services.extraction_service import ExtractionService


# ---------------------------------------------------------------------------
# Contract 1: simple string field
# ---------------------------------------------------------------------------

class TestValidateAndFormatBasicShape:
    def test_string_field_produces_canonical_wrapper(self, make_model):
        service = ExtractionService()
        model = make_model(fields=[
            {"key": "invoice_number", "label": "Invoice #", "type": "string"},
        ])

        raw = {
            "guide_extracted": {
                "invoice_number": {
                    "value": "INV-001",
                    "confidence": 0.97,
                    "bbox": [10, 10, 100, 30],
                    "page_number": 1,
                }
            },
            "other_data": [],
            "pages": [{"page_number": 1, "width": 612, "height": 792}],
        }

        out = service._validate_and_format(raw, model, raw["pages"])
        field = out["guide_extracted"]["invoice_number"]

        # Canonical wrapper shape
        assert set(field.keys()) == {
            "value", "original_value", "confidence",
            "bbox", "page_number", "validation_status",
        }
        assert field["value"] == "INV-001"
        assert field["original_value"] == "INV-001"
        assert field["confidence"] == 0.97
        assert field["page_number"] == 1
        assert field["validation_status"] in ("valid", "error_type_mismatch", "warning_low_confidence")

    def test_missing_field_gets_empty_wrapper(self, make_model):
        """When LLM didn't return a modeled field, output still has the key."""
        service = ExtractionService()
        model = make_model(fields=[
            {"key": "missing_field", "label": "Missing", "type": "string"},
        ])

        out = service._validate_and_format({"guide_extracted": {}}, model, [])
        assert "missing_field" in out["guide_extracted"]
        wrapper = out["guide_extracted"]["missing_field"]
        assert set(wrapper.keys()) == {
            "value", "original_value", "confidence",
            "bbox", "page_number", "validation_status",
        }


# ---------------------------------------------------------------------------
# Contract 2: typed coercion (number)
# ---------------------------------------------------------------------------

class TestValidateAndFormatTypeCoercion:
    def test_number_type_coerces_string_to_number(self, make_model):
        service = ExtractionService()
        model = make_model(fields=[
            {"key": "total", "label": "Total", "type": "number"},
        ])

        raw = {
            "guide_extracted": {
                "total": {"value": "1234.56", "confidence": 0.9},
            }
        }
        out = service._validate_and_format(raw, model, [])
        field = out["guide_extracted"]["total"]

        # `value` is coerced; `original_value` retains the raw LLM output.
        assert field["value"] == 1234.56
        assert field["original_value"] == "1234.56"

    def test_number_type_invalid_flags_error(self, make_model):
        service = ExtractionService()
        model = make_model(fields=[
            {"key": "total", "label": "Total", "type": "number"},
        ])

        raw = {
            "guide_extracted": {
                "total": {"value": "not a number", "confidence": 0.9},
            }
        }
        out = service._validate_and_format(raw, model, [])
        assert out["guide_extracted"]["total"]["validation_status"] == "error_type_mismatch"


# ---------------------------------------------------------------------------
# Contract 3: metadata pass-through
# ---------------------------------------------------------------------------

class TestValidateAndFormatMetadata:
    def test_raw_content_and_tables_pass_through(self, make_model):
        service = ExtractionService()
        model = make_model(fields=[
            {"key": "k", "label": "K", "type": "string"},
        ])

        raw = {
            "guide_extracted": {"k": {"value": "v", "confidence": 0.9}},
            "other_data": [{"column": "c", "value": "x"}],
            "pages": [{"page_number": 1, "width": 100, "height": 100}],
            "raw_content": "some markdown",
            "raw_tables": [{"cells": []}],
        }
        out = service._validate_and_format(raw, model, raw["pages"])

        assert out["other_data"] == [{"column": "c", "value": "x"}]
        assert out["pages"] == raw["pages"]
        assert out["raw_content"] == "some markdown"
        assert out["raw_tables"] == [{"cells": []}]

    def test_beta_metadata_pass_through(self, make_model):
        service = ExtractionService()
        model = make_model(fields=[
            {"key": "k", "label": "K", "type": "string"},
        ])

        raw = {
            "guide_extracted": {},
            "_beta_parsed_content": "parsed!",
            "_beta_ref_map": {"k": ["p1"]},
            "_beta_chunking_info": {"chunks": 3},
            "_beta_pipeline_stages": ["designer", "engineer"],
        }
        out = service._validate_and_format(raw, model, [])

        assert out["_beta_parsed_content"] == "parsed!"
        assert out["_beta_ref_map"] == {"k": ["p1"]}
        assert out["_beta_chunking_info"] == {"chunks": 3}
        assert out["_beta_pipeline_stages"] == ["designer", "engineer"]

    def test_guide_extracted_is_rebuilt_not_passed_through(self, make_model):
        """The output's guide_extracted is the validated set, not the raw input —
        stray keys not in the model get dropped."""
        service = ExtractionService()
        model = make_model(fields=[
            {"key": "a", "label": "A", "type": "string"},
        ])

        raw = {
            "guide_extracted": {
                "a": {"value": "va"},
                "stray": {"value": "vs"},  # not in model.fields
            }
        }
        out = service._validate_and_format(raw, model, [])
        assert "a" in out["guide_extracted"]
        assert "stray" not in out["guide_extracted"]
