#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE = PROJECT_ROOT / "docs/reports/NEXUS_SF2_CANDIDATE_MATERIALIZATION_BUNDLE_2026-05-18.json"
DEFAULT_STATUS_OUTPUT = PROJECT_ROOT / "docs/reports/NEXUS_SF2_CANDIDATE_ASSET_STATUS_2026-05-18.json"


def _load_assets(bundle_path: Path, batch_id: str | None) -> list[dict[str, object]]:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    assets = [asset for asset in bundle.get("assets", []) if isinstance(asset, dict)]
    if batch_id is None:
        return assets

    batch_path = bundle_path.with_name("NEXUS_SF2_MATERIALIZATION_BATCH_PLAN_2026-05-18.json")
    batch_plan = json.loads(batch_path.read_text(encoding="utf-8"))
    batches = [batch for batch in batch_plan.get("batches", []) if isinstance(batch, dict)]
    selected = next((batch for batch in batches if batch.get("batch_id") == batch_id), None)
    if selected is None:
        raise SystemExit(f"unknown batch_id: {batch_id}")
    selected_ids = set(selected.get("skill_ids", []))
    return [asset for asset in assets if asset.get("skill_id") in selected_ids]


def materialize_assets(bundle_path: Path, batch_id: str | None, dry_run: bool) -> dict[str, object]:
    assets = _load_assets(bundle_path, batch_id)
    written_paths: list[str] = []
    for asset in assets:
        target_path = str(asset.get("target_path") or "")
        skill_md = str(asset.get("skill_md") or "")
        if not target_path or not skill_md:
            raise SystemExit(f"invalid materialization asset: {asset.get('skill_id')}")
        resolved = PROJECT_ROOT / target_path
        if not resolved.resolve().is_relative_to(PROJECT_ROOT):
            raise SystemExit(f"target_path escapes project root: {target_path}")
        written_paths.append(str(resolved.relative_to(PROJECT_ROOT)))
        if dry_run:
            continue
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(skill_md, encoding="utf-8")

    return {
        "status": "PASS",
        "batch_id": batch_id or "ALL",
        "dry_run": dry_run,
        "asset_count": len(assets),
        "written_paths": written_paths,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
    }


def verify_materialized_assets(bundle_path: Path) -> dict[str, object]:
    assets = _load_assets(bundle_path, None)
    statuses: list[dict[str, object]] = []
    blockers: list[str] = []
    for asset in assets:
        skill_id = str(asset.get("skill_id") or "")
        target_path = str(asset.get("target_path") or "")
        resolved = PROJECT_ROOT / target_path
        exists = resolved.exists()
        content = resolved.read_text(encoding="utf-8") if exists else ""
        runtime_blocked = "runtime_eligible: false" in content
        public_blocked = "public_benchmark_allowed: false" in content
        candidate_only = "candidate-only" in content
        status = "PASS" if exists and runtime_blocked and public_blocked and candidate_only else "BLOCKED"
        if status != "PASS":
            blockers.append(skill_id)
        statuses.append(
            {
                "skill_id": skill_id,
                "target_path": target_path,
                "status": status,
                "exists": exists,
                "runtime_update_allowed": False,
                "runtime_eligible_false_present": runtime_blocked,
                "public_benchmark_allowed": False,
                "public_benchmark_false_present": public_blocked,
                "candidate_only_boundary_present": candidate_only,
            }
        )

    return {
        "schema": "nexus.sf2_candidate_asset_status.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "asset_count": len(assets),
            "status_visible_asset_count": sum(1 for item in statuses if item["status"] == "PASS"),
            "blocker_count": len(blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "bounded_probe_allowed": not blockers,
        },
        "blockers": blockers,
        "assets": statuses,
        "claim_boundary": [
            "Status-visible means candidate assets exist and preserve candidate-only boundaries.",
            "This report does not promote any SF2 candidate to runtime default.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize SF2 candidate-only skill assets by bounded batch.")
    parser.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    parser.add_argument("--batch-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--status-output", default=str(DEFAULT_STATUS_OUTPUT))
    args = parser.parse_args(argv)
    if args.verify_only:
        result = verify_materialized_assets(Path(args.bundle))
        output = Path(args.status_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    result = materialize_assets(Path(args.bundle), args.batch_id, args.dry_run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
