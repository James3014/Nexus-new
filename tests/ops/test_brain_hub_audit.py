from __future__ import annotations

from pathlib import Path

from scripts.ops.brain_hub_audit import scan_brain_hub


def test_brain_hub_audit_indexes_phase_guidance_and_refs(tmp_path: Path):
    root = tmp_path
    wiki = root / "wiki"
    wiki.mkdir()
    doc = wiki / "guide.md"
    doc.write_text(
        "# Guide\n\nPhase X research must consult `nexus/research/research_pack.py`.\n",
        encoding="utf-8",
    )

    audit = scan_brain_hub(root, [Path("wiki")])

    assert audit.passed is True
    assert audit.guidance["X"] == ["wiki/guide.md"]
    assert audit.documents[0].code_refs == ["nexus/research/research_pack.py"]


def test_brain_hub_reality_gate_fails_production_doc_without_runtime_ref(tmp_path: Path):
    root = tmp_path
    wiki = root / "wiki"
    wiki.mkdir()
    doc = wiki / "claim.md"
    doc.write_text("# Claim\n\n[PHYSICAL_STATUS: PRODUCTION]\n\nNo runtime reference.\n", encoding="utf-8")

    audit = scan_brain_hub(root, [Path("wiki")])

    assert audit.passed is False
    assert audit.failures == [
        {
            "path": "wiki/claim.md",
            "reason": "production_status_without_runtime_reference",
            "physical_status": "PRODUCTION",
        }
    ]
