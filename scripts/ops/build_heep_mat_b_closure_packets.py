#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_FINAL_DECISIONS = Path("docs/reports/NEXUS_HEEP_MAT_B_FINAL_SKILL_DECISIONS_2026-05-20.json")
DEFAULT_RUNTIME_PACKET = Path("docs/reports/NEXUS_HEEP_RUNTIME_APPLY_REVIEW_PACKET_2026-05-20.json")
DEFAULT_REPLAY_ROOT = Path(".nexus/reports/heep_flash_nexus_mat_b_executor_trio_replay_2026-05-20")
DEFAULT_REPLAY_STATUS = Path("docs/reports/NEXUS_HEEP_MAT_B_EXECUTOR_TRIO_REPLAY_STATUS_2026-05-20.json")
DEFAULT_ROLLUP = Path("docs/reports/NEXUS_HEEP_MAT_B_ROLLUP_V2_2026-05-20.json")
DEFAULT_MODE_GATE = Path("docs/reports/NEXUS_HEEP_MODE_MAP_UPDATE_GATE_V2_2026-05-20.json")
DEFAULT_RUNTIME_REVIEW = Path("docs/reports/NEXUS_HEEP_RUNTIME_APPLY_REVIEW_PACKET_V2_2026-05-20.json")
DEFAULT_PUBLIC_GATE = Path("docs/reports/NEXUS_HEEP_PUBLIC_BENCHMARK_READINESS_GATE_2026-05-20.json")
DEFAULT_TASKCARD_STATUS = Path("docs/reports/NEXUS_HEEP_TASKCARD_STATUS_R1_R6_2026-05-20.json")
DEFAULT_BLOCKER_RCA = Path("docs/reports/NEXUS_HEEP_PROVIDER_RECEIPT_BLOCKER_RCA_2026-05-20.json")


