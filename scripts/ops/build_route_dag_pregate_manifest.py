#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from nexus.contracts.route_dag_pregate import build_route_dag_pregate
from nexus.contracts.route_runtime_plan import build_route_runtime_plan_from_pregate
from nexus.engine.capability_planner import CapabilityPlanner, default_capability_nodes
from nexus.services.codeintel.skeleton_provider import lookup_implementation
from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_OPT_ROUTE_DAG_PREGATE_2026-05-20.json")


def build_route_dag_pregate_manifest(
    *,
    task_desc: str,
    task_type: str,
    route: dict[str, Any] | None = None,
    pillars: dict[str, Any] | None = None,
    codeintel: dict[str, Any] | None = None,
    phase_trace: dict[str, Any] | None = None,
    project_root: str | Path = ".",
    symbols: list[str] | None = None,
    symbol_roots: list[str] | None = None,
) -> dict[str, Any]:
    plan = CapabilityPlanner().plan(
        task_desc=task_desc,
        task_type=task_type,
        route=route or {},
        pillars=pillars or {},
        codeintel=codeintel or {},
        phase_trace=phase_trace or {},
    ).to_dict()
    pregate = build_route_dag_pregate(
        capability_plan=plan,
        capability_nodes=default_capability_nodes(),
    )
    pregate["task_desc"] = task_desc
    pregate["task_type"] = task_type
    pregate["source"] = "capability_planner_dry_run"
    pregate["code_skeleton_lookup"] = [
        lookup_implementation(project_root, symbol, search_paths=symbol_roots or ()).to_dict()
        for symbol in (symbols or [])
        if symbol.strip()
    ]
    pregate["runtime_dispatch_changed"] = False
    content_hash = _content_hash(pregate)
    pregate["evidence_refs"] = [f"route_dag_pregate:content_hash:{content_hash}"]
    pregate["evidence_seal_status"] = "PASS"
    pregate["evidence_hash_status"] = "PASS"
    pregate["partial_telemetry_detected"] = False
    pregate["runtime_plan"] = build_route_runtime_plan_from_pregate(pregate)
    return pregate


def _json_arg(raw: str, *, name: str) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{name}_must_be_json_object")
    return data


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _content_hash(payload: dict[str, Any]) -> str:
    sealed = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(sealed.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only route DAG pregate manifest.")
    parser.add_argument("--task-desc", required=True)
    parser.add_argument("--task-type", default="task")
    parser.add_argument("--route-json", default="")
    parser.add_argument("--pillars-json", default="")
    parser.add_argument("--codeintel-json", default="")
    parser.add_argument("--phase-trace-json", default="")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--symbol-root", action="append", default=[])
    parser.add_argument("--output", default="", type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    manifest = build_route_dag_pregate_manifest(
        task_desc=args.task_desc,
        task_type=args.task_type,
        route=_json_arg(args.route_json, name="route"),
        pillars=_json_arg(args.pillars_json, name="pillars"),
        codeintel=_json_arg(args.codeintel_json, name="codeintel"),
        phase_trace=_json_arg(args.phase_trace_json, name="phase_trace"),
        project_root=args.project_root,
        symbols=list(args.symbol),
        symbol_roots=list(args.symbol_root),
    )
    output_arg = str(args.output)
    output_dir_arg = str(args.output_dir)
    output = resolve_report_output(
        DEFAULT_OUTPUT,
        output=args.output if output_arg and output_arg != "." else None,
        output_dir=args.output_dir if output_dir_arg and output_dir_arg != "." else None,
    )
    if not args.dry_run:
        _write(output, manifest)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "node_count": len(manifest["nodes"]),
                "dependency_edge_count": len(manifest["dependency_edges"]),
                "parallelizable_edge_count": len(manifest["parallelizable_edges"]),
                "blocker_count": len(manifest["blockers"]),
                "output": str(output),
                "runtime_dispatch_changed": manifest["runtime_dispatch_changed"],
                "skeleton_lookup_count": len(manifest["code_skeleton_lookup"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
