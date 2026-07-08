from __future__ import annotations

import pytest
from nexus.services.local_heal.receipt import build_repair_receipt, _extract_output_understanding_metadata


class FakeCtx:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_canonical_metadata_propagated_when_present():
    """P1-3: Receipt includes propagated output_understanding_* fields when executor metadata contains them."""
    ctx = FakeCtx(
        instance_id="t1",
        raw_model_metadata={
            "output_understanding_format": "UNIFIED_DIFF",
            "output_understanding_success": True,
            "output_understanding_normalization_steps": [],
            "output_understanding_source_format": "UNIFIED_DIFF",
        },
    )
    receipt = build_repair_receipt(ctx)
    telemetry = receipt.get("telemetries", {})
    assert telemetry.get("output_understanding_format") == "UNIFIED_DIFF"
    assert telemetry.get("output_understanding_success") is True
    assert telemetry.get("output_understanding_normalization_steps") == []
    assert telemetry.get("output_understanding_source_format") == "UNIFIED_DIFF"


def test_absence_of_canonical_metadata_leaves_receipt_valid():
    """P1-3: Receipt remains valid when canonical metadata fields are absent."""
    ctx = FakeCtx(
        instance_id="t2",
        raw_model_metadata={},
    )
    receipt = build_repair_receipt(ctx)
    telemetry = receipt.get("telemetries", {})
    # Fields should not be present
    assert "output_understanding_format" not in telemetry
    assert "output_understanding_success" not in telemetry
    # Receipt should still have required fields
    assert "schema" in receipt
    assert "task_id" in receipt


def test_extraction_function_additive_only():
    """P1-3: _extract_output_understanding_metadata returns empty dict when fields absent."""
    ctx = FakeCtx(raw_model_metadata={})
    result = _extract_output_understanding_metadata(ctx)
    assert result == {}

    ctx2 = FakeCtx(raw_model_metadata={
        "output_understanding_format": "SEARCH_REPLACE",
        "output_understanding_success": True,
    })
    result2 = _extract_output_understanding_metadata(ctx2)
    assert result2["output_understanding_format"] == "SEARCH_REPLACE"
    assert result2["output_understanding_success"] is True
    assert "output_understanding_normalization_steps" not in result2
    assert "output_understanding_source_format" not in result2


def test_extraction_handles_missing_raw_model_metadata():
    """P1-3: Extraction handles ctx without raw_model_metadata attribute."""
    ctx = FakeCtx()
    result = _extract_output_understanding_metadata(ctx)
    assert result == {}
