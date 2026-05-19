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

from nexus.contracts.claim_evidence_read_model import validate_claim_evidence_read_model
from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path(".nexus/reports/optimization_artifact_hygiene.json")


def check_optimization_artifact_hygiene(
    *,
    read_model_path: Path,
    retention_manifest_path: Path | None = None,
    output_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    read_model = _load_json(read_model_path)
    blockers = [f"read_model:{item}" for item in validate_claim_evidence_read_model(read_model)]
    if bool(read_model.get("runtime_update_allowed", False)):
        blockers.append("read_model:runtime_update_allowed")
    if bool(read_model.get("public_benchmark_allowed", False)):
        blockers.append("read_model:public_benchmark_allowed")

    retention_status = "NOT_PROVIDED"
    if retention_manifest_path is not None:
        retention = _load_json(retention_manifest_path)
        retention_status = str(retention.get("status") or "RETURN")
        summary = retention.get("summary", {})
        summary = summary if isinstance(summary, dict) else {}
        if retention_status != "PASS":
            blockers.append("retention_manifest:not_pass")
        if int(summary.get("blocker_count") or 0) > 0:
            blockers.append("retention_manifest:blockers_present")

    payload = {
        "schema": "nexus_optimization_artifact_hygiene.v1",
        "status": "PASS" if not blockers else "RETURN",
        "dry_run": bool(dry_run),
        "read_model_path": str(read_model_path),
        "retention_manifest_path": str(retention_manifest_path) if retention_manifest_path else "",
        "retention_status": retention_status,
        "blockers": sorted(set(blockers)),
        "claim_boundary": [
            "This hygiene hook validates report artifacts only.",
            "It must not mutate runtime policy or delete files.",
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
    parser = argparse.ArgumentParser(description="Validate Nexus optimization report hygiene artifacts.")
    parser.add_argument("--read-model", required=True, type=Path)
    parser.add_argument("--retention-manifest", default=None, type=Path)
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir if str(args.output_dir) else None
    output = resolve_report_output(DEFAULT_OUTPUT, output=args.output, output_dir=output_dir)
    try:
        payload = check_optimization_artifact_hygiene(
            read_model_path=args.read_model,
            retention_manifest_path=args.retention_manifest,
            output_path=output,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns structured failure.
        payload = {
            "schema": "nexus_optimization_artifact_hygiene.v1",
            "status": "RETURN",
            "error": str(exc),
            "dry_run": bool(args.dry_run),
            "read_model_path": str(args.read_model),
            "retention_manifest_path": str(args.retention_manifest) if args.retention_manifest else "",
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
