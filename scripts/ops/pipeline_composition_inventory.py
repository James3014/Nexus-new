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
RUNTIME_OWNED_PHASES = {"P", "X", "D", "R", "A", "C"}


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


def _registered_executor_phases(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    phases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        target = getattr(node.target, "id", "")
        if target != "name":
            continue
        iterable = node.iter
        if not isinstance(iterable, (ast.Tuple, ast.List)):
            continue
        values = []
        for item in iterable.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value)
        if set(values) >= EXPECTED_PHASES:
            phases.update(values)
    return sorted(phases)


def _factory_create_all_phases(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    phases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "create_all":
            continue
        for child in ast.walk(node):
            if not isinstance(child, (ast.Tuple, ast.List)):
                continue
            values = []
            for item in child.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    values.append(item.value)
            if set(values) >= EXPECTED_PHASES:
                phases.update(values)
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
    phase_factory = engine_root / "phase_factory.py"
    builder_phases = _builder_phases(phase_executors)
    registered_executor_phases = _registered_executor_phases(pipeline)
    factory_phases = _factory_create_all_phases(phase_factory)
    pipeline_bases = _class_bases(pipeline, "NexusPipeline")
    mixin_classes = _mixin_classes(engine_root)
    unexpected_mixins = sorted(set(mixin_classes) - KNOWN_LEGACY_MIXINS)
    missing_phases = sorted(EXPECTED_PHASES - set(builder_phases))
    missing_registered_phases = sorted(EXPECTED_PHASES - set(registered_executor_phases))
    missing_factory_phases = sorted(EXPECTED_PHASES - set(factory_phases))
    runtime_missing = sorted(RUNTIME_OWNED_PHASES - set(builder_phases) - set(registered_executor_phases) - set(factory_phases))
    legacy_mixins = sorted(set(pipeline_bases) & KNOWN_LEGACY_MIXINS)
    phase_ownership_status = (
        "executor_owned_with_legacy_mixins_retained"
        if not runtime_missing and legacy_mixins
        else "executor_owned"
        if not runtime_missing
        else "incomplete"
    )
    runtime_fallback_paths = []
    if "A" in registered_executor_phases:
        runtime_fallback_paths.append(
            {
                "phase": "A",
                "status": "legacy_fallback_if_executor_missing",
                "reason": "repair_audit_loop_uses_legacy_audit_when_no_a_executor_is_registered",
            }
        )
    if "C" in registered_executor_phases:
        runtime_fallback_paths.append(
            {
                "phase": "C",
                "status": "side_effect_guarded_fallback",
                "reason": "crystallize_executor_must_emit_terminal_side_effects_or_pipeline_falls_back",
            }
        )
    fallback_debt_phases = sorted({str(item["phase"]) for item in runtime_fallback_paths})
    return {
        "schema_version": "nexus_pipeline_composition_inventory.v1",
        "passed": not missing_phases and not missing_registered_phases and not missing_factory_phases and not runtime_missing and not unexpected_mixins,
        "phase_executor_builders": builder_phases,
        "missing_phase_executor_builders": missing_phases,
        "registered_executor_phases": registered_executor_phases,
        "missing_registered_executor_phases": missing_registered_phases,
        "phase_factory_create_all_phases": factory_phases,
        "missing_phase_factory_create_all_phases": missing_factory_phases,
        "runtime_owned_phases": sorted(RUNTIME_OWNED_PHASES - set(runtime_missing)),
        "runtime_missing_phases": runtime_missing,
        "phase_ownership_status": phase_ownership_status,
        "runtime_fallback_paths": runtime_fallback_paths,
        "fallback_debt_phases": fallback_debt_phases,
        "fallback_debt_count": len(fallback_debt_phases),
        "nexus_pipeline_bases": pipeline_bases,
        "legacy_mixins": legacy_mixins,
        "composition_status": "partial" if legacy_mixins else "implemented",
        "mixin_classes": mixin_classes,
        "unexpected_mixins": unexpected_mixins,
        "failures": [
            *({"reason": "phase_executor_builder_missing", "phase": phase} for phase in missing_phases),
            *({"reason": "registered_executor_phase_missing", "phase": phase} for phase in missing_registered_phases),
            *({"reason": "phase_factory_create_all_missing", "phase": phase} for phase in missing_factory_phases),
            *({"reason": "runtime_owned_phase_missing", "phase": phase} for phase in runtime_missing),
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
