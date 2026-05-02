from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.bench.sanitize_public_benchmark import sanitize_execution_manifest, sanitize_manifest


DEFAULT_LANES_FILE = Path("scripts/bench/public_benchmark_commercial_lanes_v1.json")


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_lane_tasks(*, lanes_file: str | Path = DEFAULT_LANES_FILE, lane: str = "all") -> dict[str, Any]:
    lane_manifest = _read_json(lanes_file)
    selected_lanes = [
        item
        for item in lane_manifest.get("lanes", [])
        if lane == "all" or str(item.get("id")) == lane
    ]
    if not selected_lanes:
        raise ValueError(f"unknown_commercial_lane:{lane}")

    task_cache: dict[str, dict[str, dict[str, Any]]] = {}
    tasks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for lane_item in selected_lanes:
        lane_id = str(lane_item["id"])
        for ref in lane_item.get("task_refs", []):
            manifest_path = str(ref["manifest"])
            task_id = str(ref["task_id"])
            cache = task_cache.setdefault(
                manifest_path,
                {str(task["id"]): task for task in _read_json(manifest_path).get("tasks", [])},
            )
            try:
                task = dict(cache[task_id])
            except KeyError as exc:
                raise ValueError(f"missing_task_ref:{manifest_path}:{task_id}") from exc
            dedupe_key = (manifest_path, task_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            task["commercial_lane"] = lane_id
            task["source_manifest"] = manifest_path
            tasks.append(task)

    return {
        "version": lane_manifest["version"],
        "frozen": True,
        "benchmark_id": f"{lane_manifest['benchmark_id']}:{lane}",
        "description": f"Compiled commercial benchmark lane: {lane}",
        "commercial_lane_source": str(lanes_file),
        "tasks": tasks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile Nexus commercial benchmark lanes into a runner tasks file.")
    parser.add_argument("--lanes-file", default=str(DEFAULT_LANES_FILE))
    parser.add_argument("--lane", default="all")
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--execution-safe-output",
        default="",
        help="Optional public execution-safe manifest path for external model runs.",
    )
    parser.add_argument(
        "--disclosure-output",
        default="",
        help="Optional disclosure manifest path for public benchmark preflight.",
    )
    args = parser.parse_args(argv)

    payload = build_lane_tasks(lanes_file=args.lanes_file, lane=args.lane)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.execution_safe_output:
        out = Path(args.execution_safe_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(sanitize_execution_manifest(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.disclosure_output:
        out = Path(args.disclosure_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(sanitize_manifest(payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
