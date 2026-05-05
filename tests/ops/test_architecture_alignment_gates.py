from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_hallucination_guard_uses_schema_weight_for_historical_pattern():
    schema = json.loads((ROOT / "nexus/schemas/hallucination_index_v1.json").read_text(encoding="utf-8"))
    source = (ROOT / "nexus/governance/hallucination_guard.py").read_text(encoding="utf-8")

    assert schema["metrics"]["historical_hallucination_pattern"]["weight"] == 2
    assert "self.score += 2.0" not in source
    assert "_apply_trigger(\"historical_hallucination_pattern\"" in source


def test_storage_layer_does_not_import_service_layer_and_exposes_scoped_access():
    source = (ROOT / "nexus/infrastructure/storage_implementations.py").read_text(encoding="utf-8")
    interfaces = (ROOT / "nexus/infrastructure/storage_interfaces.py").read_text(encoding="utf-8")

    assert "nexus.services" not in source
    assert "def scoped_access" in source
    assert "class SearchProvider" in interfaces


def test_belief_gate_and_learning_steward_are_runtime_contracts():
    belief_contracts = (ROOT / "nexus/core/belief_contracts.py").read_text(encoding="utf-8")
    orchestrator = (ROOT / "nexus/core/orchestrator.py").read_text(encoding="utf-8")
    steward = (ROOT / "nexus/core/learning_steward.py").read_text(encoding="utf-8")

    assert "class BeliefGate(Protocol)" in belief_contracts
    assert "BeliefGate" in orchestrator
    assert "MagicMock" not in orchestrator
    assert "class LearningSteward" in steward
    assert "GovernanceProfile" in steward


def test_pipeline_composition_runtime_exists_while_mixin_migration_remains_explicit():
    pipeline = (ROOT / "nexus/engine/pipeline.py").read_text(encoding="utf-8")
    phase_plugin = (ROOT / "nexus/engine/phase_plugin.py").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "docs/ops/brain_hub_manifest.json").read_text(encoding="utf-8"))

    assert "PhaseRegistry" in pipeline
    assert "class PhaseRegistry" in phase_plugin
    pipeline_rows = [row for row in manifest["documents"] if "pipeline" in row["path"]]
    assert pipeline_rows
    assert any(row["status"] == "partial" for row in pipeline_rows)
