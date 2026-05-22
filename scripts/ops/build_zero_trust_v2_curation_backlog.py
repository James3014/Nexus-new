#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_RUNTIME_APPLY_DECISION = Path("docs/reports/NEXUS_SF_FINAL_RUNTIME_APPLY_DECISION_2026-05-21.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_CURATION_BACKLOG_2026-05-21.json")
SECURITY_CAPABILITY_MARKERS = (
    "claim",
    "file_lock",
    "governance",
    "policy",
    "sandbox",
    "security",
    "xray",
)
CORE_ENGINEERING_CAPABILITIES = {
    "codeintel",
    "direct_master_loop",
    "repair_loop",
    "research_control_plane",
    "sandbox_replay",
    "swarm_multi_agent",
}


def _risk_flags_for_item(item: Mapping[str, Any], warnings_by_pair: Mapping[tuple[str, str], list[Mapping[str, Any]]]) -> list[str]:
    flags: list[str] = []
    capability = str(item.get("capability_id") or "")
    skill_id = str(item.get("skill_id") or "")
    source_status = str(item.get("source_status") or "")
    if item.get("requires_curation") is True:
        flags.append("requires_curation")
    if source_status == "external_reference_candidate":
        flags.append("external_reference_candidate")
    if warnings_by_pair.get((capability, skill_id)):
        flags.append("cross_capability_reject_conflict")
    if item.get("v2_promotion_eligible") is not True:
        flags.append("v2_not_promotion_eligible")
    return sorted(set(flags))


def _priority_for_capability(capability: str, risk_flags: list[str]) -> str:
    if any(marker in capability for marker in SECURITY_CAPABILITY_MARKERS):
        return "P0"
    if "cross_capability_reject_conflict" in risk_flags:
        return "P0"
    if capability in CORE_ENGINEERING_CAPABILITIES:
        return "P1"
    return "P2"


def _required_next_steps(risk_flags: list[str]) -> list[str]:
    steps = ["source_review", "xray_static_scan", "v2_replay", "sandbox_shadow"]
    if "cross_capability_reject_conflict" in risk_flags:
        steps.insert(1, "reject_conflict_review")
    return steps


def _warnings_by_pair(runtime_apply_decision: Mapping[str, Any]) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    warnings: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for warning in runtime_apply_decision.get("reject_conflict_warnings", []) or []:
        if not isinstance(warning, Mapping):
            continue
        capability = str(warning.get("capability_id") or "")
        skill_id = str(warning.get("skill_id") or "")
        if capability and skill_id:
            warnings.setdefault((capability, skill_id), []).append(warning)
    return warnings