def _safe_read(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def _first_failed_row(replay_root: Path) -> tuple[Path | None, dict[str, Any]]:
    rows = sorted(replay_root.glob("**/*.row.json"))
    for path in rows:
        row = read_json(path)
        if str(row.get("status") or "") != "PASSED":
            return path, row
    return (rows[0], read_json(rows[0])) if rows else (None, {})


def _infer_capability(row: Mapping[str, Any], row_path: Path | None) -> str:
    capability = str(row.get("capability") or "")
    if capability:
        return capability
    coverage = row.get("expected_capability_receipt_coverage")
    if isinstance(coverage, Mapping):
        missing = [str(item) for item in coverage.get("missing", []) if str(item)]
        if missing:
            return missing[0]
    if row_path is not None:
        for part in row_path.parts:
            if part.startswith("heep_"):
                return part.removeprefix("heep_").split("_heep-mat-b-", 1)[0]
    return ""


def build_executor_trio_replay_status(*, replay_root: Path = DEFAULT_REPLAY_ROOT) -> dict[str, Any]:
    summary = _safe_read(replay_root / "live_summary.json") or _safe_read(replay_root / "checkpoint_summary.json")
    failed_path, failed_row = _first_failed_row(replay_root)
    missing_expected = (
        failed_row.get("expected_capability_receipt_coverage", {}).get("missing", [])
        if isinstance(failed_row.get("expected_capability_receipt_coverage"), Mapping)
        else []
    )
    blocker_reasons = []
    if failed_row.get("token_data_contract_status") == "DATA_CONTRACT_VIOLATION":
        blocker_reasons.append(str(failed_row.get("token_data_contract_reason") or "token_data_contract_violation"))
    if failed_row.get("skill_mount_contract_status") == "RETURN":
        blocker_reasons.append("skill_mount_contract_return")
    if missing_expected:
        blocker_reasons.append("missing_expected_capability_receipts:" + ",".join(map(str, missing_expected)))
    status = "PASS" if summary.get("status") == "PASS" else "BLOCKED"
    return {
        "schema": "nexus.heep_mat_b_executor_trio_replay_status.v1",
        "status": status,
        "summary": {
            "planned_rows": int(summary.get("summary", {}).get("planned_rows", summary.get("planned_rows", 0)) or 0),
            "completed_rows": int(summary.get("summary", {}).get("completed_rows", summary.get("completed_rows", 0)) or 0),
            "pass_count": int(summary.get("summary", {}).get("pass_count", summary.get("pass_count", 0)) or 0),
            "return_count": int(summary.get("summary", {}).get("return_count", summary.get("return_count", 0)) or 0),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "first_blocker": {
            "row_path": str(failed_path or ""),
            "row_id": str(failed_row.get("row_id") or ""),
            "capability": _infer_capability(failed_row, failed_path),
            "status": str(failed_row.get("status") or ""),
            "semantic_status": str(failed_row.get("semantic_status") or ""),
            "skill_mount_contract_status": str(failed_row.get("skill_mount_contract_status") or ""),
            "token_data_contract_status": str(failed_row.get("token_data_contract_status") or ""),
            "token_data_contract_reason": str(failed_row.get("token_data_contract_reason") or ""),
            "receipt_data_contract_status": str(failed_row.get("receipt_data_contract_status") or ""),
            "receipt_data_contract_reason": str(failed_row.get("receipt_data_contract_reason") or ""),
            "infra_invalid_reason": str(failed_row.get("infra_invalid_reason") or ""),
            "gateway_error_category": str(failed_row.get("gateway_error_category") or ""),
            "provider_token_measured": bool(failed_row.get("provider_token_measured")),
            "expected_capability_missing": list(missing_expected),
            "blocker_reasons": blocker_reasons,
        },
        "lesson": (
            "Executor route smoke can prove route-oracle coverage, but MAT-B skill comparison still needs "
            "skill-specific runtime receipts and measured provider token truth before runtime/public gates consume it."
        ),
        "claim_boundary": [
            "This is an internal HEEP MAT-B replay status artifact.",
            "A BLOCKED status cannot update runtime defaults or public benchmark claims.",
        ],
    }


def _decisions_by_type(final_decisions: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    decisions = [item for item in final_decisions.get("decisions", []) if isinstance(item, Mapping)]
    multi = [item for item in decisions if item.get("decision") == "USE_MULTI_SKILL"]
    fallback = [item for item in decisions if item.get("decision") == "USE_SINGLE_PRIMARY_FALLBACK"]
    return multi, fallback


def build_rollup_v2(
    *,
    final_decisions: Mapping[str, Any],
    replay_status: Mapping[str, Any],
    runtime_packet: Mapping[str, Any],
) -> dict[str, Any]:
    multi, fallback = _decisions_by_type(final_decisions)
    return {
        "schema": "nexus.heep_mat_b_rollup_v2.v1",
        "status": "PASS",
        "summary": {
            "capability_count": len(final_decisions.get("decisions", []) or []),
            "internal_multi_skill_selection_count": len(multi),
            "single_primary_fallback_count": len(fallback),
            "ready_for_runtime_apply_review_count": int(
                runtime_packet.get("summary", {}).get("ready_for_runtime_apply_review_count", 0) or 0
            ),
            "executor_trio_replay_status": str(replay_status.get("status") or ""),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "decisions": final_decisions.get("decisions", []),
        "blocking_gates": [
            "provider-clean same-window replay with measured provider tokens",
            "skill-specific MAT-B executor receipts for drone/nightshift/swarm_multi_agent",
            "runtime apply review packet must not consume blocked rows",
            "public benchmark remains separate and blocked",
        ],
        "claim_boundary": [
            "Rollup V2 finalizes internal usable skill decisions for the 13 previously blocked capabilities.",
            "It does not change runtime defaults.",
        ],
    }


def build_mode_gate_v2(*, final_decisions: Mapping[str, Any]) -> dict[str, Any]:
    rows = []
    for item in final_decisions.get("decisions", []) or []:
        if not isinstance(item, Mapping):
            continue
        decision = str(item.get("decision") or "")
        rows.append(
            {
                "capability": item.get("capability"),
                "mode_map_update": "INTERNAL_CANDIDATE_ONLY" if decision == "USE_MULTI_SKILL" else "KEEP_SINGLE_PRIMARY_FALLBACK",
                "selected_skill_ids": item.get("selected_skill_ids", []),
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
                "reason": item.get("reason", ""),
                "remaining_gate": item.get("remaining_gate", []),
            }
        )
    return {
        "schema": "nexus.heep_mode_map_update_gate_v2.v1",
        "status": "PASS",
        "summary": {
            "row_count": len(rows),
            "internal_candidate_count": sum(1 for row in rows if row["mode_map_update"] == "INTERNAL_CANDIDATE_ONLY"),
            "single_fallback_count": sum(1 for row in rows if row["mode_map_update"] == "KEEP_SINGLE_PRIMARY_FALLBACK"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "claim_boundary": [
            "Mode map updates are internal HEEP candidate state only.",
            "Runtime defaults require the runtime apply review gate.",
        ],
    }


def build_runtime_review_v2(
    *,
    runtime_packet: Mapping[str, Any],
    final_decisions: Mapping[str, Any],
) -> dict[str, Any]:
    rows = list(runtime_packet.get("rows", []) or [])
    for item in final_decisions.get("decisions", []) or []:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "capability": item.get("capability"),
                "selected_mode": item.get("selected_mode"),
                "selected_skill_ids": item.get("selected_skill_ids", []),
                "disposition": (
                    "REVIEW_HOLD_PROVIDER_CLEAN_REPLAY"
                    if item.get("decision") == "USE_MULTI_SKILL"
                    else "REVIEW_HOLD_SKILL_SPECIFIC_MAT_B_REPLAY"
                ),
                "mat_b_verdict": item.get("decision"),
                "mat_b_required_before_runtime_apply": True,
                "remaining_gate": item.get("remaining_gate", []),
                "runtime_update_allowed": False,
                "public_benchmark_allowed": False,
            }
        )
    return {
        "schema": "nexus.heep_runtime_apply_review_packet_v2.v1",
        "status": "PASS",
        "summary": {
            "row_count": len(rows),
            "existing_ready_for_runtime_apply_review_count": int(
                runtime_packet.get("summary", {}).get("ready_for_runtime_apply_review_count", 0) or 0
            ),
            "hold_for_provider_clean_count": sum(
                1 for row in rows if row.get("disposition") == "REVIEW_HOLD_PROVIDER_CLEAN_REPLAY"
            ),
            "hold_for_skill_specific_replay_count": sum(
                1 for row in rows if row.get("disposition") == "REVIEW_HOLD_SKILL_SPECIFIC_MAT_B_REPLAY"
            ),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "rows": rows,
        "claim_boundary": [
            "This packet records review candidates and holds; it is not runtime default apply approval.",
            "Provider-clean and skill-specific replay holds must close before runtime apply can consume the 13 blocked capabilities.",
        ],
    }


def build_public_readiness_gate(*, rollup: Mapping[str, Any], runtime_review: Mapping[str, Any]) -> dict[str, Any]:
    blockers = []
    if not rollup.get("summary", {}).get("public_benchmark_allowed"):
        blockers.append("mat_b_rollup_public_benchmark_allowed_false")
    if runtime_review.get("summary", {}).get("hold_for_provider_clean_count", 0):
        blockers.append("provider_clean_replay_holds_present")
    if runtime_review.get("summary", {}).get("hold_for_skill_specific_replay_count", 0):
        blockers.append("skill_specific_replay_holds_present")
    return {
        "schema": "nexus.heep_public_benchmark_readiness_gate.v1",
        "status": "BLOCKED" if blockers else "PASS",
        "summary": {
            "blocker_count": len(blockers),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": blockers,
        "claim_boundary": [
            "Internal HEEP/EMAS evidence cannot be converted into a public benchmark claim.",
            "Public benchmark requires its own same-model, hidden-verifier, provider-clean evidence bundle.",
        ],
    }


def build_taskcard_status(
    *,
    replay_status: Mapping[str, Any],
    rollup: Mapping[str, Any],
    mode_gate: Mapping[str, Any],
    runtime_review: Mapping[str, Any],
    public_gate: Mapping[str, Any],
) -> dict[str, Any]:
    provider_clean = not runtime_review.get("summary", {}).get("hold_for_provider_clean_count", 0)
    skill_specific = replay_status.get("status") == "PASS"
    taskcards = [
        {
            "taskcard": "HEEP-R1 Provider-Clean Replay Window",
            "status": "BLOCKED" if not provider_clean else "PASS",
            "evidence": str(DEFAULT_REPLAY_STATUS),
            "reason": "provider-clean replay holds remain" if not provider_clean else "provider token truth clean",
        },
        {
            "taskcard": "HEEP-R2 Executor Trio Skill-Specific MAT-B",
            "status": "BLOCKED" if not skill_specific else "PASS",
            "evidence": str(DEFAULT_REPLAY_STATUS),
            "reason": "skill-specific executor trio replay is not clean" if not skill_specific else "executor trio MAT-B clean",
        },
        {
            "taskcard": "HEEP-R3 Runtime Apply Review Refresh",
            "status": "PASS",
            "evidence": str(DEFAULT_RUNTIME_REVIEW),
            "reason": "review packet refreshed with explicit holds",
        },
        {
            "taskcard": "HEEP-R4 Runtime Overlay Apply Gate",
            "status": "BLOCKED",
            "evidence": str(DEFAULT_RUNTIME_REVIEW),
            "reason": "blocked rows cannot update runtime overlay/default",
        },
        {
            "taskcard": "HEEP-R5 Post-Apply Smoke",
            "status": "BLOCKED",
            "evidence": str(DEFAULT_RUNTIME_REVIEW),
            "reason": "no new runtime overlay apply is allowed before R1/R2 pass",
        },
        {
            "taskcard": "HEEP-R6 Public Benchmark Readiness",
            "status": str(public_gate.get("status") or "BLOCKED"),
            "evidence": str(DEFAULT_PUBLIC_GATE),
            "reason": "public benchmark remains separate and fail-closed",
        },
    ]
    return {
        "schema": "nexus.heep_taskcard_status_r1_r6.v1",
        "status": "PASS",
        "summary": {
            "taskcard_count": len(taskcards),
            "pass_count": sum(1 for item in taskcards if item["status"] == "PASS"),
            "blocked_count": sum(1 for item in taskcards if item["status"] == "BLOCKED"),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "taskcards": taskcards,
        "milestone_roadmap": [
            "DONE: 13/13 blocked capabilities have usable internal HEEP skill decisions.",
            "DONE: R3 review packet refresh is explicit and fail-closed.",
            "BLOCKED: R1/R2 need provider-clean and skill-specific MAT-B evidence.",
            "BLOCKED: R4/R5/R6 cannot proceed to apply/public lanes until R1/R2 pass.",
        ],
        "source_reports": {
            "rollup": str(DEFAULT_ROLLUP),
            "mode_gate": str(DEFAULT_MODE_GATE),
            "runtime_review": str(DEFAULT_RUNTIME_REVIEW),
            "public_gate": str(DEFAULT_PUBLIC_GATE),
        },
    }


def build_provider_receipt_blocker_rca(*, replay_status: Mapping[str, Any]) -> dict[str, Any]:
    first = replay_status.get("first_blocker", {})
    first = first if isinstance(first, Mapping) else {}
    provider_unclean = (
        first.get("token_data_contract_status") == "DATA_CONTRACT_VIOLATION"
        and str(first.get("token_data_contract_reason") or "") == "model_call_without_measured_provider_tokens"
    )
    model_delivery_failed = str(first.get("status") or "") == "FAILED" and str(first.get("semantic_status") or "") != "VERIFIED"
    missing_receipts = [str(item) for item in (first.get("expected_capability_missing") or []) if str(item)]
    receipt_downstream = bool(missing_receipts) and model_delivery_failed
    action = "WAIT_FOR_PROVIDER_CLEAN_REPLAY_WINDOW" if provider_unclean else "RUN_RECEIPT_RCA"
    if receipt_downstream:
        action = "WAIT_FOR_PROVIDER_CLEAN_REPLAY_WINDOW_THEN_RERUN_SKILL_SPECIFIC_MAT_B"
    return {
        "schema": "nexus.heep_provider_receipt_blocker_rca.v1",
        "status": "BLOCKED" if provider_unclean or receipt_downstream else "PASS",
        "summary": {
            "provider_unclean": provider_unclean,
            "model_delivery_failed": model_delivery_failed,
            "receipt_blocker_downstream_of_model_delivery": receipt_downstream,
            "missing_expected_capability_count": len(missing_receipts),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "first_blocker": dict(first),
        "diagnosis": [
            "provider_token_truth_is_not_fixable_by_local_score_or_estimated_tokens"
            if provider_unclean
            else "provider_token_truth_clean_or_not_observed",
            "skill_specific_receipt_missing_is_downstream_of_failed_model_required_row"
            if receipt_downstream
            else "skill_specific_receipt_requires_separate_rca",
            "matrix_has_executor_env_but_runtime_receipt_requires_successful_model_delivery_window",
        ],
        "next_action": action,
        "claim_boundary": [
            "Do not convert estimated tokens into provider-clean cost evidence.",
            "Do not backfill executor skill receipts on a semantically failed model-required row.",
            "A provider-clean same-window replay is the only admissible path to unblock R1/R2.",
        ],
    }


def build_all(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    final_decisions = read_json(Path(args.final_decisions))
    runtime_packet = read_json(Path(args.runtime_packet))
    replay_status = build_executor_trio_replay_status(replay_root=Path(args.replay_root))
    rollup = build_rollup_v2(
        final_decisions=final_decisions,
        replay_status=replay_status,
        runtime_packet=runtime_packet,
    )
    mode_gate = build_mode_gate_v2(final_decisions=final_decisions)
    runtime_review = build_runtime_review_v2(runtime_packet=runtime_packet, final_decisions=final_decisions)
    public_gate = build_public_readiness_gate(rollup=rollup, runtime_review=runtime_review)
    blocker_rca = build_provider_receipt_blocker_rca(replay_status=replay_status)
    taskcard_status = build_taskcard_status(
        replay_status=replay_status,
        rollup=rollup,
        mode_gate=mode_gate,
        runtime_review=runtime_review,
        public_gate=public_gate,
    )
    outputs = {
        Path(args.replay_status_output): replay_status,
        Path(args.rollup_output): rollup,
        Path(args.mode_gate_output): mode_gate,
        Path(args.runtime_review_output): runtime_review,
        Path(args.public_gate_output): public_gate,
        Path(args.taskcard_status_output): taskcard_status,
        Path(args.blocker_rca_output): blocker_rca,
    }
    for path, payload in outputs.items():
        write_json(path, payload)
    return {
        "replay_status": replay_status,
        "rollup": rollup,
        "mode_gate": mode_gate,
        "runtime_review": runtime_review,
        "public_gate": public_gate,
        "taskcard_status": taskcard_status,
        "blocker_rca": blocker_rca,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build HEEP MAT-B closure packets for remaining task cards.")
    parser.add_argument("--final-decisions", default=str(DEFAULT_FINAL_DECISIONS))
    parser.add_argument("--runtime-packet", default=str(DEFAULT_RUNTIME_PACKET))
    parser.add_argument("--replay-root", default=str(DEFAULT_REPLAY_ROOT))
    parser.add_argument("--replay-status-output", default=str(DEFAULT_REPLAY_STATUS))
    parser.add_argument("--rollup-output", default=str(DEFAULT_ROLLUP))
    parser.add_argument("--mode-gate-output", default=str(DEFAULT_MODE_GATE))
    parser.add_argument("--runtime-review-output", default=str(DEFAULT_RUNTIME_REVIEW))
    parser.add_argument("--public-gate-output", default=str(DEFAULT_PUBLIC_GATE))
    parser.add_argument("--taskcard-status-output", default=str(DEFAULT_TASKCARD_STATUS))
    parser.add_argument("--blocker-rca-output", default=str(DEFAULT_BLOCKER_RCA))
    args = parser.parse_args(argv)
    artifacts = build_all(args)
    print(
        json.dumps(
            {
                "status": "PASS",
                "replay_status": artifacts["replay_status"]["status"],
                "rollup_capability_count": artifacts["rollup"]["summary"]["capability_count"],
                "mode_gate_rows": artifacts["mode_gate"]["summary"]["row_count"],
                "runtime_review_rows": artifacts["runtime_review"]["summary"]["row_count"],
                "public_gate_status": artifacts["public_gate"]["status"],
                "taskcard_blocked_count": artifacts["taskcard_status"]["summary"]["blocked_count"],
                "blocker_rca_status": artifacts["blocker_rca"]["status"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
