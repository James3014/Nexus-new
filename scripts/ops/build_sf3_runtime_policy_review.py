#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.sf2_bounded_probe import (
    build_sf3_candidate_only_hardening_plan,
    build_sf3_candidate_metadata_overlay,
    build_sf3_evidence_based_approval_artifact,
    build_sf3_manual_runtime_policy_review,
    build_sf3_manual_approval_packet,
    build_sf3_manual_approval_validation,
    build_sf3_post_review_gate,
    build_sf3_runtime_policy_apply_gate,
    build_sf3_runtime_policy_approval_draft,
    build_sf3_runtime_policy_patch_plan,
)


DEFAULT_RUNTIME_GATE = Path("docs/reports/NEXUS_SF3_RUNTIME_REVIEW_GATE_2026-05-18.json")
DEFAULT_BEST = Path("docs/reports/NEXUS_SF3_BEST_CANDIDATE_SEARCH_2026-05-18.json")
DEFAULT_RESCUE = Path("docs/reports/NEXUS_SF3_METADATA_BIAS_RESCUE_2026-05-18.json")
DEFAULT_MANUAL_REVIEW = Path("docs/reports/NEXUS_SF3_MANUAL_RUNTIME_POLICY_REVIEW_2026-05-18.json")
DEFAULT_HARDENING = Path("docs/reports/NEXUS_SF3_CANDIDATE_ONLY_HARDENING_PLAN_2026-05-18.json")
DEFAULT_POST_REVIEW = Path("docs/reports/NEXUS_SF3_POST_REVIEW_GATE_2026-05-18.json")
DEFAULT_METADATA_OVERLAY = Path("docs/reports/NEXUS_SF3_CANDIDATE_METADATA_OVERLAY_2026-05-18.json")
DEFAULT_APPROVAL_DRAFT = Path("docs/reports/NEXUS_SF3_RUNTIME_POLICY_APPROVAL_DRAFT_2026-05-18.json")
DEFAULT_APPLY_GATE = Path("docs/reports/NEXUS_SF3_RUNTIME_POLICY_APPLY_GATE_2026-05-18.json")
DEFAULT_APPROVAL_PACKET = Path("docs/reports/NEXUS_SF3_MANUAL_APPROVAL_PACKET_2026-05-18.json")
DEFAULT_APPROVAL_TEMPLATE = Path("docs/reports/NEXUS_SF3_MANUAL_APPROVAL_TEMPLATE_2026-05-18.json")
DEFAULT_APPROVAL_VALIDATION = Path("docs/reports/NEXUS_SF3_MANUAL_APPROVAL_VALIDATION_2026-05-18.json")
DEFAULT_PATCH_PLAN = Path("docs/reports/NEXUS_SF3_RUNTIME_POLICY_PATCH_PLAN_2026-05-18.json")
DEFAULT_EVIDENCE_APPROVAL = Path("docs/reports/NEXUS_SF3_EVIDENCE_BASED_APPROVAL_ARTIFACT_2026-05-18.json")