def _rows_for_backlog(runtime_apply_decision: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    rows.extend(item for item in runtime_apply_decision.get("applied_primary", []) or [] if isinstance(item, Mapping))
    for raw in runtime_apply_decision.get("kept_primary", []) or []:
        if not isinstance(raw, Mapping):
            continue
        rows.append(
            {
                **raw,
                "previous_skill_id": str(raw.get("skill_id") or ""),
                "source_status": str(raw.get("source_status") or "current_runtime_primary"),
                "runtime_review_scope": str(raw.get("runtime_review_scope") or "kept_primary_requires_v2_coverage"),
                "security_contract_version": str(raw.get("security_contract_version") or "v2_coverage_required"),
                "promotion_credit_source": str(raw.get("promotion_credit_source") or "none"),
                "v1_evidence_count": int(raw.get("v1_evidence_count") or 0),
                "v2_evidence_count": int(raw.get("v2_evidence_count") or 0),
                "v2_trust_mismatch_count": int(raw.get("v2_trust_mismatch_count") or 0),
                "requires_sandbox_attestation": raw.get("requires_sandbox_attestation") is True,
                "sandbox_attestation_status": str(raw.get("sandbox_attestation_status") or "missing_for_v2_coverage"),
                "v2_promotion_eligible": raw.get("v2_promotion_eligible") is True,
                "requires_curation": raw.get("requires_curation") is True,
                "coverage_lane": "kept_primary_v2_coverage",
            }
        )
    return rows


def build_zero_trust_v2_curation_backlog(*, runtime_apply_decision: Mapping[str, Any]) -> dict[str, Any]:
    summary = runtime_apply_decision.get("summary") if isinstance(runtime_apply_decision.get("summary"), Mapping) else {}
    warnings_by_pair = _warnings_by_pair(runtime_apply_decision)
    items: list[dict[str, Any]] = []
    for raw in _rows_for_backlog(runtime_apply_decision):
        capability = str(raw.get("capability_id") or "")
        skill_id = str(raw.get("skill_id") or "")
        if not capability or not skill_id:
            continue
        risk_flags = _risk_flags_for_item(raw, warnings_by_pair)
        item = {
            "capability_id": capability,
            "skill_id": skill_id,
            "previous_skill_id": str(raw.get("previous_skill_id") or ""),
            "source_status": str(raw.get("source_status") or ""),
            "current_runtime_scope": str(raw.get("runtime_review_scope") or ""),
            "security_contract_version": str(raw.get("security_contract_version") or ""),
            "promotion_credit_source": str(raw.get("promotion_credit_source") or ""),
            "v1_evidence_count": int(raw.get("v1_evidence_count") or 0),
            "v2_evidence_count": int(raw.get("v2_evidence_count") or 0),
            "v2_trust_mismatch_count": int(raw.get("v2_trust_mismatch_count") or 0),
            "requires_sandbox_attestation": raw.get("requires_sandbox_attestation") is True,
            "sandbox_attestation_status": str(raw.get("sandbox_attestation_status") or ""),
            "v2_promotion_eligible": raw.get("v2_promotion_eligible") is True,
            "curation_status": "PENDING",
            "priority": _priority_for_capability(capability, risk_flags),
            "risk_flags": risk_flags,
            "reject_conflict_warnings": [dict(warning) for warning in warnings_by_pair.get((capability, skill_id), [])],
            "required_next_steps": _required_next_steps(risk_flags),
            "evidence_refs": list(raw.get("evidence_refs") or []),
            "receipt_path": str(raw.get("receipt_path") or ""),
            "decision": str(raw.get("decision") or ""),
            "coverage_lane": str(raw.get("coverage_lane") or "applied_replacement_v2_curation"),
        }
        items.append(item)
    items.sort(key=lambda item: (item["priority"], item["capability_id"], item["skill_id"]))
    priority_counts: dict[str, int] = {}
    for item in items:
        priority_counts[item["priority"]] = priority_counts.get(item["priority"], 0) + 1
    return {
        "schema": "nexus.zero_trust_v2.curation_backlog.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "source_runtime_apply_decision": str(DEFAULT_RUNTIME_APPLY_DECISION),
        "summary": {
            "candidate_count": len(items),
            "applied_replacement_count": int(summary.get("applied_replacement_count") or 0),
            "kept_primary_count": int(summary.get("kept_primary_count") or 0),
            "kept_primary_v2_coverage_count": sum(
                1 for item in items if item["coverage_lane"] == "kept_primary_v2_coverage"
            ),
            "requires_curation_count": sum(1 for item in items if "requires_curation" in item["risk_flags"]),
            "external_reference_candidate_count": sum(
                1 for item in items if item["source_status"] == "external_reference_candidate"
            ),
            "cross_capability_reject_warning_count": sum(
                1 for item in items if "cross_capability_reject_conflict" in item["risk_flags"]
            ),
            "v2_ready_count": sum(1 for item in items if item["v2_promotion_eligible"] is True),
            "v1_evidence_count": sum(int(item["v1_evidence_count"]) for item in items),
            "v2_evidence_count": sum(int(item["v2_evidence_count"]) for item in items),
            "promotion_credit_source": "none",
            "runtime_update_allowed": bool(summary.get("runtime_update_allowed")),
            "public_benchmark_allowed": bool(summary.get("public_benchmark_allowed")),
            "priority_counts": dict(sorted(priority_counts.items())),
        },
        "items": items,
        "claim_boundary": [
            "This backlog is diagnostic and curation-only.",
            "It does not mutate runtime overlay or grant V2 promotion credit.",
            "V2 promotion requires replay, signed receipts, sandbox attestation, clean-slate evidence, and manual apply.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 curation backlog from runtime apply decision.")
    parser.add_argument("--runtime-apply-decision", default=str(DEFAULT_RUNTIME_APPLY_DECISION))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    result = build_zero_trust_v2_curation_backlog(runtime_apply_decision=read_json(args.runtime_apply_decision))
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": args.output,
                **result["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
