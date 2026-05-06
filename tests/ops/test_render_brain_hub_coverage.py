from __future__ import annotations

from pathlib import Path

from scripts.ops.render_brain_hub_coverage import build_coverage, render_markdown


def test_render_brain_hub_coverage_classifies_manifest_docs():
    payload = build_coverage(Path(".").resolve(), manifest=Path("docs/ops/brain_hub_manifest.json"))
    markdown = render_markdown(payload)

    assert payload["audit_passed"] is True
    assert payload["document_count"] == 18
    assert payload["status_counts"]["implemented"] >= 1
    assert "# Brain Hub Code-Reality Coverage" in markdown
    assert "arch_diagnosis_brain_hub.md" in markdown
