#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.contracts.optimization_report import ProviderTokenCleanliness
from nexus.contracts.sf_replacement import build_sf_replacement_cleanliness_manifest


def build_manifest_from_sf_rollup(
    *,
    rollup_path: Path,
    output_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    rollup = json.loads(rollup_path.read_text(encoding="utf-8"))
    rows = rollup.get("rows", []) or []
    if not isinstance(rows, list):
        raise ValueError("invalid_sf_rollup_rows")
    normalized = [rollup_row_to_replacement_gate_row(row) for row in rows if isinstance(row, Mapping)]
    manifest = build_sf_replacement_cleanliness_manifest(normalized)
    manifest["source_path"] = str(rollup_path)
    manifest["source_schema"] = str(rollup.get("schema") or "")
    manifest["rollup_verdict_counts"] = _count(str(row.get("verdict") or "") for row in rows if isinstance(row, Mapping))
    if not dry_run:
        _write(output_path, manifest)
    return _summary(manifest, output_path=output_path, dry_run=dry_run)


def rollup_row_to_replacement_gate_row(row: Mapping[str, Any]) -> dict[str, Any]:
    current = row.get("current_best", {})
    challenger = row.get("challenger", {})
    current = current if isinstance(current, Mapping) else {}
    challenger = challenger if isinstance(challenger, Mapping) else {}
    return {
        "capability": str(row.get("capability") or ""),
        "current_skill": str(current.get("skill_id") or ""),
        "challenger_skill": str(challenger.get("skill_id") or ""),
        "status": "PASS" if _arm_pass(current) and _arm_pass(challenger) else "RETURN",
        "current_runtime_receipt_chain_ok": _arm_receipt_ok(current),
        "challenger_runtime_receipt_chain_ok": _arm_receipt_ok(challenger),
        "challenger_effective": bool(challenger.get("effective", False)),
        "same_provider_cleanliness_window": _provider_cleanliness(current) == _provider_cleanliness(challenger),
        "current_provider_token_cleanliness": _provider_cleanliness(current).value,
        "challenger_provider_token_cleanliness": _provider_cleanliness(challenger).value,
        "token_delta": row.get("token_delta_challenger_minus_current"),
        "wall_delta_sec": row.get("wall_delta_challenger_minus_current"),
    }


def _arm_pass(arm: Mapping[str, Any]) -> bool:
    return (
        str(arm.get("status") or "") == "PASS"
        and str(arm.get("benchmark_status") or "") == "SUCCESS"
        and str(arm.get("semantic_status") or "") == "VERIFIED"
        and not bool(arm.get("trust_mismatch", False))
    )


def _arm_receipt_ok(arm: Mapping[str, Any]) -> bool:
    return _arm_pass(arm) and bool(arm.get("effective", False)) and str(arm.get("skill_mount_contract_status") or "") == "PASS"


def _provider_cleanliness(arm: Mapping[str, Any]) -> ProviderTokenCleanliness:
    model_calls = int(arm.get("model_calls") or 0)
    if model_calls <= 0:
        return ProviderTokenCleanliness.NOT_APPLICABLE
    if bool(arm.get("provider_token_measured", False)):
        return ProviderTokenCleanliness.MEASURED
    return ProviderTokenCleanliness.MISSING


def _summary(manifest: dict[str, Any], *, output_path: Path, dry_run: bool) -> dict[str, Any]:
    return {
        "schema": "nexus_sf_replacement_cleanliness_manifest_export.v1",
        "status": manifest["status"],
        "dry_run": bool(dry_run),
        "output_path": str(output_path),
        "decision_count": manifest["summary"]["decision_count"],
        "replace_count": manifest["summary"]["replace_count"],
        "hold_count": manifest["summary"]["hold_count"],
        "no_replacement_count": manifest["summary"]["no_replacement_count"],
        "runtime_update_allowed": manifest["summary"]["runtime_update_allowed"],
        "public_benchmark_allowed": manifest["summary"]["public_benchmark_allowed"],
    }


def _count(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF replacement cleanliness manifest from an SF live rollup.")
    parser.add_argument("--rollup", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = build_manifest_from_sf_rollup(
            rollup_path=args.rollup,
            output_path=args.output,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary returns structured failure.
        summary = {
            "schema": "nexus_sf_replacement_cleanliness_manifest_export.v1",
            "status": "RETURN",
            "error": str(exc),
            "dry_run": bool(args.dry_run),
            "output_path": str(args.output),
        }
    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
