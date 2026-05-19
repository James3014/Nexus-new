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

from nexus.contracts.route_context_seam_freeze import build_route_context_seam_freeze
from scripts.ops.report_output import resolve_report_output


DEFAULT_OUTPUT = Path(".nexus/reports/route_context_seam_freeze.json")


def build_route_context_seam_freeze_from_artifacts(
    *,
    route_manifest_path: Path,
    context_contract_path: Path,
    claim_read_model_path: Path,
    output_path: Path,
    allowed_next_work: list[str] | tuple[str, ...] = (),
    dry_run: bool = False,
) -> dict[str, Any]:
    route_manifest = _load_json(route_manifest_path)
    context_contract = _load_json(context_contract_path)
    claim_read_model = _load_json(claim_read_model_path)
    payload = build_route_context_seam_freeze(
        route_manifest_ref=str(route_manifest_path),
        context_receipt_ref=str(context_contract_path),
        runtime_dispatch_changed=bool(route_manifest.get("runtime_dispatch_changed", False)),
        preserved_l0_l1=bool(context_contract.get("preserved_L0_L1", False)),
        claim_read_model_status=str(claim_read_model.get("status") or "RETURN"),
        allowed_next_work=allowed_next_work,
    )
    payload["claim_read_model_ref"] = str(claim_read_model_path)
    if not dry_run:
        _write(output_path, payload)
    return {
        "schema": "nexus_route_context_seam_freeze_export.v1",
        "status": payload["status"],
        "dry_run": bool(dry_run),
        "output_path": str(output_path),
        "route_manifest_path": str(route_manifest_path),
        "context_contract_path": str(context_contract_path),
        "claim_read_model_path": str(claim_read_model_path),
        "blocker_count": len(payload["blockers"]),
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid json object: {path}")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a route/context seam freeze from existing artifacts.")
    parser.add_argument("--route-manifest", required=True, type=Path)
    parser.add_argument("--context-contract", required=True, type=Path)
    parser.add_argument("--claim-read-model", required=True, type=Path)
    parser.add_argument("--allowed-next-work", action="append", default=[])
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument("--output-dir", default="", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir if str(args.output_dir) and str(args.output_dir) != "." else None
    output = resolve_report_output(DEFAULT_OUTPUT, output=args.output, output_dir=output_dir)
    try:
        summary = build_route_context_seam_freeze_from_artifacts(
            route_manifest_path=args.route_manifest,
            context_contract_path=args.context_contract,
            claim_read_model_path=args.claim_read_model,
            output_path=output,
            allowed_next_work=tuple(args.allowed_next_work),
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns structured failure.
        summary = {
            "schema": "nexus_route_context_seam_freeze_export.v1",
            "status": "RETURN",
            "error": str(exc),
            "dry_run": bool(args.dry_run),
            "output_path": str(output),
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
