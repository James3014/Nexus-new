from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class P7ArmorTraceRow:
    trace_version: str = "1.0"
    trace_id: str = ""
    p3_source_artifact: str = ""
    p6_source_artifact: str = ""
    p3_closed_status: str = "P6_CLOSED_HELDOUT_DRY_RUN_READY"
    p6_closed_status: str = "P6_CLOSED_HELDOUT_DRY_RUN_READY"
    p3_candidate_available: bool = True
    p3_candidate_is_synthetic: bool = True
    p3_real_provider_invoked: bool = False
    p3_network_invoked: bool = False
    p3_api_key_used: bool = False
    p6_advisory_present: bool = True
    p6_advisory_only: bool = True
    p6_recommendation: str = ""
    p2_apply_required: bool = True
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    p5_selection_metadata_required: bool = True
    patch_apply_invoked: bool = False
    runtime_behavior_changed: bool = False
    solved_claim: bool = False
    claim_eligible: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False
    invariant_passed: bool = True
    blocked_reasons: list[str] = field(default_factory=list)


SCENARIOS = [
    {"sid": "happy_path_synthetic_medium", "diff": "medium", "rec": "keep_full_committee"},
    {"sid": "happy_path_synthetic_hard", "diff": "hard", "rec": "keep_full_committee"},
    {"sid": "p6_fail_closed_advisory", "diff": "medium", "rec": "fail_closed"},
    {"sid": "p6_local_only_advisory", "diff": "medium", "rec": "local_only"},
    {"sid": "p6_cloud_disabled_advisory", "diff": "medium", "rec": "reduce_candidate_count"},
    {"sid": "no_p6_handoff", "diff": "medium", "rec": ""},
    {"sid": "missing_p3_candidate", "diff": "medium", "rec": "keep_full_committee", "no_candidate": True},
    {"sid": "unsafe_real_provider_invoked", "diff": "medium", "rec": "keep_full_committee", "prov": True},
    {"sid": "unsafe_network_invoked", "diff": "medium", "rec": "keep_full_committee", "net": True},
    {"sid": "unsafe_api_key_used", "diff": "medium", "rec": "keep_full_committee", "api": True},
    {"sid": "unsafe_patch_apply", "diff": "medium", "rec": "keep_full_committee", "patch": True},
    {"sid": "unsafe_runtime_change", "diff": "medium", "rec": "keep_full_committee", "runtime": True},
    {"sid": "unsafe_solved_claim", "diff": "medium", "rec": "keep_full_committee", "solved": True},
    {"sid": "unsafe_claim_eligible", "diff": "medium", "rec": "keep_full_committee", "ce": True},
    {"sid": "unsafe_public_claim", "diff": "medium", "rec": "keep_full_committee", "pub": True},
    {"sid": "unsafe_production_ready", "diff": "medium", "rec": "keep_full_committee", "prod": True},
    {"sid": "unsafe_p2_hash_missing", "diff": "medium", "rec": "keep_full_committee", "p2h": False},
    {"sid": "unsafe_p4_verifier_missing", "diff": "medium", "rec": "keep_full_committee", "p4v": False},
    {"sid": "unsafe_p4_claim_gate_missing", "diff": "medium", "rec": "keep_full_committee", "p4cg": False},
    {"sid": "unsafe_p6_not_advisory", "diff": "medium", "rec": "keep_full_committee", "p6adv": False},
    {"sid": "happy_path_synthetic_easy", "diff": "easy", "rec": "keep_full_committee"},
    {"sid": "p6_fail_closed_hard", "diff": "hard", "rec": "fail_closed"},
    {"sid": "p6_local_only_easy", "diff": "easy", "rec": "local_only"},
    {"sid": "p6_reduce_count_hard", "diff": "hard", "rec": "reduce_candidate_count"},
]


def build_armor_trace_rows() -> list[dict[str, Any]]:
    rows = []
    for i, sc in enumerate(SCENARIOS):
        sid = sc["sid"]
        prov = sc.get("prov", False)
        net = sc.get("net", False)
        api = sc.get("api", False)
        patch = sc.get("patch", False)
        runtime = sc.get("runtime", False)
        solved = sc.get("solved", False)
        ce = sc.get("ce", False)
        pub = sc.get("pub", False)
        prod = sc.get("prod", False)
        p2h = sc.get("p2h", True)
        p4v = sc.get("p4v", True)
        p4cg = sc.get("p4cg", True)
        p6adv = sc.get("p6adv", True)
        no_candidate = sc.get("no_candidate", False)

        blocked = []
        if prov: blocked.append("real_provider_invoked")
        if net: blocked.append("network_invoked")
        if api: blocked.append("api_key_used")
        if patch: blocked.append("patch_apply_invoked")
        if runtime: blocked.append("runtime_behavior_changed")
        if solved: blocked.append("solved_claim")
        if ce: blocked.append("claim_eligible")
        if pub: blocked.append("public_claim_allowed")
        if prod: blocked.append("production_ready")
        if not p2h: blocked.append("p2_hash_truth_missing")
        if not p4v: blocked.append("p4_verifier_missing")
        if not p4cg: blocked.append("p4_claim_gate_missing")
        if not p6adv: blocked.append("p6_not_advisory")

        row = P7ArmorTraceRow(
            trace_id=f"P7-{i+1:02d}",
            p6_recommendation=sc.get("rec", ""),
            p3_real_provider_invoked=prov,
            p3_network_invoked=net,
            p3_api_key_used=api,
            p6_advisory_present=bool(sc.get("rec")),
            p6_advisory_only=p6adv,
            p2_hash_truth_required=p2h,
            p2_anchor_truth_required=True,
            p4_verifier_required=p4v,
            p4_claim_gate_required=p4cg,
            p3_candidate_available=not no_candidate,
            patch_apply_invoked=patch,
            runtime_behavior_changed=runtime,
            solved_claim=solved,
            claim_eligible=ce,
            public_claim_allowed=pub,
            production_ready=prod,
            invariant_passed=len(blocked) == 0,
            blocked_reasons=blocked,
        )
        rows.append({
            "trace_version": row.trace_version, "trace_id": row.trace_id,
            "p3_source_artifact": row.p3_source_artifact, "p6_source_artifact": row.p6_source_artifact,
            "p3_closed_status": row.p3_closed_status, "p6_closed_status": row.p6_closed_status,
            "p3_candidate_available": row.p3_candidate_available,
            "p3_candidate_is_synthetic": row.p3_candidate_is_synthetic,
            "p3_real_provider_invoked": row.p3_real_provider_invoked,
            "p3_network_invoked": row.p3_network_invoked, "p3_api_key_used": row.p3_api_key_used,
            "p6_advisory_present": row.p6_advisory_present, "p6_advisory_only": row.p6_advisory_only,
            "p6_recommendation": row.p6_recommendation,
            "p2_apply_required": row.p2_apply_required,
            "p2_hash_truth_required": row.p2_hash_truth_required,
            "p2_anchor_truth_required": row.p2_anchor_truth_required,
            "p4_verifier_required": row.p4_verifier_required,
            "p4_claim_gate_required": row.p4_claim_gate_required,
            "p5_selection_metadata_required": row.p5_selection_metadata_required,
            "patch_apply_invoked": row.patch_apply_invoked,
            "runtime_behavior_changed": row.runtime_behavior_changed,
            "solved_claim": row.solved_claim, "claim_eligible": row.claim_eligible,
            "public_claim_allowed": row.public_claim_allowed,
            "production_ready": row.production_ready,
            "invariant_passed": row.invariant_passed,
            "blocked_reasons": row.blocked_reasons,
        })
    return rows
