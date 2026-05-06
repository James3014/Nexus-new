from __future__ import annotations

from pathlib import Path

from scripts.ops.pipeline_composition_inventory import build_inventory


def test_pipeline_composition_inventory_reports_partial_legacy_mixins():
    payload = build_inventory(Path(".").resolve())

    assert payload["passed"] is True
    assert payload["composition_status"] == "partial"
    assert set(payload["phase_executor_builders"]) >= {"P", "X", "D", "R", "A", "C"}
    assert payload["unexpected_mixins"] == []
    assert "PipelineRepairMixin" in payload["legacy_mixins"]
