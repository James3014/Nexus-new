from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ZoneKind = Literal["core_fort", "hazard_zone", "fragile_supply_line"]


@dataclass(frozen=True)
class StrategicZone:
    name: str
    kind: ZoneKind
    runtime_refs: tuple[str, ...]
    test_refs: tuple[str, ...]


@dataclass(frozen=True)
class BoundaryRule:
    name: str
    source_globs: tuple[str, ...]
    forbidden_import_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class StrategicMap:
    zones: tuple[StrategicZone, ...]
    boundary_rules: tuple[BoundaryRule, ...]


def load_strategic_map(path: str | Path) -> StrategicMap:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "nexus_strategic_map.v1":
        raise ValueError("unsupported strategic map schema")
    zones = tuple(_zone(item) for item in payload.get("zones", []))
    boundary_rules = tuple(_boundary_rule(item) for item in payload.get("boundary_rules", []))
    return StrategicMap(zones=zones, boundary_rules=boundary_rules)


def _zone(item: dict[str, Any]) -> StrategicZone:
    kind = str(item.get("kind") or "")
    if kind not in {"core_fort", "hazard_zone", "fragile_supply_line"}:
        raise ValueError(f"unsupported strategic zone kind: {kind}")
    return StrategicZone(
        name=str(item.get("name") or ""),
        kind=kind,  # type: ignore[arg-type]
        runtime_refs=tuple(str(ref) for ref in item.get("runtime_refs", []) if str(ref)),
        test_refs=tuple(str(ref) for ref in item.get("test_refs", []) if str(ref)),
    )


def _boundary_rule(item: dict[str, Any]) -> BoundaryRule:
    return BoundaryRule(
        name=str(item.get("name") or ""),
        source_globs=tuple(str(ref) for ref in item.get("source_globs", []) if str(ref)),
        forbidden_import_prefixes=tuple(str(ref) for ref in item.get("forbidden_import_prefixes", []) if str(ref)),
    )
