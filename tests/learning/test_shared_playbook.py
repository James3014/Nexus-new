from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
import yaml

from nexus.learning.shared_playbook import SharedPlaybookError, load_selected_shared_playbook

REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_diagnose_skill(tmp_path: Path) -> Path:
    source = REPO_ROOT / ".agents" / "skills" / "diagnose"
    target = tmp_path / ".agents" / "skills" / "diagnose"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return target


def _mutate_manifest(skill_dir: Path, mutate) -> None:
    path = skill_dir / "playbook.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_diagnose_shared_playbook_binds_exact_manifest_and_instructions_hashes() -> None:
    identity = load_selected_shared_playbook("diagnose", "xray", root=REPO_ROOT, required=True)
    assert identity is not None
    assert identity.playbook_id == "diagnose"
    assert identity.version == "1.0.0"
    assert identity.status == "CANDIDATE"
    assert identity.primary is True
    assert identity.trace_authority == "DERIVED_ONLY"
    assert (
        identity.manifest_sha256
        == hashlib.sha256((REPO_ROOT / identity.manifest_path).read_bytes()).hexdigest()
    )
    assert (
        identity.instructions_sha256
        == hashlib.sha256((REPO_ROOT / identity.instructions_path).read_bytes()).hexdigest()
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
