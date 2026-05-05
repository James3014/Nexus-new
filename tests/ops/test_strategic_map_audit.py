from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.strategic_map_audit import audit_strategic_map


def test_strategic_map_audit_passes_repository_map():
    audit = audit_strategic_map()

    assert audit.passed is True
    assert any(zone["kind"] == "hazard_zone" and zone["name"] == "hallucination_guard" for zone in audit.zones)


def test_strategic_map_audit_blocks_infrastructure_service_import(tmp_path: Path):
    _write_file(tmp_path / "nexus" / "infrastructure" / "bad.py", "from nexus.services.memory import MemoryService\n")
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

    audit = audit_strategic_map(root=tmp_path, manifest_path=manifest_path)

    assert audit.passed is False
    assert {
        "rule": "infra_no_services",
        "reason": "forbidden_import",
        "path": "nexus/infrastructure/bad.py",
        "module": "nexus.services.memory",
    } in audit.failures


def test_strategic_map_audit_requires_hazard_zone_tests(tmp_path: Path):
    _write_file(tmp_path / "nexus" / "core" / "context_hub.py", "# runtime\n")
    manifest = {
        "schema_version": "nexus_strategic_map.v1",
        "zones": [
            {
                "name": "context_hub",
                "kind": "hazard_zone",
                "runtime_refs": ["nexus/core/context_hub.py"],
                "test_refs": [],
            }
        ],
        "boundary_rules": [],
    }
    manifest_path = tmp_path / "strategic_map_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    audit = audit_strategic_map(root=tmp_path, manifest_path=manifest_path)

    assert audit.passed is False
    assert {"zone": "context_hub", "reason": "test_refs_missing"} in audit.failures
    assert {"zone": "context_hub", "reason": "hazard_zone_without_test_gate"} in audit.failures


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