def _read(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _approval_template(approval_packet: dict) -> dict:
    return {
        "schema": "nexus.sf3_manual_approval_artifact.v1",
        "status": "PENDING",
        "approval_items": [
            {
                "capability_id": item["capability_id"],
                "skill_id": item["skill_id"],
                "decision": "PENDING",
                "allowed_review_decisions": item.get("allowed_review_decisions", []),
                "default_review_decision": item.get("default_review_decision", ""),
                "reviewer_notes": "",
            }
            for item in approval_packet.get("packet_items", []) or []
        ],
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "instructions": [
            "Replace each decision with APPROVE_FOR_RUNTIME_REVIEW, APPROVE_AS_ALTERNATE, or REJECT.",
            "Candidate-only items cannot be approved for runtime review until curated separately.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF3 runtime policy review and hardening gates.")
    parser.add_argument("--runtime-review-gate", default=str(DEFAULT_RUNTIME_GATE))
    parser.add_argument("--best-candidate-search", default=str(DEFAULT_BEST))
    parser.add_argument("--metadata-bias-rescue", default=str(DEFAULT_RESCUE))
    parser.add_argument("--manual-review-output", default=str(DEFAULT_MANUAL_REVIEW))
    parser.add_argument("--hardening-plan-output", default=str(DEFAULT_HARDENING))
    parser.add_argument("--post-review-gate-output", default=str(DEFAULT_POST_REVIEW))
    parser.add_argument("--metadata-overlay-output", default=str(DEFAULT_METADATA_OVERLAY))
    parser.add_argument("--approval-draft-output", default=str(DEFAULT_APPROVAL_DRAFT))
    parser.add_argument("--apply-gate-output", default=str(DEFAULT_APPLY_GATE))
    parser.add_argument("--approval-packet-output", default=str(DEFAULT_APPROVAL_PACKET))
    parser.add_argument("--approval-template-output", default=str(DEFAULT_APPROVAL_TEMPLATE))
    parser.add_argument("--approval-artifact", default="")
    parser.add_argument("--approval-validation-output", default=str(DEFAULT_APPROVAL_VALIDATION))
    parser.add_argument("--patch-plan-output", default=str(DEFAULT_PATCH_PLAN))
    parser.add_argument("--evidence-approval-output", default=str(DEFAULT_EVIDENCE_APPROVAL))
    parser.add_argument("--max-files-per-batch", type=int, default=15)
    args = parser.parse_args(argv)

    runtime_gate = _read(args.runtime_review_gate)
    best = _read(args.best_candidate_search)
    rescue = _read(args.metadata_bias_rescue)

    manual_review = build_sf3_manual_runtime_policy_review(runtime_gate, best)
    hardening_plan = build_sf3_candidate_only_hardening_plan(
        rescue,
        max_files_per_batch=args.max_files_per_batch,
    )
    post_review_gate = build_sf3_post_review_gate(runtime_gate, manual_review, hardening_plan)
    metadata_overlay = build_sf3_candidate_metadata_overlay(hardening_plan)
    approval_draft = build_sf3_runtime_policy_approval_draft(manual_review, metadata_overlay)
    approval_packet = build_sf3_manual_approval_packet(approval_draft, metadata_overlay)
    evidence_approval = build_sf3_evidence_based_approval_artifact(approval_packet)
    approval_template = _approval_template(approval_packet)
    approval_artifact = _read(args.approval_artifact) if args.approval_artifact else evidence_approval
    approval_validation = build_sf3_manual_approval_validation(approval_packet, approval_artifact)
    patch_plan = build_sf3_runtime_policy_patch_plan(approval_validation)
    apply_gate = build_sf3_runtime_policy_apply_gate(patch_plan)

    _write(Path(args.manual_review_output), manual_review)
    _write(Path(args.hardening_plan_output), hardening_plan)
    _write(Path(args.post_review_gate_output), post_review_gate)
    _write(Path(args.metadata_overlay_output), metadata_overlay)
    _write(Path(args.approval_draft_output), approval_draft)
    _write(Path(args.apply_gate_output), apply_gate)
    _write(Path(args.approval_packet_output), approval_packet)
    _write(Path(args.evidence_approval_output), evidence_approval)
    _write(Path(args.approval_template_output), approval_template)
    _write(Path(args.approval_validation_output), approval_validation)
    _write(Path(args.patch_plan_output), patch_plan)

    print(
        json.dumps(
            {
                "status": post_review_gate["status"],
                "sf_closed_loop_complete": post_review_gate["summary"]["sf_closed_loop_complete"],
                "sf_state": post_review_gate["summary"]["sf_state"],
                "manual_review_item_count": manual_review["summary"]["review_item_count"],
                "hardening_batch_count": hardening_plan["summary"]["batch_count"],
                "metadata_overlay_count": metadata_overlay["summary"]["overlay_count"],
                "pending_manual_approval_count": approval_draft["summary"]["pending_manual_approval_count"],
                "runtime_policy_apply_gate": apply_gate["status"],
                "approval_packet_item_count": approval_packet["summary"]["packet_item_count"],
                "evidence_runtime_review_decision_count": evidence_approval["summary"]["runtime_review_decision_count"],
                "evidence_alternate_decision_count": evidence_approval["summary"]["alternate_decision_count"],
                "approval_validation": approval_validation["status"],
                "patch_plan": patch_plan["status"],
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if post_review_gate["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
