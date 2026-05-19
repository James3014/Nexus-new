#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.contracts.publication_readiness import build_publication_readiness_gate
from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path("docs/reports/NEXUS_PUBLICATION_READINESS_GATE_2026-05-20.json")


def build_gate_from_files(
    *,
    benchmark_summary_path: Path,
    read_model_path: Path,
    output_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    benchmark_summary = _load_json(benchmark_summary_path)
    read_model = _load_json(read_model_path)
    gate = build_publication_readiness_gate(benchmark_summary, read_model)
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(gate, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "schema": "nexus_publication_readiness_gate_export.v1",
        "status": gate["status"],
        "publication_ready": gate["publication_ready"],
        "public_benchmark_allowed": gate["public_benchmark_allowed"],
        "blocker_count": len(gate["blockers"]),
        "output_path": str(output_path),
        "dry_run": bool(dry_run),
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a publication readiness gate from public benchmark evidence.")
    parser.add_argument("--benchmark-summary", required=True, type=Path)
    parser.add_argument("--read-model", required=True, type=Path)
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir if str(args.output_dir) else None
    output = resolve_report_output(DEFAULT_OUTPUT, output=args.output, output_dir=output_dir)
    try:
        summary = build_gate_from_files(
            benchmark_summary_path=args.benchmark_summary,
            read_model_path=args.read_model,
            output_path=output,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        summary = {
            "schema": "nexus_publication_readiness_gate_export.v1",
            "status": "RETURN",
            "error": str(exc),
            "output_path": str(output),
            "dry_run": bool(args.dry_run),
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
