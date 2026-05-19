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

from nexus.contracts.context_assembly import build_context_assembly_contract
from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path(".nexus/reports/context_assembly_contract.json")


def build_context_assembly_contract_from_source_manifest(
    *,
    input_path: Path,
    output_path: Path,
    token_budget: int,
    task_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    manifest = _load_json(input_path)
    sources = manifest.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("invalid context source manifest: sources must be a list")
    payload = build_context_assembly_contract(
        task_id=task_id,
        sources=[source for source in sources if isinstance(source, dict)],
        token_budget=token_budget,
    )
    payload["source_manifest_path"] = str(input_path)
    if not dry_run:
        _write(output_path, payload)
    return {
        "schema": "nexus_context_assembly_contract_export.v1",
        "status": payload["status"],
        "dry_run": bool(dry_run),
        "input_path": str(input_path),
        "output_path": str(output_path),
        "task_id": task_id,
        "source_count": len(sources),
        "kept_source_count": payload["kept_source_count"],
        "dropped_source_count": payload["dropped_source_count"],
        "blocker_count": len(payload["blockers"]),
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid context source manifest: expected object")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Nexus context assembly contract from a source manifest.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    parser.add_argument("--token-budget", required=True, type=int)
    parser.add_argument("--task-id", default="context-assembly")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir if str(args.output_dir) and str(args.output_dir) != "." else None
    output = resolve_report_output(DEFAULT_OUTPUT, output=args.output, output_dir=output_dir)
    try:
        summary = build_context_assembly_contract_from_source_manifest(
            input_path=args.input,
            output_path=output,
            token_budget=args.token_budget,
            task_id=args.task_id,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns structured failure.
        summary = {
            "schema": "nexus_context_assembly_contract_export.v1",
            "status": "RETURN",
            "error": str(exc),
            "dry_run": bool(args.dry_run),
            "input_path": str(args.input),
            "output_path": str(output),
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
