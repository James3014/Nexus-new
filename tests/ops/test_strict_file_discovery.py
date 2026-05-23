from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ops.strict_file_discovery import read_nonempty_json, strict_glob, strict_json_glob
from scripts.ops.strategic_map_audit import audit_strategic_map


def test_strict_glob_fails_empty_match(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="glob matched no files"):
        strict_glob(tmp_path, "missing/*.json", label="manifest")


def test_strict_json_glob_fails_empty_json(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty JSON file"):
        strict_json_glob(tmp_path, "*.json", label="manifest")


def test_read_nonempty_json_fails_corrupt_json(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        read_nonempty_json(manifest, label="manifest")


def test_strategic_map_audit_fails_fast_for_empty_boundary_glob(tmp_path: Path):
    _write_file(tmp_path / "nexus" / "core" / "state_contracts.py", "# runtime\n")
    _write_file(tmp_path / "tests" / "core" / "test_state_contracts.py", "# tests\n")
    manifest = {
        "schema_version": "nexus_strategic_map.v1",
        "zones": [
            {
                "name": "state_contracts",
                "kind": "core_fort",
                "runtime_refs": ["nexus/core/state_contracts.py"],
                "test_refs": ["tests/core/test_state_contracts.py"],
            }
        ],
        "boundary_rules": [
            {
                "name": "infra_no_services",
                "source_globs": ["nexus/infrastructure/*.py"],
                "forbidden_import_prefixes": ["nexus.services"],
            }
        ],
    }
    manifest_path = tmp_path / "strategic_map_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="strategic boundary rule infra_no_services"):
        audit_strategic_map(root=tmp_path, manifest_path=manifest_path)


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
