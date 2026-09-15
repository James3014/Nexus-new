from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nexus.engine.capability_planner import CapabilityPlanner
from nexus.learning import shared_playbook
from nexus.learning.shared_playbook import (
    KNOWN_SHARED_WORKER_PLAYBOOKS,
    PROMOTION_RECORD_FILENAME,
    SharedPlaybookError,
    inspect_shared_playbook_drift,
    load_selected_shared_playbook,
    validate_shared_playbook_candidate_intake,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_diagnose(tmp_path: Path) -> Path:
    source = REPO_ROOT / ".agents" / "skills" / "diagnose"
    target = tmp_path / ".agents" / "skills" / "diagnose"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return target


def test_diagnose_active_promotion_has_valid_provenance() -> None:
    identity = load_selected_shared_playbook("diagnose", "xray", root=REPO_ROOT, required=True)
    assert identity is not None
    assert identity.status == "ACTIVE"
    assert identity.playbook_id == "diagnose"
    assert identity.version == "1.0.0"
    assert identity.primary is True
    assert identity.trace_authority == "DERIVED_ONLY"
    assert identity.promotion_record_path == ".agents/skills/diagnose/promotion_record.json"

    # Verify physical provenance artifact contents
    prov_path = REPO_ROOT / ".agents" / "skills" / "diagnose" / PROMOTION_RECORD_FILENAME
    assert prov_path.is_file()
    record = json.loads(prov_path.read_text(encoding="utf-8"))
    assert record["schema"] == "nexus.shared_playbook.promotion_record.v1"
    assert record["playbook_id"] == "diagnose"
    assert record["status"] == "ACTIVE"
    assert record["target_manifest_sha256"] == identity.manifest_sha256
    assert record["target_instructions_sha256"] == identity.instructions_sha256
    assert record["evaluation_provenance"]["gate"] == "G8"
    assert record["evaluation_provenance"]["verdict"] == "PASS"
    assert record["runtime_provenance"]["gate"] == "G9"
    assert record["runtime_provenance"]["fail_closed_verified"] is True
    assert record["acceptance_decision"]["gate"] == "G10"
    assert record["acceptance_decision"]["decision"] == "PROMOTED_TO_ACTIVE"
    assert record["acceptance_decision"]["self_promotion"] is False


def test_active_promotion_fails_closed_when_promotion_evidence_missing(tmp_path: Path) -> None:
    skill_dir = _copy_diagnose(tmp_path)
    prov_path = skill_dir / PROMOTION_RECORD_FILENAME
    assert prov_path.is_file()
    prov_path.unlink()

    with pytest.raises(SharedPlaybookError, match="shared_playbook_missing_promotion_evidence"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_active_promotion_fails_closed_on_self_promotion(tmp_path: Path) -> None:
    skill_dir = _copy_diagnose(tmp_path)
    prov_path = skill_dir / PROMOTION_RECORD_FILENAME
    record = json.loads(prov_path.read_text(encoding="utf-8"))
    record["self_promotion"] = True
    prov_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(SharedPlaybookError, match="shared_playbook_self_promotion_forbidden"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_active_promotion_fails_closed_on_manifest_hash_tamper(tmp_path: Path) -> None:
    skill_dir = _copy_diagnose(tmp_path)
    manifest_path = skill_dir / "playbook.yaml"
    content = manifest_path.read_text(encoding="utf-8") + "\n# tampered comment"
    manifest_path.write_text(content, encoding="utf-8")

    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_promotion_provenance_hash_mismatch"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_1_forged_evaluation_evidence_with_new_instructions_hash(
    tmp_path: Path,
) -> None:
    """Falsification 1: 偽造舊 evaluation evidence 指向新的 instructions hash."""
    skill_dir = _copy_diagnose(tmp_path)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\n\n## Unauthorized Mutation\n", encoding="utf-8"
    )

    prov_path = skill_dir / PROMOTION_RECORD_FILENAME
    record = json.loads(prov_path.read_text(encoding="utf-8"))
    record["evaluation_provenance"]["notes"] = "Forged evaluation pointing to new instructions"
    prov_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_promotion_provenance_hash_mismatch"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_falsification_2_modify_active_instructions_without_updating_promotion_evidence(
    tmp_path: Path,
) -> None:
    """Falsification 2: 修改 ACTIVE playbook instructions 但不更新 promotion evidence."""
    skill_dir = _copy_diagnose(tmp_path)
    skill_md = skill_dir / "SKILL.md"
    # Append instructions line
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8") + "\n- extra step without evaluation", encoding="utf-8"
    )

    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_promotion_provenance_hash_mismatch"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_unverified_shared_worker_playbooks_not_active() -> None:
    """Other candidate playbooks must NOT automatically become ACTIVE or mountable."""
    unpromoted_candidates = [
        "nexus-crash-consistency-audit",
        "nexus-bug-family-sweep",
        "nexus-proven-pattern-reuse",
        "nexus-openwiki-navigator",
        "nexus-merge-conflict-resolution",
    ]
    assert set(unpromoted_candidates).issubset(KNOWN_SHARED_WORKER_PLAYBOOKS)

    for candidate_id in unpromoted_candidates:
        with pytest.raises(SharedPlaybookError, match="shared_playbook_missing"):
            load_selected_shared_playbook(candidate_id, "xray", root=REPO_ROOT, required=True)


