#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.contracts.strategic_map import StrategicMap, load_strategic_map

DEFAULT_MANIFEST = REPO_ROOT / "docs" / "ops" / "strategic_map_manifest.json"


@dataclass(frozen=True)
class StrategicMapAudit:
    zones: list[dict[str, Any]]
    boundary_rules: list[dict[str, Any]]
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _imports_for(path: Path) -> list[str]:
    imports: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def audit_strategic_map(root: Path = REPO_ROOT, manifest_path: Path = DEFAULT_MANIFEST) -> StrategicMapAudit:
    strategic_map = load_strategic_map(manifest_path if manifest_path.is_absolute() else root / manifest_path)
    failures: list[dict[str, Any]] = []
    _audit_zone_refs(root, strategic_map, failures)
    _audit_boundary_rules(root, strategic_map, failures)
    return StrategicMapAudit(
        zones=[asdict(zone) for zone in strategic_map.zones],
        boundary_rules=[asdict(rule) for rule in strategic_map.boundary_rules],
        failures=failures,
    )


def _audit_zone_refs(root: Path, strategic_map: StrategicMap, failures: list[dict[str, Any]]) -> None:
    for zone in strategic_map.zones:
        if not zone.name:
            failures.append({"reason": "zone_name_missing"})
        if not zone.runtime_refs:
            failures.append({"zone": zone.name, "reason": "runtime_refs_missing"})
        if zone.kind in {"core_fort", "hazard_zone", "fragile_supply_line"} and not zone.test_refs:
            failures.append({"zone": zone.name, "reason": "test_refs_missing"})
        if zone.kind == "hazard_zone" and not any(ref.startswith("tests/") for ref in zone.test_refs):
            failures.append({"zone": zone.name, "reason": "hazard_zone_without_test_gate"})
        for ref in zone.runtime_refs + zone.test_refs:
            if not (root / ref).exists():
                failures.append({"zone": zone.name, "reason": "ref_missing", "ref": ref})


def _audit_boundary_rules(root: Path, strategic_map: StrategicMap, failures: list[dict[str, Any]]) -> None:
    for rule in strategic_map.boundary_rules:
        matched: list[Path] = []
        for pattern in rule.source_globs:
            matched.extend(sorted(root.glob(pattern)))
        if not matched:
            failures.append({"rule": rule.name, "reason": "boundary_rule_matched_no_files"})
            continue
        for path in matched:
            if path.suffix != ".py":
                continue
            for module in _imports_for(path):
                if any(module == prefix or module.startswith(prefix + ".") for prefix in rule.forbidden_import_prefixes):
                    failures.append(
                        {
                            "rule": rule.name,
                            "reason": "forbidden_import",
                            "path": str(path.relative_to(root)),
                            "module": module,
                        }
                    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Nexus strategic map runtime/test/boundary alignment.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    audit = audit_strategic_map(root=root, manifest_path=Path(args.manifest))
    print(json.dumps({"schema_version": "nexus_strategic_map_audit.v1", "passed": audit.passed, **asdict(audit)}, indent=2, ensure_ascii=False))
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
