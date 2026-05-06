from __future__ import annotations

from pathlib import Path

from scripts.ops.render_brain_hub_coverage import build_coverage, render_markdown, validate_coverage_gate


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
