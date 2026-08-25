from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from nexus.engine.planner.skill_mount_evidence import build_skill_mount_evidence
from nexus.learning import shared_playbook
from nexus.learning.shared_playbook import load_selected_shared_playbook


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
        manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return target


def _status_report(tmp_path: Path, names: list[str]) -> Path:
    report = tmp_path / "skill_status.json"
    report.write_text(
        json.dumps(
            {
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
            }
        ),
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


def test_planner_mount_fails_closed_when_required_playbook_is_missing(tmp_path: Path, monkeypatch) -> None:
    report = _status_report(tmp_path, ["diagnose"])
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)

    result = build_skill_mount_evidence(
        skills=[{"skill_id": "diagnose", "capability_id": "xray"}],
        budget={"skill_status_report": str(report)},
        selected_capabilities=["xray"],
    )

    assert result["skill_mount_contracts"] == []
    assert [item["reason"] for item in result["skill_mount_violations"]] == ["shared_playbook_missing"]


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
    assert [item["reason"] for item in result["skill_mount_violations"]] == ["shared_playbook_second_primary"]
