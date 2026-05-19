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

from nexus.contracts.route_context_seam_freeze import validate_route_context_seam_freeze
from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path(".nexus/reports/route_context_seam_freeze_check.json")


def check_route_context_seam_freeze(
    *,
    freeze_path: Path,
    output_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    freeze = _load_json(freeze_path)
    blockers = [f"freeze:{item}" for item in validate_route_context_seam_freeze(freeze)]
    if str(freeze.get("status") or "").upper() != "PASS":
        blockers.append("freeze:status_not_pass")
    if freeze.get("blockers"):
        blockers.append("freeze:blockers_present")

    payload = {
        "schema": "nexus_route_context_seam_freeze_check.v1",
        "status": "PASS" if not blockers else "RETURN",
        "dry_run": bool(dry_run),
        "freeze_path": str(freeze_path),
        "blockers": sorted(set(blockers)),
        "claim_boundary": [
            "This gate validates a route/context freeze artifact only.",
            "It must not approve runtime policy changes or public benchmark claims.",
        ],
    }
    if output_path is not None and not dry_run:
        _write(output_path, payload)
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid json object: {path}")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Nexus route/context seam freeze artifact.")
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir if str(args.output_dir) and str(args.output_dir) != "." else None
    output = resolve_report_output(DEFAULT_OUTPUT, output=args.output, output_dir=output_dir)
    try:
        payload = check_route_context_seam_freeze(
            freeze_path=args.freeze,
            output_path=output,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns structured failure.
        payload = {
            "schema": "nexus_route_context_seam_freeze_check.v1",
            "status": "RETURN",
            "error": str(exc),
            "dry_run": bool(args.dry_run),
            "freeze_path": str(args.freeze),
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
