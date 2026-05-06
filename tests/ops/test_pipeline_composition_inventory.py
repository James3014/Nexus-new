from __future__ import annotations

from pathlib import Path

from scripts.ops.pipeline_composition_inventory import build_inventory


def test_pipeline_composition_inventory_reports_partial_legacy_mixins():
    payload = build_inventory(Path(".").resolve())

    assert payload["passed"] is True
    assert payload["composition_status"] == "partial"
    assert payload["phase_ownership_status"] == "executor_owned_with_legacy_mixins_retained"
    assert set(payload["phase_executor_builders"]) >= {"P", "X", "D", "R", "A", "C"}
    assert set(payload["registered_executor_phases"]) >= {"P", "X", "D", "R", "A", "C"}
    assert set(payload["phase_factory_create_all_phases"]) >= {"P", "X", "D", "R", "A", "C"}
    assert payload["runtime_missing_phases"] == []
    assert payload["fallback_debt_phases"] == ["A", "C"]
    assert payload["fallback_debt_count"] == 2
    assert {item["phase"] for item in payload["runtime_fallback_paths"]} == {"A", "C"}
    assert payload["unexpected_mixins"] == []
    assert "PipelineRepairMixin" in payload["legacy_mixins"]
