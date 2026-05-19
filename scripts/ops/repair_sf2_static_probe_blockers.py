#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from nexus.learning.skill_route_taxonomy import CAPABILITY_BY_ID


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "docs/reports/NEXUS_SF2_ROUTE_SKILL_VERDICT_CATALOG_2026-05-18.json"
DEFAULT_TASKS = PROJECT_ROOT / "docs/reports/NEXUS_SF2_STATIC_REPAIR_TASK_MANIFEST_2026-05-18.json"
DEFAULT_EXECUTION = PROJECT_ROOT / "docs/reports/NEXUS_SF2_STATIC_REPAIR_EXECUTION_MANIFEST_2026-05-18.json"
DEFAULT_CHUNKS = PROJECT_ROOT / "docs/reports/NEXUS_SF2_STATIC_REPAIR_CHUNK_PLAN_2026-05-18.json"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _skill_text(capability_id: str) -> str:
    capability = CAPABILITY_BY_ID.get(capability_id)
    keywords = ", ".join(capability.keywords if capability else (capability_id,))
    phases = ", ".join(capability.phases if capability else ())
    return f"""# SF2 {capability_id} Route Fit Spec

Purpose: candidate-only route-fit skill for `{capability_id}`.

Capability keywords: {keywords}
Phases: {phases}

Use when:
- The route capability is `{capability_id}`.
- The bounded probe requires selected / injected / used / evidence / gate / outcome receipts.

Evidence contract:
- Emit receipt evidence for route fit.
- Preserve gate evidence and outcome contribution notes.
- Never update runtime defaults from this candidate-only asset.

runtime_eligible: false
public_benchmark_allowed: false
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize SF2 static-probe repair assets for blocked capabilities.")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    parser.add_argument("--task-output", default=str(DEFAULT_TASKS))
    parser.add_argument("--execution-output", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--chunk-output", default=str(DEFAULT_CHUNKS))
    args = parser.parse_args(argv)

    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    blocked = [str(item) for item in catalog.get("blocked_capabilities", [])]
    tasks = []
    rows = []
    for capability_id in blocked:
        skill_id = f"sf2-{_safe_id(capability_id)}-route-fit-spec"
        skill_dir = PROJECT_ROOT / ".agents" / "skills" / "sf2" / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_dir.joinpath("SKILL.md").write_text(_skill_text(capability_id), encoding="utf-8")
        task_id = f"sf2-static-repair-{capability_id}-001"
        tasks.append(
            {
                "id": task_id,
                "task_id": task_id,
                "capability_id": capability_id,
                "difficulty": "medium",
                "task_type": "sf2_static_repair",
                "task_desc": f"Repair SF2 static route-fit coverage for {capability_id}.",
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )
        for arm_type, row_skill in (
            ("capability_only", ""),
            ("skill_arm", skill_id),
            ("negative_control", ""),
        ):
            row_id = f"{capability_id}::{arm_type}" + (f"::{row_skill}" if row_skill else "")
            rows.append(
                {
                    "row_id": row_id,
                    "capability_id": capability_id,
                    "capability": capability_id,
                    "arm_type": arm_type,
                    "skill_id": row_skill or None,
                    "task_ref": {"manifest": str(Path(args.task_output)), "task_id": task_id},
                    "runtime_update_allowed": False,
                    "public_benchmark_allowed": False,
                }
            )
    chunks = [
        {
            "chunk_id": "SF2-I3-REPAIR-01",
            "status": "READY" if rows else "BLOCKED",
            "row_count": len(rows),
            "row_ids": [row["row_id"] for row in rows],
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        }
    ]
    _write(Path(args.task_output), {"schema": "nexus.sf2_static_repair_task_manifest.v1", "tasks": tasks})
    _write(
        Path(args.execution_output),
        {
            "schema": "nexus.sf2_static_repair_execution_manifest.v1",
            "status": "PASS" if rows else "BLOCKED",
            "summary": {"row_count": len(rows), "runtime_update_allowed": False, "public_benchmark_allowed": False},
            "rows": rows,
        },
    )
    _write(
        Path(args.chunk_output),
        {
            "schema": "nexus.sf2_static_repair_chunk_plan.v1",
            "status": "PASS" if rows else "BLOCKED",
            "summary": {"chunk_count": len(chunks), "row_count": len(rows)},
            "chunks": chunks,
        },
    )
    print(json.dumps({"status": "PASS", "blocked_repaired": len(blocked), "row_count": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
