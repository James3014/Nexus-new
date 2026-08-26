from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from nexus.learning.shared_playbook import (
    PROMOTION_RECORD_FILENAME,
    SharedPlaybookError,
    compute_playbook_acceptance_binding_hash,
    load_selected_shared_playbook,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_diagnose_skill(tmp_path: Path) -> Path:
    source = REPO_ROOT / ".agents" / "skills" / "diagnose"
    target = tmp_path / ".agents" / "skills" / "diagnose"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    manifest_path = target / "playbook.yaml"
    instructions_path = target / "SKILL.md"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace("status: CANDIDATE", "status: ACTIVE"),
        encoding="utf-8",
    )
    m_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    i_sha = hashlib.sha256(instructions_path.read_bytes()).hexdigest()
    receipt_path = target / "acceptance_receipt.json"
    binding_hash = compute_playbook_acceptance_binding_hash(
        task_id="g10-diagnose-promotion-acceptance",
        attempt_id="attempt-1",
        reviewer_id="reviewer-independent-1",
        subject_playbook_id="diagnose",
        subject_manifest_sha256=m_sha,
        subject_instructions_sha256=i_sha,
        candidate_commit_sha="c8c6de8c330ec8868dc515de4c337007093ad988",
        verdict="ACCEPT_CANDIDATE",
    )
    payload = {
        "schema": "nexus.candidate_acceptance_result.v1",
        "decision": "ACCEPT",
        "verdict": "ACCEPT_CANDIDATE",
        "task_id": "g10-diagnose-promotion-acceptance",
        "attempt_id": "attempt-1",
        "candidate_commit_sha": "c8c6de8c330ec8868dc515de4c337007093ad988",
        "reviewer_id": "reviewer-independent-1",
        "binding_hash": binding_hash,
        "subject_playbook_id": "diagnose",
        "subject_manifest_sha256": m_sha,
        "subject_instructions_sha256": i_sha,
        "independence_classification": "INDEPENDENT_REVIEWER",
        "self_promotion": False,
        "reasons": ["independent G10 candidate acceptance verified"],
        "evidence_cutoff": "2026-08-27T00:00:00Z",
    }
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    receipt_path.write_bytes(raw_bytes)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    prov_path = target / PROMOTION_RECORD_FILENAME
    if prov_path.is_file():
        record = json.loads(prov_path.read_text(encoding="utf-8"))
        record["status"] = "ACTIVE"
        record["target_manifest_sha256"] = m_sha
        record["target_instructions_sha256"] = i_sha
        record["evaluation_provenance"]["evaluated_manifest_sha256"] = m_sha
        record["evaluation_provenance"]["evaluated_instructions_sha256"] = i_sha
        record["runtime_provenance"]["integrated_manifest_sha256"] = m_sha
        record["runtime_provenance"]["integrated_instructions_sha256"] = i_sha
        record.setdefault("acceptance_decision", {})["decision"] = "PROMOTED_TO_ACTIVE"
        record["acceptance_decision"]["acceptance_artifact_hash"] = digest
        record["acceptance_decision"]["acceptance_receipt_path"] = (
            ".agents/skills/diagnose/acceptance_receipt.json"
        )
        record["acceptance_decision"]["acceptance_schema"] = "nexus.candidate_acceptance_result.v1"
        record["acceptance_decision"]["subject_manifest_sha256"] = m_sha
        record["acceptance_decision"]["subject_instructions_sha256"] = i_sha
        prov_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return target


def _mutate_manifest(skill_dir: Path, mutate) -> None:
    path = skill_dir / "playbook.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_diagnose_shared_playbook_binds_exact_manifest_and_instructions_hashes(
    tmp_path: Path,
) -> None:
    _copy_diagnose_skill(tmp_path)
    identity = load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)
    assert identity is not None
    assert identity.playbook_id == "diagnose"
    assert identity.version == "1.0.0"
    assert identity.status == "ACTIVE"
    assert identity.primary is True
    assert identity.trace_authority == "DERIVED_ONLY"
    assert identity.promotion_record_path == ".agents/skills/diagnose/promotion_record.json"
    assert (
        identity.manifest_sha256
        == hashlib.sha256((tmp_path / identity.manifest_path).read_bytes()).hexdigest()
    )
    assert (
        identity.instructions_sha256
        == hashlib.sha256((tmp_path / identity.instructions_path).read_bytes()).hexdigest()
    )


def test_shared_playbook_rejects_permission_expansion(tmp_path: Path) -> None:
    skill_dir = _copy_diagnose_skill(tmp_path)
    _mutate_manifest(
        skill_dir, lambda payload: payload["permissions"].__setitem__("network", "ALLOW")
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_permission_expansion"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_shared_playbook_rejects_authority_escalation(tmp_path: Path) -> None:
    skill_dir = _copy_diagnose_skill(tmp_path)
    _mutate_manifest(
        skill_dir, lambda payload: payload["authority"].__setitem__("route_selection", True)
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_authority_escalation"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_shared_playbook_rejects_auto_chain(tmp_path: Path) -> None:
    skill_dir = _copy_diagnose_skill(tmp_path)
    _mutate_manifest(skill_dir, lambda payload: payload.__setitem__("auto_chain", True))

    with pytest.raises(SharedPlaybookError, match="shared_playbook_auto_chain_forbidden"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_shared_playbook_rejects_capability_mismatch() -> None:
    with pytest.raises(SharedPlaybookError, match="shared_playbook_capability_mismatch"):
        load_selected_shared_playbook("diagnose", "benchmark", root=REPO_ROOT, required=True)


def test_shared_playbook_rejects_local_transition_across_stage_boundary(tmp_path: Path) -> None:
    skill_dir = _copy_diagnose_skill(tmp_path)

    def mutate(payload) -> None:
        payload["transitions"][-1]["kind"] = "LOCAL_TRANSITION"

    _mutate_manifest(skill_dir, mutate)
    with pytest.raises(
        SharedPlaybookError, match="shared_playbook_cross_boundary_requires_handoff"
    ):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)


def test_shared_playbook_rejects_unknown_permission_expansion(tmp_path: Path) -> None:
    skill_dir = _copy_diagnose_skill(tmp_path)
    _mutate_manifest(
        skill_dir, lambda payload: payload["permissions"].__setitem__("shell", "ALLOW")
    )

    with pytest.raises(SharedPlaybookError, match="shared_playbook_permission_expansion"):
        load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)
