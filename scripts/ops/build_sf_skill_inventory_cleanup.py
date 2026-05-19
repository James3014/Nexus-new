#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_inventory_roots import (
    DEFAULT_SKILL_ROOTS,
    build_canonical_capability_buckets,
    build_full_skill_inventory,
    build_identity_dedup_report,
    build_pairing_identity_recheck,
)


DEFAULT_INVENTORY = Path("docs/reports/NEXUS_SF_FULL_SKILL_INVENTORY_2026-05-18.json")
DEFAULT_DEDUP = Path("docs/reports/NEXUS_SF_SKILL_IDENTITY_DEDUP_2026-05-18.json")
DEFAULT_BUCKETS = Path("docs/reports/NEXUS_SF_CANONICAL_CAPABILITY_BUCKETS_2026-05-18.json")
DEFAULT_RECHECK = Path("docs/reports/NEXUS_SF_PAIRING_IDENTITY_RECHECK_2026-05-18.json")
DEFAULT_FINAL_PAIRING = Path("docs/reports/NEXUS_SF_FINAL_PAIRING_V2_2026-05-18.json")
DEFAULT_PATCH_PLAN = Path("docs/reports/NEXUS_SF3_RUNTIME_POLICY_PATCH_PLAN_2026-05-18.json")
DEFAULT_PROMOTION_REVIEW = Path("docs/reports/NEXUS_SF2_PROMOTION_REVIEW_2026-05-18.json")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _final_pairing_report(inventory: dict, dedup: dict, buckets: dict, recheck: dict) -> dict:
    recheck_by_capability = {
        item["capability_id"]: item
        for item in recheck.get("pairings", []) or []
        if isinstance(item, dict)
    }
    rows = []
    for bucket in buckets.get("capability_buckets", []) or []:
        capability_id = str(bucket.get("capability_id") or "")
        pairing = recheck_by_capability.get(capability_id, {})
        top = (bucket.get("top_candidates") or [{}])[0] if bucket.get("top_candidates") else {}
        rows.append(
            {
                "capability_id": capability_id,
                "current_pairing_skill_id": pairing.get("skill_id", ""),
                "current_pairing_identity_id": pairing.get("identity_id", ""),
                "current_pairing_skill_path": pairing.get("skill_path", ""),
                "current_pairing_sha256": pairing.get("sha256", ""),
                "current_pairing_source_status": pairing.get("source_status", ""),
                "current_pairing_status": pairing.get("status", "MISSING"),
                "current_pairing_score": pairing.get("score", 0),
                "current_pairing_runtime_eligible": bool(pairing.get("runtime_eligible")),
                "current_pairing_ablation_eligible": bool(pairing.get("ablation_eligible")),
                "canonical_top_skill_id": top.get("skill_id", ""),
                "canonical_top_identity_id": top.get("identity_id", ""),
                "canonical_top_skill_path": top.get("skill_path", ""),
                "canonical_top_sha256": top.get("sha256", ""),
                "canonical_top_source_status": top.get("source_status", ""),
                "canonical_top_score": top.get("score", 0),
                "canonical_top_runtime_eligible": bool(top.get("runtime_eligible")),
                "canonical_top_ablation_eligible": bool(top.get("ablation_eligible")),
                "candidate_count": int(bucket.get("candidate_count") or 0),
                "decision": "use_current_pairing_for_review"
                if pairing.get("status") == "PASS"
                else "use_canonical_top_for_bounded_probe"
                if top
                else "candidate_supply_gap",
            }
        )
    blockers = [
        row["capability_id"]
        for row in rows
        if row["decision"] == "candidate_supply_gap" or row["current_pairing_status"] == "BLOCKED"
    ]
    return {
        "schema": "nexus.sf_final_pairing_v2.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "skill_file_count": inventory["summary"]["skill_file_count"],
            "unique_skill_id_count": inventory["summary"]["unique_skill_id_count"],
            "safe_delete_candidate_count": dedup["summary"]["safe_delete_candidate_count"],
            "manual_review_required_count": dedup["summary"]["manual_review_required_count"],
            "capability_count": len(rows),
            "capabilities_with_candidates": buckets["summary"]["capabilities_with_candidates"],
            "pairing_blocker_count": recheck["summary"]["blocker_count"],
            "sf_clean_closed": not blockers
            and dedup["summary"]["safe_delete_candidate_count"] == 0
            and buckets["summary"]["capabilities_without_candidates"] == 0
            and recheck["summary"]["blocker_count"] == 0,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "pairings": rows,
        "claim_boundary": [
            "This final pairing report closes SF cleanup and pairing identity review.",
            "It does not unlock public benchmark; live SF bounded probes decide runtime promotion confidence.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF skill inventory cleanup and canonical bucket reports.")
    parser.add_argument("--root", action="append", default=[], help="Skill root to scan. Defaults to Nexus SF roots.")
    parser.add_argument("--inventory-output", default=str(DEFAULT_INVENTORY))
    parser.add_argument("--dedup-output", default=str(DEFAULT_DEDUP))
    parser.add_argument("--buckets-output", default=str(DEFAULT_BUCKETS))
    parser.add_argument("--recheck-output", default=str(DEFAULT_RECHECK))
    parser.add_argument("--final-pairing-output", default=str(DEFAULT_FINAL_PAIRING))
    parser.add_argument("--patch-plan", default=str(DEFAULT_PATCH_PLAN))
    parser.add_argument("--promotion-review", default=str(DEFAULT_PROMOTION_REVIEW))
    args = parser.parse_args(argv)

    roots = tuple(args.root) if args.root else DEFAULT_SKILL_ROOTS
    inventory = build_full_skill_inventory(roots)
    dedup = build_identity_dedup_report(inventory)
    buckets = build_canonical_capability_buckets(inventory, dedup)
    recheck = build_pairing_identity_recheck(
        patch_plan_path=args.patch_plan,
        promotion_review_path=args.promotion_review,
        inventory=inventory,
        dedup_report=dedup,
    )
    final_pairing = _final_pairing_report(inventory, dedup, buckets, recheck)

    _write(Path(args.inventory_output), inventory)
    _write(Path(args.dedup_output), dedup)
    _write(Path(args.buckets_output), buckets)
    _write(Path(args.recheck_output), recheck)
    _write(Path(args.final_pairing_output), final_pairing)

    print(
        json.dumps(
            {
                "status": "PASS" if recheck["status"] == "PASS" else "BLOCKED",
                "skill_file_count": inventory["summary"]["skill_file_count"],
                "unique_skill_id_count": inventory["summary"]["unique_skill_id_count"],
                "duplicate_skill_id_count": inventory["summary"]["duplicate_skill_id_count"],
                "safe_delete_candidate_count": dedup["summary"]["safe_delete_candidate_count"],
                "manual_review_required_count": dedup["summary"]["manual_review_required_count"],
                "canonical_skill_count": buckets["summary"]["canonical_skill_count"],
                "capability_bucket_count": buckets["summary"]["capability_bucket_count"],
                "pairing_recheck_status": recheck["status"],
                "pairing_blocker_count": recheck["summary"]["blocker_count"],
                "sf_clean_closed": final_pairing["summary"]["sf_clean_closed"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if recheck["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
