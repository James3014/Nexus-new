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


def test_brain_hub_manifest_requires_status_and_existing_refs(tmp_path: Path):
    root = tmp_path
    wiki = root / "wiki"
    wiki.mkdir()
    (wiki / "guide.md").write_text("# Guide\n\nPhase S cold-start.\n", encoding="utf-8")
    (root / "scripts" / "ops").mkdir(parents=True)
    (root / "tests" / "ops").mkdir(parents=True)
    (root / "scripts" / "ops" / "brain_hub_audit.py").write_text("# runtime\n", encoding="utf-8")
    (root / "tests" / "ops" / "test_brain_hub_audit.py").write_text("# tests\n", encoding="utf-8")
    manifest = root / "docs" / "ops" / "brain_hub_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """{
          "schema_version": "nexus_brain_hub_manifest.v1",
          "documents": [
            {
              "path": "wiki/guide.md",
              "status": "audit",
              "runtime_refs": ["scripts/ops/brain_hub_audit.py"],
              "test_refs": ["tests/ops/test_brain_hub_audit.py"]
            }
          ]
        }""",
        encoding="utf-8",
    )

    audit = scan_brain_hub(root, [], manifest_path=manifest)

    assert audit.passed is True
    assert audit.documents[0].manifest_status == "audit"
    assert audit.documents[0].runtime_refs == ["scripts/ops/brain_hub_audit.py"]
    assert audit.guidance["S"] == ["wiki/guide.md"]


def test_brain_hub_manifest_fails_missing_document_and_refs(tmp_path: Path):
    root = tmp_path
    manifest = root / "manifest.json"
    manifest.write_text(
        """{
          "schema_version": "nexus_brain_hub_manifest.v1",
          "documents": [
            {"path": "wiki/missing.md", "status": "", "runtime_refs": ["missing.py"], "test_refs": []}
          ]
        }""",
        encoding="utf-8",
    )

    audit = scan_brain_hub(root, [], manifest_path=manifest)

    assert audit.passed is False
    assert audit.failures == [{"path": "wiki/missing.md", "reason": "manifest_document_missing"}]