def test_drift_inspection_detects_upstream_instructions_drift_without_auto_mutation() -> None:
    """Upstream/reference hash drift produces re-evaluation candidate only, never mutating ACTIVE."""
    status = inspect_shared_playbook_drift(
        "diagnose",
        upstream_content="Modified upstream GPT skill instructions with new steps",
        upstream_reference_id="gpt-diagnose-v2",
        root=REPO_ROOT,
    )
    assert status.drift_detected is True
    assert status.drift_reason == "upstream_source_drift_detected"
    assert status.sync_disposition == "RE_EVALUATION_REQUIRED_CANDIDATE_ONLY"
    assert status.mutation_blocked is True
    assert status.status == "ACTIVE"


def test_intake_rejects_self_promotion_to_active() -> None:
    """Intake cannot produce an ACTIVE playbook directly."""
    payload = {
        "schema": "nexus.shared_playbook.v1",
        "playbook_id": "nexus-crash-consistency-audit",
        "skill_id": "nexus-crash-consistency-audit",
        "version": "1.0.0",
        "status": "ACTIVE",
        "primary": True,
        "capability_mounts": ["xray"],
        "trace_authority": "DERIVED_ONLY",
        "permissions": {
            "filesystem": "INHERIT_ONLY",
            "network": "INHERIT_ONLY",
            "tools": "INHERIT_ONLY",
        },
        "authority": {
            "route_selection": False,
            "model_selection": False,
            "worker_selection": False,
            "approval": False,
            "integration": False,
            "merge": False,
            "promotion": False,
            "task_receipt": False,
            "claim_authority": False,
            "self_modify": False,
            "permission_expand": False,
        },
        "auto_chain": False,
        "local_transition_contract": {
            "same_task": True,
            "same_scope": True,
            "same_capability": True,
            "same_permissions": True,
            "same_authority": True,
        },
        "stages": [{"id": "audit", "exit_evidence": ["audit_log"]}],
        "transitions": [{"from": "audit", "to": "audit", "kind": "LOCAL_TRANSITION"}],
        "stop_conditions": ["complete"],
        "learning_writeback": {"mode": "CANDIDATE_ONLY", "self_modify": False},
    }
    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_intake_cannot_self_promote_active"
    ):
        validate_shared_playbook_candidate_intake(
            payload,
            skill_id="nexus-crash-consistency-audit",
            capability_mount="xray",
        )


def test_planner_mounts_active_diagnose_by_default_path(tmp_path: Path, monkeypatch) -> None:
    """Executable proof that ACTIVE diagnose mounts through the default CapabilityPlanner path."""
    _copy_diagnose(tmp_path)
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    # Create dummy status report
    report = tmp_path / "skill_status.json"
    report.write_text(
        json.dumps({
            "schema": "nexus.skill_status.v1",
            "skills": [
                {
                    "name": "diagnose",
                    "path": ".agents/skills/diagnose/SKILL.md",
                    "root": "current_best",
                    "skill_status": "nexus_curated_candidate",
                    "test_level": "focused",
                    "action": "runtime_policy_overlay_only",
                    "capability_mount": "xray",
                }
            ],
        }),
        encoding="utf-8",
    )

    planner = CapabilityPlanner()
    plan = planner.plan(
        task_desc="Diagnose flaky test regression\n- Expected capability receipts: xray",
        task_type="bugfix",
        route={
            "selected_route": "Mode B",
            "workforce_admission_enabled": True,
            "route_decision": {"selected_capabilities": ["xray"]},
        },
        budget={"skill_status_report": str(report)},
        skills=[{"skill_id": "diagnose", "capability_id": "xray"}],
    )

    snapshot = plan.signal_snapshot
    contracts = snapshot.get("planned_skill_mount_contracts", [])
    violations = snapshot.get("skill_mount_violations", [])

    assert violations == []
    assert len(contracts) == 1
    mount = contracts[0]
    assert mount["skill_id"] == "diagnose"
    assert mount["capability_mount"] == "xray"
    assert mount["planner_selected_capability"] is True
    assert "shared_playbook" in mount
    sp = mount["shared_playbook"]
    assert sp["status"] == "ACTIVE"
    assert sp["primary"] is True
    assert sp["promotion_record_path"] == ".agents/skills/diagnose/promotion_record.json"
