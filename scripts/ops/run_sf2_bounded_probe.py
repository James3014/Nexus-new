#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.sf2_bounded_probe import build_sf2_probe_verdict_catalog, run_sf2_probe_chunk


DEFAULT_EXECUTION = Path("docs/reports/NEXUS_SF2_BOUNDED_PROBE_EXECUTION_MANIFEST_2026-05-18.json")
DEFAULT_TASKS = Path("docs/reports/NEXUS_SF2_BOUNDED_PROBE_TASK_MANIFEST_2026-05-18.json")
DEFAULT_CHUNKS = Path("docs/reports/NEXUS_SF2_BOUNDED_PROBE_CHUNK_PLAN_2026-05-18.json")
DEFAULT_OUTPUT_ROOT = Path("docs/reports/sf2_bounded_probe_chunks_2026-05-18")
DEFAULT_CATALOG = Path("docs/reports/NEXUS_SF2_ROUTE_SKILL_VERDICT_CATALOG_2026-05-18.json")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SF2 bounded-probe chunks without public benchmark promotion.")
    parser.add_argument("--execution-manifest", default=str(DEFAULT_EXECUTION))
    parser.add_argument("--task-manifest", default=str(DEFAULT_TASKS))
    parser.add_argument("--chunk-plan", default=str(DEFAULT_CHUNKS))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--catalog-output", default=str(DEFAULT_CATALOG))
    parser.add_argument("--chunk-id", default="all")
    args = parser.parse_args(argv)

    execution = json.loads(Path(args.execution_manifest).read_text(encoding="utf-8"))
    tasks = json.loads(Path(args.task_manifest).read_text(encoding="utf-8"))
    chunk_plan = json.loads(Path(args.chunk_plan).read_text(encoding="utf-8"))
    chunks = [chunk for chunk in chunk_plan.get("chunks", []) if isinstance(chunk, dict)]
    if args.chunk_id != "all":
        chunks = [chunk for chunk in chunks if str(chunk.get("chunk_id") or "") == args.chunk_id]

    output_root = Path(args.output_root)
    reports = []
    for chunk in chunks:
        report = run_sf2_probe_chunk(
            execution_manifest=execution,
            task_manifest=tasks,
            chunk=chunk,
            repo_root=PROJECT_ROOT,
        )
        reports.append(report)
        _write(output_root / f"{report['chunk_id']}.json", report)

    catalog = build_sf2_probe_verdict_catalog(reports)
    if args.chunk_id == "all":
        _write(Path(args.catalog_output), catalog)

    print(
        json.dumps(
            {
                "status": "PASS" if reports and all(report["status"] == "PASS" for report in reports) else "RETURN",
                "chunk_count": len(reports),
                "row_count": sum(report["summary"]["row_count"] for report in reports),
                "pass_count": sum(report["summary"]["pass_count"] for report in reports),
                "return_count": sum(report["summary"]["return_count"] for report in reports),
                "catalog_status": catalog["status"],
                "blocked_capability_count": catalog["summary"]["blocked_capability_count"],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
