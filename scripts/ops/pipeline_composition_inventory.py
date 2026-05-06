#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_PHASES = {"P", "X", "D", "R", "A", "C"}
KNOWN_LEGACY_MIXINS = {
    "PipelineStagesMixin",
    "PipelineRepairMixin",
    "PipelineCrystalMixin",
    "PipelineResearchMixin",
}


def _class_bases(path: Path, class_name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [getattr(base, "id", getattr(base, "attr", "")) for base in node.bases]
    return []


def _builder_phases(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    phases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("build_"):
            continue
        name = node.name
        if name == "build_plan_executor":
            phases.add("P")
        elif name == "build_research_executor":
            phases.add("X")
        elif name == "build_diagnose_executor":
            phases.add("D")
        elif name == "build_repair_executor":
            phases.add("R")
        elif name == "build_audit_executor":
            phases.add("A")
        elif name == "build_crystallize_executor":
            phases.add("C")
    return sorted(phases)


def _mixin_classes(engine_root: Path) -> list[str]:
    classes: set[str] = set()
    for path in sorted(engine_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Mixin"):
                classes.add(node.name)
    return sorted(classes)


def build_inventory(repo_root: Path) -> dict[str, Any]:
    engine_root = repo_root / "nexus" / "engine"
    phase_executors = engine_root / "phase_executors.py"
    pipeline = engine_root / "pipeline.py"
    builder_phases = _builder_phases(phase_executors)
    pipeline_bases = _class_bases(pipeline, "NexusPipeline")
    mixin_classes = _mixin_classes(engine_root)
    unexpected_mixins = sorted(set(mixin_classes) - KNOWN_LEGACY_MIXINS)
    missing_phases = sorted(EXPECTED_PHASES - set(builder_phases))
    return {
        "schema_version": "nexus_pipeline_composition_inventory.v1",
        "passed": not missing_phases and not unexpected_mixins,
        "phase_executor_builders": builder_phases,
        "missing_phase_executor_builders": missing_phases,
        "nexus_pipeline_bases": pipeline_bases,
        "legacy_mixins": sorted(set(pipeline_bases) & KNOWN_LEGACY_MIXINS),
        "composition_status": "partial" if set(pipeline_bases) & KNOWN_LEGACY_MIXINS else "implemented",
        "mixin_classes": mixin_classes,
        "unexpected_mixins": unexpected_mixins,
        "failures": [
            *({"reason": "phase_executor_builder_missing", "phase": phase} for phase in missing_phases),
            *({"reason": "unexpected_new_mixin", "class": name} for name in unexpected_mixins),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory Nexus pipeline composition seams.")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    payload = build_inventory(Path(args.repo_root).resolve())
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
