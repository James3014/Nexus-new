from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bench.freeze_public_manifest import build_freeze_receipt, validate_manifest


def _base_manifest() -> dict:
    return {
        "version": "2026-04-25",
        "frozen": True,
        "benchmark_id": "pilot",
        "description": "test",
        "tasks": [
            {
                "id": "pub-bug-001",
                "category": "bugfix",
                "difficulty": "medium",
                "repo_kind": "neutral_fixture",
                "repo": "fixture://demo",
                "repo_ref": "v1",
                "task_desc": "Fix bug",
                "fixture_kind": "python_demo",
                "success_criteria": "patch_and_tests_pass",
                "mutation_required": True,
                "allowed_files": ["target.py", "test_target.py"],
                "forbidden_files": [".git/"],
                "setup_command": "python -m pytest --version",
                "verification_command": "python -m pytest -q test_target.py",
            }
        ],
    }


def test_validate_manifest_accepts_frozen_neutral_fixture(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_base_manifest()), encoding="utf-8")
    summary = validate_manifest(path, repo_root=tmp_path)
    assert summary["task_count"] == 1
    assert len(summary["manifest_sha256"]) == 64
    assert summary["category_counts"] == {"bugfix": 1}
    assert summary["repo_kind_counts"] == {"neutral_fixture": 1}


def test_validate_manifest_rejects_unfrozen_by_default(tmp_path: Path):
    payload = _base_manifest()
    payload["frozen"] = False
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen=true"):
        validate_manifest(path, repo_root=tmp_path)


def test_validate_manifest_rejects_placeholder_external_ref(tmp_path: Path):
    payload = _base_manifest()
    payload["tasks"][0].update(
        {
            "repo_kind": "external",
            "repo": "https://github.com/example/project",
            "repo_ref": "pinned-before-freeze",
        }
    )
    payload["tasks"][0].pop("fixture_kind")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="external repo_ref"):
        validate_manifest(path, repo_root=tmp_path)


def test_validate_manifest_rejects_duplicate_ids(tmp_path: Path):
    payload = _base_manifest()
    payload["tasks"].append(dict(payload["tasks"][0]))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate task ids"):
        validate_manifest(path, repo_root=tmp_path)


def test_build_freeze_receipt_has_stable_manifest_hash(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_base_manifest(), sort_keys=True), encoding="utf-8")
    first = build_freeze_receipt(path, repo_root=tmp_path)
    second = build_freeze_receipt(path, repo_root=tmp_path)
    assert first["schema"] == "nexus_public_benchmark_freeze_receipt_v1"
    assert first["status"] == "VERIFIED"
    assert first["manifest_sha256"] == second["manifest_sha256"]
