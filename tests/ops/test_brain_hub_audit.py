from __future__ import annotations

from pathlib import Path

from scripts.ops.brain_hub_audit import scan_brain_hub, validate_s_stage_runtime_contract


def _write_valid_s_stage_pipeline(root: Path) -> None:
    (root / "nexus" / "engine").mkdir(parents=True, exist_ok=True)
    (root / "nexus" / "engine" / "pipeline.py").write_text(
        'CANONICAL_STAGE_FLOW = ["S", "P", "X", "D", "R", "A", "C"]\n'
        'STAGE_DESCRIPTIONS = {"S": "cold_start_seed"}\n'
        "stage_flow = CANONICAL_STAGE_FLOW\n"
        "stage_descriptions = STAGE_DESCRIPTIONS\n"
        "class PipelineContext:\n"
        "    def __init__(self):\n"
        "        self.decision_journal = []\n"
        "    def append_journal(self, *, origin_phase, event_type, payload=None):\n"
        "        self.decision_journal.append({'origin_phase': origin_phase, 'event_type': event_type})\n"
        "class NexusPipeline:\n"
        "    def _init_stage_status(self, state):\n"
        "        state.metadata.setdefault('stage_status', {stage: \"pending\" for stage in CANONICAL_STAGE_FLOW})\n",
        encoding="utf-8",
    )


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
    _write_valid_s_stage_pipeline(root)
    (root / "tests" / "engine").mkdir(parents=True)
    (root / "scripts" / "ops" / "brain_hub_audit.py").write_text("# runtime\n", encoding="utf-8")
    (root / "tests" / "ops" / "test_brain_hub_audit.py").write_text("# tests\n", encoding="utf-8")
    (root / "tests" / "engine" / "test_pipeline_stage_flow.py").write_text(
        "def test_stage_flow(): pass\n",
        encoding="utf-8",
    )
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


def test_brain_hub_audit_requires_s_stage_runtime_checklist(tmp_path: Path):
    root = tmp_path
    (root / "wiki").mkdir()
    (root / "wiki" / "guide.md").write_text("# Guide\n\nPhase S cold-start.\n", encoding="utf-8")
    _write_valid_s_stage_pipeline(root)
    (root / "tests" / "engine").mkdir(parents=True)
    (root / "tests" / "engine" / "test_pipeline_stage_flow.py").write_text(
        "def test_stage_flow(): pass\n",
        encoding="utf-8",
    )

    audit = scan_brain_hub(root, [Path("wiki")])

    assert audit.passed is True
    assert all(audit.runtime_checklist["s_stage_required_checks"].values())
    assert all(audit.runtime_checklist["s_stage_runtime_contract"].values())


def test_s_stage_runtime_contract_fails_when_s_missing(tmp_path: Path):
    root = tmp_path
    (root / "nexus" / "engine").mkdir(parents=True)
    (root / "nexus" / "engine" / "pipeline.py").write_text(
        'CANONICAL_STAGE_FLOW = ["P", "X", "D", "R", "A", "C"]\n'
        'STAGE_DESCRIPTIONS = {"P": "plan"}\n'
        "stage_status = {}\n"
        "decision_journal = []\n"
        "origin_phase = 'P'\n"
        "event_type = 'seed'\n",
        encoding="utf-8",
    )

    contract = validate_s_stage_runtime_contract(root)

    assert contract["checks"]["canonical_stage_flow"] is False
    assert any(item["check"] == "canonical_stage_flow" for item in contract["failures"])


def test_s_stage_runtime_contract_fails_when_cold_start_description_missing(tmp_path: Path):
    root = tmp_path
    (root / "nexus" / "engine").mkdir(parents=True)
    (root / "nexus" / "engine" / "pipeline.py").write_text(
        'CANONICAL_STAGE_FLOW = ["S", "P", "X", "D", "R", "A", "C"]\n'
        'STAGE_DESCRIPTIONS = {"S": "seed"}\n'
        "stage_status = {}\n"
        "decision_journal = []\n"
        "origin_phase = 'S'\n"
        "event_type = 'cold_start'\n",
        encoding="utf-8",
    )

    contract = validate_s_stage_runtime_contract(root)

    assert contract["checks"]["s_stage_description"] is False
    assert any(item["check"] == "s_stage_description" for item in contract["failures"])


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
