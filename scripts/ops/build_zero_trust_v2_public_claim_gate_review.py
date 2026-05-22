#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


DEFAULT_BEHAVIOR_EVIDENCE = Path("docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_EVIDENCE_2026-05-21.json")
DEFAULT_RUNTIME_STATUS = Path("docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_SKILL_STATUS_MERGED_2026-05-22.json")
DEFAULT_UNIFIED_MAINLINE = Path("docs/reports/NEXUS_ZERO_TRUST_V2_UNIFIED_MAINLINE_2026-05-22.json")
DEFAULT_EVIDENCE_ROOT = Path(".nexus/reports/zero_trust_v2_behavior")
DEFAULT_FINAL_EVIDENCE_BUNDLE = Path(
    ".nexus/reports/bench_gemini3flash_public_cost_opt_12x3_v2_premodel_strict/evidence_bundle.json"
)
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_ZERO_TRUST_V2_PUBLIC_CLAIM_GATE_REVIEW_2026-05-22.json")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any) -> bool:
    return bool(value)


def _gate_failures(bundle: Mapping[str, Any]) -> list[str]:
    gate = _as_dict(bundle.get("public_claim_gate"))
    return [str(item) for item in _as_list(gate.get("failures")) if str(item)]


def _gate_checks(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(_as_dict(bundle.get("public_claim_gate")).get("checks"))


def _top_level_gate_verdict(bundle: Mapping[str, Any], gate_name: str) -> str:
    gate = _as_dict(bundle.get(gate_name))
    return str(gate.get("verdict") or gate.get("status") or "")


def _public_lane_reasons(bundle: Mapping[str, Any]) -> list[str]:
    contract = _as_dict(bundle.get("public_lane_contract"))
    return [str(item) for item in _as_list(contract.get("non_public_reasons")) if str(item)]


def _scan_bundle(path: Path) -> dict[str, Any]:
    try:
        bundle = _read_json(path)
    except Exception as exc:
        return {
            "path": path.as_posix(),
            "parse_status": "FAIL",
            "parse_error": exc.__class__.__name__,
            "public_claim_gate_verdict": "MISSING",
            "public_claim_gate_failures": ["evidence_bundle_parse_failed"],
        }
    gate = _as_dict(bundle.get("public_claim_gate"))
    checks = _gate_checks(bundle)
    failures = _gate_failures(bundle)
    return {
        "path": path.as_posix(),
        "parse_status": "PASS",
        "schema": str(bundle.get("schema") or ""),
        "public_claim_gate_verdict": str(gate.get("verdict") or gate.get("status") or "MISSING"),
        "public_verified_delivery_claim_gate_verdict": _top_level_gate_verdict(
            bundle, "public_verified_delivery_claim_gate"
        ),
        "public_cost_claim_gate_verdict": _top_level_gate_verdict(bundle, "public_cost_claim_gate"),
        "public_cost_efficiency_claim_gate_verdict": _top_level_gate_verdict(
            bundle, "public_cost_efficiency_claim_gate"
        ),
        "x3_promotion_gate_verdict": _top_level_gate_verdict(bundle, "x3_promotion_gate"),
        "external_provider_public_claim_allowed": bool(
            _as_dict(bundle.get("external_provider_claim_boundary_contract")).get("public_claim_allowed", True)
        ),
        "public_promotion_readiness_status": str(
            _as_dict(bundle.get("public_promotion_readiness_contract")).get("status") or ""
        ),
        "public_claim_gate_failures": failures,
        "public_lane_non_public_reasons": _public_lane_reasons(bundle),
        "same_model": _as_bool(checks.get("same_model")),
        "same_task_trials": _as_bool(checks.get("same_task_trials")),
        "hidden_verifier_mode": _as_bool(checks.get("hidden_verifier_mode")),
        "run_eligibility_complete": _as_bool(checks.get("run_eligibility_complete")),
        "valid_comparison_ready": _as_bool(checks.get("valid_comparison_ready")),
        "eligible_with_nexus": int(checks.get("eligible_with_nexus") or 0),
        "eligible_without_nexus": int(checks.get("eligible_without_nexus") or 0),
        "infra_valid_pair_count": int(checks.get("infra_valid_pair_count") or 0),
        "token_measured_rate_with": float(checks.get("token_measured_rate_with") or 0.0),
        "token_measured_rate_without": float(checks.get("token_measured_rate_without") or 0.0),
        "provider_token_measured_rate_with": float(checks.get("provider_token_measured_rate_with") or 0.0),
        "provider_token_measured_rate_without": float(checks.get("provider_token_measured_rate_without") or 0.0),
        "raw_file_hashes_present": _as_bool(checks.get("raw_file_hashes_present")),
        "runner_command_present": _as_bool(checks.get("runner_command_present")),
        "manifest_hash_present": _as_bool(checks.get("manifest_hash_present")),
        "nexus_wearing_valid_rate": float(checks.get("nexus_wearing_valid_rate") or 0.0),
    }


def _scan_evidence_bundles(evidence_root: Path) -> list[dict[str, Any]]:
    if not evidence_root.exists():
        return []
    return [_scan_bundle(path) for path in sorted(evidence_root.glob("**/evidence_bundle.json"))]


def _scan_selected_evidence(*, evidence_root: Path, evidence_bundle: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if evidence_bundle is not None:
        return [_scan_bundle(evidence_bundle)], {
            "mode": "single_final_evidence_bundle",
            "evidence_bundle": evidence_bundle.as_posix(),
            "evidence_root": "",
        }
    return _scan_evidence_bundles(evidence_root), {
        "mode": "evidence_root_scan",
        "evidence_bundle": "",
        "evidence_root": evidence_root.as_posix(),
    }


def _blockers(
    *,
    behavior_evidence: Mapping[str, Any],
    runtime_status: Mapping[str, Any],
    unified_mainline: Mapping[str, Any],
    bundle_rows: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    behavior_summary = _as_dict(behavior_evidence.get("summary"))
    runtime_summary = _as_dict(runtime_status.get("summary"))
    unified_summary = _as_dict(unified_mainline.get("summary"))

    if behavior_evidence.get("status") != "PASS":
        blockers.append("behavior_evidence_not_pass")
    if int(behavior_summary.get("v2_behavior_ready_count") or 0) < 34:
        blockers.append("v2_behavior_ready_count_lt_34")
    if runtime_status.get("status") != "PASS" or runtime_summary.get("runtime_update_allowed") is not True:
        blockers.append("runtime_default_not_applied")
    if int(runtime_summary.get("v2_default_applied_count") or 0) < 34:
        blockers.append("v2_default_applied_count_lt_34")
    if unified_mainline.get("status") != "PASS" or unified_summary.get("v2_unification_complete") is not True:
        blockers.append("v2_unification_not_complete")

    if not bundle_rows:
        blockers.append("zero_trust_v2_public_evidence_bundles_missing")
        return sorted(set(blockers))

    pass_rows = [row for row in bundle_rows if row["public_claim_gate_verdict"] == "PASS"]
    delivery_pass_rows = [row for row in bundle_rows if row["public_verified_delivery_claim_gate_verdict"] == "PASS"]
    cost_pass_rows = [row for row in bundle_rows if row["public_cost_claim_gate_verdict"] == "PASS"]
    cost_efficiency_rows = [
        row for row in bundle_rows if row["public_cost_efficiency_claim_gate_verdict"] in {"PASS", "IMPROVED"}
    ]
    x3_pass_rows = [row for row in bundle_rows if row["x3_promotion_gate_verdict"] == "PASS"]
    valid_ready_rows = [row for row in bundle_rows if row["valid_comparison_ready"]]
    same_model_rows = [row for row in bundle_rows if row["same_model"]]
    paired_rows = [row for row in bundle_rows if int(row["infra_valid_pair_count"]) > 0]
    without_token_rows = [
        row
        for row in bundle_rows
        if row["token_measured_rate_without"] >= 1.0 and row["provider_token_measured_rate_without"] >= 1.0
    ]
    report_artifact_rows = [
        row
        for row in bundle_rows
        if row["raw_file_hashes_present"] and row["runner_command_present"] and row["manifest_hash_present"]
    ]

    if not pass_rows:
        blockers.append("no_public_claim_gate_pass")
    if not delivery_pass_rows:
        blockers.append("public_verified_delivery_claim_gate_not_pass")
    if not cost_pass_rows:
        blockers.append("public_cost_claim_gate_not_pass")
    if not cost_efficiency_rows:
        blockers.append("public_cost_efficiency_claim_gate_not_improved")
    if not x3_pass_rows:
        blockers.append("x3_promotion_gate_not_pass")
    if not valid_ready_rows:
        blockers.append("valid_comparison_ready_count_zero")
    if not same_model_rows:
        blockers.append("same_model_v2_vs_baseline_missing")
    if not paired_rows:
        blockers.append("infra_valid_pair_count_zero")
    if not without_token_rows:
        blockers.append("baseline_provider_token_cost_accounting_missing")
    if len(report_artifact_rows) < len(bundle_rows):
        blockers.append("some_bundles_missing_rerun_artifacts")
    if any(not row["external_provider_public_claim_allowed"] for row in bundle_rows):
        blockers.append("external_provider_public_claim_not_allowed")
    if any(row["public_promotion_readiness_status"] == "RETURN" for row in bundle_rows):
        blockers.append("public_promotion_readiness_return")

    failure_counts = Counter(
        failure for row in bundle_rows for failure in row.get("public_claim_gate_failures", [])
    )
    if failure_counts.get("non_public_shortcut:nexus_only", 0):
        blockers.append("nexus_only_shortcut_evidence_present")
    if failure_counts.get("single_arm_run", 0):
        blockers.append("single_arm_evidence_present")
    if failure_counts.get("task_trial_mismatch", 0):
        blockers.append("task_trial_mismatch_present")
    if failure_counts.get("model_mismatch", 0):
        blockers.append("model_mismatch_present")
    if failure_counts.get("without_provider_token_measured_below_threshold", 0):
        blockers.append("baseline_provider_token_measured_below_threshold")
    return sorted(set(blockers))


def build_zero_trust_v2_public_claim_gate_review(
    *,
    behavior_evidence: dict[str, Any],
    runtime_status: dict[str, Any],
    unified_mainline: dict[str, Any],
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    evidence_bundle: Path | None = None,
) -> dict[str, Any]:
    bundle_rows, evidence_selection = _scan_selected_evidence(evidence_root=evidence_root, evidence_bundle=evidence_bundle)
    blockers = _blockers(
        behavior_evidence=behavior_evidence,
        runtime_status=runtime_status,
        unified_mainline=unified_mainline,
        bundle_rows=bundle_rows,
    )
    status_counts = Counter(row["public_claim_gate_verdict"] for row in bundle_rows)
    failure_counts = Counter(failure for row in bundle_rows for failure in row.get("public_claim_gate_failures", []))
    summary = {
        "behavior_ready_count": int(_as_dict(behavior_evidence.get("summary")).get("v2_behavior_ready_count") or 0),
        "runtime_update_allowed": bool(_as_dict(runtime_status.get("summary")).get("runtime_update_allowed")),
        "v2_default_applied_count": int(_as_dict(runtime_status.get("summary")).get("v2_default_applied_count") or 0),
        "v2_unification_complete": bool(_as_dict(unified_mainline.get("summary")).get("v2_unification_complete")),
        "evidence_bundle_count": len(bundle_rows),
        "public_claim_gate_status_counts": dict(sorted(status_counts.items())),
        "public_claim_gate_pass_count": status_counts.get("PASS", 0),
        "public_verified_delivery_claim_gate_pass_count": sum(
            1 for row in bundle_rows if row["public_verified_delivery_claim_gate_verdict"] == "PASS"
        ),
        "public_cost_claim_gate_pass_count": sum(
            1 for row in bundle_rows if row["public_cost_claim_gate_verdict"] == "PASS"
        ),
        "public_cost_efficiency_claim_gate_improved_count": sum(
            1 for row in bundle_rows if row["public_cost_efficiency_claim_gate_verdict"] == "IMPROVED"
        ),
        "x3_promotion_gate_pass_count": sum(1 for row in bundle_rows if row["x3_promotion_gate_verdict"] == "PASS"),
        "valid_comparison_ready_count": sum(1 for row in bundle_rows if row["valid_comparison_ready"]),
        "same_model_count": sum(1 for row in bundle_rows if row["same_model"]),
        "infra_valid_pair_count_total": sum(int(row["infra_valid_pair_count"]) for row in bundle_rows),
        "baseline_provider_token_measured_complete_count": sum(
            1
            for row in bundle_rows
            if row["provider_token_measured_rate_without"] >= 1.0 and row["token_measured_rate_without"] >= 1.0
        ),
        "public_benchmark_allowed": not blockers,
    }
    allowed_claim = (
        "Nexus V2 hidden-verifier-backed deterministic local rescue profile improved verified delivery and "
        "cost efficiency on the frozen same-model public benchmark fixture."
    )
    disallowed_claim = (
        "Do not claim the same external model became cheaper or used fewer tokens for the same with-Nexus model work; "
        "with-Nexus rows in this profile bypass model calls after policy and verifier gates pass."
    )
    return {
        "schema": "nexus.zero_trust_v2.public_claim_gate_review.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_selection": evidence_selection,
        "summary": summary,
        "blockers": blockers,
        "failure_counts": dict(sorted(failure_counts.items())),
        "sample_blocked_bundles": [
            {
                "path": row["path"],
                "public_claim_gate_verdict": row["public_claim_gate_verdict"],
                "failures": row["public_claim_gate_failures"],
            }
            for row in bundle_rows
            if row["public_claim_gate_verdict"] != "PASS"
        ][:20],
        "next_actions": [
            "Use the selected final 12x3 evidence bundle for public wording, not the older Nexus-only behavior bundle root.",
            "Keep the cost-efficiency claim scoped to the explicit pre-model rescue profile.",
            "Preserve raw JSONL, evidence bundle, command, model name, manifest hash, and public report artifacts.",
            "Recompute this review whenever the selected final evidence bundle changes.",
        ],
        "claim_scope": {
            "allowed": allowed_claim,
            "not_allowed": disallowed_claim,
            "profile": "NEXUS_ALLOW_COST_EFFICIENCY_PRE_MODEL_RESCUE=1",
        },
        "claim_boundary": [
            "Internal Zero-Trust V2 runtime default completion does not imply public benchmark permission.",
            "Nexus-only, smoke-only, forced readiness, or single-arm evidence is diagnostic only.",
            allowed_claim,
            disallowed_claim,
            "This review is fail-closed and does not mutate runtime policy.",
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Zero-Trust V2 public claim gate review.")
    parser.add_argument("--behavior-evidence", type=Path, default=DEFAULT_BEHAVIOR_EVIDENCE)
    parser.add_argument("--runtime-status", type=Path, default=DEFAULT_RUNTIME_STATUS)
    parser.add_argument("--unified-mainline", type=Path, default=DEFAULT_UNIFIED_MAINLINE)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--evidence-bundle", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    result = build_zero_trust_v2_public_claim_gate_review(
        behavior_evidence=_read_json(args.behavior_evidence),
        runtime_status=_read_json(args.runtime_status),
        unified_mainline=_read_json(args.unified_mainline),
        evidence_root=args.evidence_root,
        evidence_bundle=args.evidence_bundle,
    )
    _write_json(args.output, result)
    print(json.dumps({"status": result["status"], "output": args.output.as_posix(), **result["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
