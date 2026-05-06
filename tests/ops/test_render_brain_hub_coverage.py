from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.render_brain_hub_coverage import build_coverage, main, render_markdown, validate_coverage_gate


def test_render_brain_hub_coverage_classifies_manifest_docs():
    payload = build_coverage(Path(".").resolve(), manifest=Path("docs/ops/brain_hub_manifest.json"))
    markdown = render_markdown(payload)

    assert payload["audit_passed"] is True
    assert payload["document_count"] == 18
    assert payload["status_counts"]["implemented"] >= 1
    assert validate_coverage_gate(payload)["passed"] is True
    assert "# Brain Hub Code-Reality Coverage" in markdown
    assert "arch_diagnosis_brain_hub.md" in markdown


def test_brain_hub_coverage_gate_fails_on_contradicted_docs():
    gate = validate_coverage_gate({"audit_passed": True, "status_counts": {"implemented": 1, "contradicted": 1}})

    assert gate["passed"] is False
    assert "contradicted_coverage_present" in gate["failures"]


def test_render_brain_hub_coverage_writes_full_json_artifact(tmp_path):
    md_output = tmp_path / "brain_hub_coverage.md"
    json_output = tmp_path / "brain_hub_coverage.json"

    assert main(["--output", str(md_output), "--json-output", str(json_output)]) == 0

    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["coverage"]["schema_version"] == "nexus_brain_hub_coverage.v1"
    assert payload["gate"]["schema_version"] == "nexus_brain_hub_coverage_gate.v1"
    assert payload["gate"]["passed"] is True
    assert len(payload["coverage"]["documents"]) == payload["coverage"]["document_count"]
    assert md_output.exists()
