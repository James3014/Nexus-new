from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

from nexus.engine.planner.skill_mount_evidence import build_skill_mount_evidence
from nexus.learning import shared_playbook
from nexus.learning.shared_playbook import (
    PROMOTION_RECORD_FILENAME,
    compute_playbook_acceptance_binding_hash,
    load_selected_shared_playbook,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_skill(tmp_path: Path, source_id: str = "diagnose", target_id: str = "diagnose") -> Path:
    source = REPO_ROOT / ".agents" / "skills" / source_id
    target = tmp_path / ".agents" / "skills" / target_id
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    if target_id != source_id:
        manifest_path = target / "playbook.yaml"
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        payload["playbook_id"] = target_id
        payload["skill_id"] = target_id
        payload["status"] = "CANDIDATE"
        manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        prov_path = target / PROMOTION_RECORD_FILENAME
        if prov_path.exists():
            prov_path.unlink()
    else:
        manifest_path = target / "playbook.yaml"
        instructions_path = target / "SKILL.md"
        manifest_path.write_text(
            manifest_path.read_text(encoding="utf-8").replace(
                "status: CANDIDATE", "status: ACTIVE"
            ),
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
            record["acceptance_decision"]["acceptance_schema"] = (
                "nexus.candidate_acceptance_result.v1"
            )
            record["acceptance_decision"]["subject_manifest_sha256"] = m_sha
            record["acceptance_decision"]["subject_instructions_sha256"] = i_sha
            prov_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return target


def _status_report(tmp_path: Path, names: list[str]) -> Path:
    report = tmp_path / "skill_status.json"
    report.write_text(
        json.dumps({
            "schema": "nexus.skill_status.v1",
            "skills": [
                {
                    "name": name,
                    "path": f".agents/skills/{name}/SKILL.md",
                    "root": "current_best",
                    "skill_status": "nexus_curated_candidate",
                    "test_level": "focused",
                    "action": "runtime_policy_overlay_only",
                    "capability_mount": "xray",
                }
                for name in names
            ],
        }),
        encoding="utf-8",
    )
    return report


def test_planner_mount_binds_one_exact_primary_shared_playbook(tmp_path: Path, monkeypatch) -> None:
    _copy_skill(tmp_path)
    report = _status_report(tmp_path, ["diagnose"])
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    result = build_skill_mount_evidence(
        skills=[{"skill_id": "diagnose", "capability_id": "xray"}],
        budget={"skill_status_report": str(report)},
        selected_capabilities=["xray"],
    )

    assert result["skill_mount_violations"] == []
    assert len(result["skill_mount_contracts"]) == 1
    contract = result["skill_mount_contracts"][0]
    identity = load_selected_shared_playbook("diagnose", "xray", root=tmp_path, required=True)
    assert identity is not None
    assert contract["planner_selected_capability"] is True
    assert contract["shared_playbook"] == identity.to_dict()
    assert "shared_playbook_exact_identity_bound" in contract["load_reason_codes"]


def test_planner_mount_fails_closed_when_required_playbook_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    report = _status_report(tmp_path, ["diagnose"])
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    result = build_skill_mount_evidence(
        skills=[{"skill_id": "diagnose", "capability_id": "xray"}],
        budget={"skill_status_report": str(report)},
        selected_capabilities=["xray"],
    )

    assert result["skill_mount_contracts"] == []
    assert [item["reason"] for item in result["skill_mount_violations"]] == [
        "shared_playbook_missing"
    ]
    assert result["skill_mount_violations"][0]["capability_mount"] == "xray"


def test_planner_mount_rejects_unselected_playbook_injection(tmp_path: Path, monkeypatch) -> None:
    _copy_skill(tmp_path)
    report = _status_report(tmp_path, ["diagnose"])
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    selected_capabilities = ["benchmark"]
    result = build_skill_mount_evidence(
        skills=[{"skill_id": "diagnose", "capability_id": "xray"}],
        budget={"skill_status_report": str(report)},
        selected_capabilities=selected_capabilities,
    )

    assert selected_capabilities == ["benchmark"]
    assert result["skill_mount_contracts"] == []
    assert [item["reason"] for item in result["skill_mount_violations"]] == [
        "shared_playbook_not_planner_selected"
    ]


def test_planner_mount_rejects_second_primary_playbook(tmp_path: Path, monkeypatch) -> None:
    _copy_skill(tmp_path)
    _copy_skill(tmp_path, target_id="diagnose-alt")
    report = _status_report(tmp_path, ["diagnose", "diagnose-alt"])
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    result = build_skill_mount_evidence(
        skills=[
            {"skill_id": "diagnose", "capability_id": "xray"},
            {"skill_id": "diagnose-alt", "capability_id": "xray"},
        ],
        budget={"skill_status_report": str(report)},
        selected_capabilities=["xray"],
    )

    assert [item["skill_id"] for item in result["skill_mount_contracts"]] == ["diagnose"]
    assert [item["reason"] for item in result["skill_mount_violations"]] == [
        "shared_playbook_second_primary"
    ]


def test_planner_mount_preserves_optional_skill_without_shared_playbook(
    tmp_path: Path, monkeypatch
) -> None:
    report = _status_report(tmp_path, ["plain-skill"])
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    result = build_skill_mount_evidence(
        skills=[{"skill_id": "plain-skill", "capability_id": "xray"}],
        budget={"skill_status_report": str(report)},
        selected_capabilities=["xray"],
    )

    assert result["skill_mount_violations"] == []
    assert len(result["skill_mount_contracts"]) == 1
    contract = result["skill_mount_contracts"][0]
    assert contract["skill_id"] == "plain-skill"
    assert contract["planner_selected_capability"] is True
    assert "shared_playbook" not in contract
