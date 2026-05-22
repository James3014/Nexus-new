#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json
from nexus.learning.zero_trust_v2_behavior import build_behavior_runner_command_spec, extract_behavior_receipt_from_path


DEFAULT_BACKLOG = Path("docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json")
DEFAULT_M45_M52 = Path("docs/reports/NEXUS_ZERO_TRUST_V2_M45_M52_COMPLETION_2026-05-22.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_EVIDENCE_2026-05-21.json")


def _behavior_evidence_from_m45(*, m45_m52: dict) -> dict:
    grouped: dict[tuple[str, str], dict] = {}
    for item in m45_m52.get("m45_behavior_run_results", []) or []:
        if not isinstance(item, dict):
            continue
        capability_id = str(item.get("capability_id") or "")
        skill_id = str(item.get("skill_id") or "")
        if not capability_id or not skill_id:
            continue
        key = (capability_id, skill_id)
        row = grouped.setdefault(
            key,
            {
                "capability_id": capability_id,
                "skill_id": skill_id,
                "priority": str(item.get("priority") or ""),
                "evidence_refs": [],
                "failed_security_contract_rules": set(),
                "v2_behavior_evidence_count": 0,
                "runtime_signed_receipt_verified_count": 0,
                "eligible_behavior_row_count": 0,
            },
        )
        if str(item.get("priority") or "") and not row["priority"]:
            row["priority"] = str(item.get("priority") or "")
        evidence_bundle = str(item.get("evidence_bundle") or "")
        if evidence_bundle:
            row["evidence_refs"].append(evidence_bundle)
        if item.get("clean_v2_receipt") is True:
            row["v2_behavior_evidence_count"] += 1
        if item.get("runtime_signed_receipt_verified") is True:
            row["runtime_signed_receipt_verified_count"] += 1
        row["eligible_behavior_row_count"] += int(item.get("eligible_behavior_rows") or 0)
        for blocker in item.get("blockers", []) or []:
            if blocker:
                row["failed_security_contract_rules"].add(str(blocker))

    candidates = []
    for item in sorted(grouped.values(), key=lambda row: (row["priority"], row["capability_id"], row["skill_id"])):
        failed_rules = sorted(item["failed_security_contract_rules"])
        status = "PASS" if item["v2_behavior_evidence_count"] >= 3 and not failed_rules else "BLOCKED"
        candidates.append(
            {
                "capability_id": item["capability_id"],
                "skill_id": item["skill_id"],
                "priority": item["priority"],
                "historical_behavior_receipt_status": "NOT_USED_FOR_V2_PROMOTION",
                "historical_behavior_receipt_count": 0,
                "v2_behavior_evidence_count": item["v2_behavior_evidence_count"],
                "runtime_signed_receipt_verified_count": item["runtime_signed_receipt_verified_count"],
                "eligible_behavior_row_count": item["eligible_behavior_row_count"],
                "status": status,
                "failed_security_contract_rules": failed_rules,
                "evidence_refs": item["evidence_refs"],
                "receipt_summaries": [],
            }
        )
    priority_counts = Counter(candidate["priority"] for candidate in candidates)
    return {
        "schema": "nexus.zero_trust_v2.behavior_evidence.v2",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_m45_m52": str(DEFAULT_M45_M52),
        "summary": {
            "candidate_count": len(candidates),
            "p0_count": priority_counts.get("P0", 0),
            "p1_count": priority_counts.get("P1", 0),
            "p2_count": priority_counts.get("P2", 0),
            "historical_behavior_pass_count": 0,
            "v2_behavior_ready_count": sum(1 for c in candidates if c["status"] == "PASS"),
            "v2_behavior_evidence_count": sum(int(c["v2_behavior_evidence_count"]) for c in candidates),
            "runtime_signed_receipt_verified_count": sum(
                int(c["runtime_signed_receipt_verified_count"]) for c in candidates
            ),
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "candidates": candidates,
        "claim_boundary": [
            "V2 behavior evidence is imported from runtime-signed M45/M46 behavior receipts.",
            "Historical behavior receipts remain diagnostic only and are not counted here.",
        ],
    }


def build_zero_trust_v2_behavior_evidence(*, backlog: dict, m45_m52: dict | None = None) -> dict:
    if m45_m52 is not None:
        return _behavior_evidence_from_m45(m45_m52=m45_m52)

    candidates = []
    for item in backlog.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        evidence_refs = [str(ref) for ref in item.get("evidence_refs", []) or [] if str(ref)]
        receipts = [extract_behavior_receipt_from_path(ref, skill_id=str(item.get("skill_id") or "")) for ref in evidence_refs]
        combined_rules = sorted({rule for receipt in receipts for rule in receipt.get("failed_security_contract_rules", [])})
        historical_pass = bool(receipts) and all(receipt.get("status") == "PASS" for receipt in receipts)
        blocked_reasons = list(combined_rules)
        if historical_pass:
            blocked_reasons.append("HISTORICAL_BEHAVIOR_ONLY_NOT_V2_PHYSICAL")
        if not receipts:
            blocked_reasons.append("NO_EVIDENCE_REFS")
        candidates.append(
            {
                "capability_id": str(item.get("capability_id") or ""),
                "skill_id": str(item.get("skill_id") or ""),
                "priority": str(item.get("priority") or ""),
                "behavior_command_spec": build_behavior_runner_command_spec(item),
                "historical_behavior_receipt_status": "PASS" if historical_pass else "BLOCKED",
                "historical_behavior_receipt_count": len(receipts),
                "v2_behavior_evidence_count": 0,
                "status": "BLOCKED",
                "failed_security_contract_rules": sorted(set(blocked_reasons)),
                "evidence_refs": evidence_refs,
                "receipt_summaries": receipts,
            }
        )
    priority_counts = Counter(candidate["priority"] for candidate in candidates)
    return {
        "schema": "nexus.zero_trust_v2.behavior_evidence.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_backlog": str(DEFAULT_BACKLOG),
        "summary": {
            "candidate_count": len(candidates),
            "p0_count": priority_counts.get("P0", 0),
            "p1_count": priority_counts.get("P1", 0),
            "p2_count": priority_counts.get("P2", 0),
            "historical_behavior_pass_count": sum(1 for c in candidates if c["historical_behavior_receipt_status"] == "PASS"),
            "v2_behavior_ready_count": 0,
            "runtime_mutation_allowed": False,
            "public_benchmark_allowed": False,
        },
        "candidates": candidates,
        "claim_boundary": [
            "Historical behavior receipts are diagnostic only.",
            "V2 behavior evidence requires physical sandbox execution plus selected/injected/used/evidence/gate/outcome receipts.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 behavior evidence report.")
    parser.add_argument("--backlog", default=str(DEFAULT_BACKLOG))
    parser.add_argument("--m45-m52", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_behavior_evidence(
        backlog=read_json(args.backlog),
        m45_m52=read_json(args.m45_m52) if args.m45_m52 else None,
    )
    write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output, **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
