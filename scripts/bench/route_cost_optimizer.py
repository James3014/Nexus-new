from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.bench.cost_evidence_classifier import (
    LOCAL_SUCCESS_SOURCES,
    model_attempt_runner_overhead_polluted,
    row_has_measured_provider_tokens,
)


@dataclass(frozen=True)
class TaskCostDecision:
    task_id: str
    decision: str
    reason: str
    baseline_verified: bool
    candidate_verified: bool
    bare_verified: bool
    baseline_wall_sec: float
    candidate_wall_sec: float
    baseline_tokens: float
    candidate_tokens: float
    candidate_effective_wall_sec: float
    candidate_runner_overhead_sec: float
    candidate_runner_overhead_polluted: bool
    wall_delta_pct: float
    token_delta_pct: float
    candidate_model_calls: int
    candidate_success_source: str
    candidate_token_source: str
    measured_token_only: bool
    clean_model_cost_evidence: bool
    cost_evidence_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "decision": self.decision,
            "reason": self.reason,
            "baseline_verified": self.baseline_verified,
            "candidate_verified": self.candidate_verified,
            "bare_verified": self.bare_verified,
            "baseline_wall_sec": self.baseline_wall_sec,
            "candidate_wall_sec": self.candidate_wall_sec,
            "baseline_tokens": self.baseline_tokens,
            "candidate_tokens": self.candidate_tokens,
            "candidate_effective_wall_sec": self.candidate_effective_wall_sec,
            "candidate_runner_overhead_sec": self.candidate_runner_overhead_sec,
            "candidate_runner_overhead_polluted": self.candidate_runner_overhead_polluted,
            "wall_delta_pct": self.wall_delta_pct,
            "token_delta_pct": self.token_delta_pct,
            "candidate_model_calls": self.candidate_model_calls,
            "candidate_success_source": self.candidate_success_source,
            "candidate_token_source": self.candidate_token_source,
            "measured_token_only": self.measured_token_only,
            "clean_model_cost_evidence": self.clean_model_cost_evidence,
            "cost_evidence_class": self.cost_evidence_class,
        }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _latest_jsonl(run_dir: Path, arm: str) -> Path:
    files = sorted(run_dir.glob(f"{arm}_*.jsonl"))
    if not files:
        raise FileNotFoundError(f"missing {arm}_*.jsonl in {run_dir}")
    return files[-1]


def _verified(row: dict[str, Any]) -> bool:
    return (
        bool(row.get("run_eligible", True))
        and str(row.get("semantic_status") or "") == "VERIFIED"
        and not bool(row.get("report_trust_mismatch", False))
    )


def _num(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _pct_delta(candidate: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0
    return round(((candidate - baseline) / baseline) * 100.0, 2)


def _candidate_rows(run_dir: Path) -> dict[str, dict[str, Any]]:
    rows = _load_jsonl(_latest_jsonl(run_dir, "with_nexus"))
    return {str(row.get("task_id") or ""): row for row in rows if row.get("task_id")}


def _candidate_bare_rows(run_dir: Path) -> dict[str, dict[str, Any]]:
    rows = _load_jsonl(_latest_jsonl(run_dir, "without_nexus"))
    return {str(row.get("task_id") or ""): row for row in rows if row.get("task_id")}


def _measured_token_only(row: dict[str, Any]) -> bool:
    return row_has_measured_provider_tokens(row)


def _clean_model_cost_evidence(row: dict[str, Any]) -> bool:
    if "clean_model_cost_evidence" in row:
        return bool(row.get("clean_model_cost_evidence", False))
    source = str(row.get("nexus_winner_source") or "").strip()
    return bool(
        _measured_token_only(row)
        and int(_num(row, "model_calls")) > 0
        and not _runner_overhead_polluted(row)
        and source not in LOCAL_SUCCESS_SOURCES
        and not source.startswith("local_preflight")
    )


def _cost_evidence_class(row: dict[str, Any]) -> str:
    explicit = str(row.get("cost_evidence_class") or "").strip()
    if explicit:
        return explicit
    if _clean_model_cost_evidence(row):
        return "clean_model_cost"
    if _runner_overhead_polluted(row):
        return "runner_overhead_polluted"
    source = str(row.get("nexus_winner_source") or "").strip()
    if int(_num(row, "model_calls")) <= 0:
        return "rescue_only_no_model_call" if source in LOCAL_SUCCESS_SOURCES or source.startswith("local_preflight") else "no_model_call"
    if source in LOCAL_SUCCESS_SOURCES or source.startswith("local_preflight"):
        if int(_num(row, "model_calls")) > 0:
            if _measured_token_only(row):
                return "rescue_with_model_fallback_measured"
            return "rescue_with_model_fallback"
        return "rescue_only_local_success"
    if not _measured_token_only(row):
        return "token_unreliable"
    return "not_clean_model_cost"


def _runner_overhead_polluted(row: dict[str, Any]) -> bool:
    return model_attempt_runner_overhead_polluted(row)


def _effective_candidate_wall(row: dict[str, Any]) -> float:
    model_attempt_wall = _num(row, "model_attempt_wall_sec")
    if model_attempt_wall > 0:
        return model_attempt_wall
    if _runner_overhead_polluted(row):
        cli_elapsed = _num(row, "cli_elapsed_sec")
        if cli_elapsed > 0:
            return cli_elapsed
    return _num(row, "wall_duration_sec")


def build_optimizer_plan(*, baseline_aggregate: dict[str, Any], candidate_dir: Path) -> dict[str, Any]:
    baseline_rows = {str(row.get("task_id") or ""): row for row in baseline_aggregate.get("rows", []) or []}
    candidate_rows = _candidate_rows(candidate_dir)
    candidate_bare_rows = _candidate_bare_rows(candidate_dir)
    decisions: list[TaskCostDecision] = []
    for task_id, candidate in sorted(candidate_rows.items()):
        baseline = baseline_rows.get(task_id, {})
        candidate_verified = _verified(candidate)
        baseline_verified = str(baseline.get("with_semantic") or "") == "VERIFIED" and str(baseline.get("with_status") or "") == "SUCCESS"
        bare = candidate_bare_rows.get(task_id, {})
        bare_verified = _verified(bare) or (str(baseline.get("without_semantic") or "") == "VERIFIED" and str(baseline.get("without_status") or "") == "SUCCESS")
        baseline_wall = float(baseline.get("with_wall") or 0.0)
        candidate_wall = _num(candidate, "wall_duration_sec")
        candidate_effective_wall = _effective_candidate_wall(candidate)
        candidate_runner_overhead = _num(candidate, "runner_overhead_sec")
        candidate_runner_overhead_polluted = _runner_overhead_polluted(candidate)
        baseline_tokens = float(baseline.get("with_tokens") or 0.0)
        candidate_tokens = _num(candidate, "total_tokens")
        source = str(candidate.get("nexus_winner_source") or "")
        token_source = str(candidate.get("gateway_token_source") or "missing")
        measured_token_only = _measured_token_only(candidate)
        clean_model_cost_evidence = _clean_model_cost_evidence(candidate)
        cost_evidence_class = _cost_evidence_class(candidate)
        calls = int(_num(candidate, "model_calls"))
        wall_delta = _pct_delta(candidate_effective_wall, baseline_wall)
        token_delta = _pct_delta(candidate_tokens, baseline_tokens)
        if not candidate_verified:
            decision = "reject_failed_candidate"
            reason = "candidate route did not preserve verified delivery"
        elif candidate_runner_overhead_polluted:
            decision = "hold_runner_overhead_polluted"
            reason = (
                "candidate wall cost is polluted by runner overhead; rerun inprocess or use uncontaminated cost truth before promotion"
            )
        elif clean_model_cost_evidence and wall_delta <= -15.0 and token_delta <= 5.0:
            decision = "promote_cost_tune"
            reason = f"verified with wall improvement {abs(wall_delta):.2f}% and token delta {token_delta:.2f}%"
        elif clean_model_cost_evidence and token_delta <= -15.0 and wall_delta <= 10.0:
            decision = "promote_cost_tune"
            reason = f"verified with token improvement {abs(token_delta):.2f}% and wall delta {wall_delta:.2f}%"
        elif bare_verified and candidate_verified:
            decision = "route_lite_required"
            reason = "bare also verified; Nexus should use lighter governance for this class"
        elif source in LOCAL_SUCCESS_SOURCES:
            decision = "hold_not_model_uplift"
            reason = f"candidate success source {source} is not model uplift"
        elif not measured_token_only:
            decision = "hold_not_model_uplift"
            reason = f"candidate token capture is not provider-measured: source={token_source}"
        else:
            decision = "hold_needs_trace_diagnosis"
            reason = f"verified but cost did not improve enough: wall_delta={wall_delta}% token_delta={token_delta}%"
        decisions.append(
            TaskCostDecision(
                task_id=task_id,
                decision=decision,
                reason=reason,
                baseline_verified=baseline_verified,
                candidate_verified=candidate_verified,
                bare_verified=bare_verified,
                baseline_wall_sec=baseline_wall,
                candidate_wall_sec=candidate_wall,
                baseline_tokens=baseline_tokens,
                candidate_tokens=candidate_tokens,
                candidate_effective_wall_sec=candidate_effective_wall,
                candidate_runner_overhead_sec=candidate_runner_overhead,
                candidate_runner_overhead_polluted=candidate_runner_overhead_polluted,
                wall_delta_pct=wall_delta,
                token_delta_pct=token_delta,
                candidate_model_calls=calls,
                candidate_success_source=source,
                candidate_token_source=token_source,
                measured_token_only=measured_token_only,
                clean_model_cost_evidence=clean_model_cost_evidence,
                cost_evidence_class=cost_evidence_class,
            )
        )
    counts: dict[str, int] = {}
    for item in decisions:
        counts[item.decision] = counts.get(item.decision, 0) + 1
    promoted = [item.task_id for item in decisions if item.decision == "promote_cost_tune"]
    lite = [item.task_id for item in decisions if item.decision == "route_lite_required"]
    hold = [item.task_id for item in decisions if item.decision.startswith("hold") or item.decision.startswith("reject")]
    feature_rules = [
        *_route_cost_feature_rules(
            decisions,
            candidate_rows,
            decision="promote_cost_tune",
            controls={"candidate_cap": 1},
        ),
        *_route_cost_feature_rules(
            decisions,
            candidate_rows,
            decision="route_lite_required",
            controls={"candidate_cap": 1, "lite_route": True},
        ),
        *_route_cost_feature_rules(
            decisions,
            candidate_rows,
            decision_prefixes=("hold", "reject"),
            controls={"hold": True},
        ),
    ]
    return {
        "schema_version": "nexus_route_cost_optimizer_v1",
        "baseline_schema": baseline_aggregate.get("schema_version", ""),
        "candidate_dir": str(candidate_dir),
        "cost_truth_table": [
            {
                "task_id": item.task_id,
                "baseline_wall_sec": item.baseline_wall_sec,
                "candidate_wall_sec": item.candidate_wall_sec,
                "candidate_effective_wall_sec": item.candidate_effective_wall_sec,
                "candidate_runner_overhead_sec": item.candidate_runner_overhead_sec,
                "candidate_runner_overhead_polluted": item.candidate_runner_overhead_polluted,
                "baseline_tokens": item.baseline_tokens,
                "candidate_tokens": item.candidate_tokens,
                "candidate_model_calls": item.candidate_model_calls,
                "candidate_token_source": item.candidate_token_source,
                "measured_token_only": item.measured_token_only,
                "clean_model_cost_evidence": item.clean_model_cost_evidence,
                "cost_evidence_class": item.cost_evidence_class,
                "candidate_verified": item.candidate_verified,
                "bare_verified": item.bare_verified,
            }
            for item in decisions
        ],
        "decision_counts": counts,
        "promoted_task_ids": promoted,
        "lite_required_task_ids": lite,
        "hold_task_ids": hold,
        "decisions": [item.to_dict() for item in decisions],
        "promoted_policy": {
            "schema_version": "nexus_promoted_route_cost_policy.v1",
            "source": str(candidate_dir),
            "feature_rules": feature_rules,
            "candidate_cap_overrides": {},
            "lite_route_tasks": [],
            "hold_tasks": [],
            "legacy_task_policy_source_ids": {
                "promoted_task_ids": promoted,
                "lite_required_task_ids": lite,
                "hold_task_ids": hold,
            },
            "promotion_gate": {
                "verified_delivery_preserved": all(item.candidate_verified for item in decisions),
                "trust_mismatch_zero_required": True,
                "reject_unreliable_local_fallback": True,
                "reject_runner_overhead_pollution": True,
                "runner_overhead_polluted": any(item.candidate_runner_overhead_polluted for item in decisions),
            },
        },
        "next_required_action": _next_required_action(decisions),
    }


def build_longtail_cost_recommendations(route_cost_ledger: dict[str, Any]) -> dict[str, Any]:
    """Convert route-cost ledger offenders into safe, lane-aware tuning hints."""

    arms = route_cost_ledger.get("arms", {}) if isinstance(route_cost_ledger, dict) else {}
    with_nexus = arms.get("with_nexus", {}) if isinstance(arms.get("with_nexus", {}), dict) else {}
    offenders = with_nexus.get("top_phase_wall_offenders") or with_nexus.get("top_wall_offenders") or []
    recommendations: list[dict[str, Any]] = []
    for offender in offenders if isinstance(offenders, list) else []:
        if not isinstance(offender, dict):
            continue
        phase = str(offender.get("dominant_phase") or "").upper()
        capability = str(offender.get("task_capability") or "unknown").strip() or "unknown"
        task_type = str(offender.get("task_type") or "").strip()
        controls: dict[str, Any] = {"context_mode": "compact"}
        safety_floor = ["mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"]
        rationale = "compact_context_for_longtail_offender"
        if phase == "R":
            controls["max_rounds"] = 1
            rationale = "cap_repair_phase_rounds_preserve_gates"
            if capability == "ddtree":
                controls["candidate_cap"] = 3
                safety_floor.append("ddtree")
                rationale = "ddtree_requires_three_candidates_but_single_repair_round"
            elif capability in {"autoreason", "ultra_review", "research"}:
                safety_floor.append(capability)
        elif phase == "X":
            controls["disable_research"] = capability != "research"
            rationale = "slim_recon_context_without_disabling_expected_research"
            if capability == "research":
                safety_floor.append("research")
        elif phase == "A":
            rationale = "audit_phase_longtail_preserve_claim_and_delivery_gates"
            safety_floor.extend(["claim_gate", "delivery_gate"])
        match = {"task_capability": capability}
        if task_type:
            match["task_type"] = task_type
        recommendations.append(
            {
                "task_id": str(offender.get("task_id") or ""),
                "match": match,
                "dominant_phase": phase,
                "controls": controls,
                "safety_floor": sorted(set(safety_floor)),
                "rationale": rationale,
                "claim_boundary": "recommendation_only_requires_rerun_before_promotion",
            }
        )
    return {
        "schema_version": "nexus_route_cost_longtail_recommendations_v1",
        "source_schema": str(route_cost_ledger.get("schema") or ""),
        "recommendations": recommendations,
        "promotion_gate": {
            "requires_verified_delivery_preserved": True,
            "requires_trust_mismatch_zero": True,
            "requires_same_model_rerun": True,
            "do_not_remove_governance_gates": True,
        },
    }


def _route_cost_feature_rules(
    decisions: list[TaskCostDecision],
    rows_by_task_id: dict[str, dict[str, Any]],
    *,
    controls: dict[str, Any],
    decision: str | None = None,
    decision_prefixes: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for item in decisions:
        if decision is not None and item.decision != decision:
            continue
        if decision_prefixes and not item.decision.startswith(decision_prefixes):
            continue
        match = _stable_feature_match(rows_by_task_id.get(item.task_id, {}))
        if not match:
            continue
        rule_id = "optimizer:{decision}:{task_id}".format(decision=item.decision, task_id=_slug(item.task_id))
        rules.append(
            {
                "id": rule_id,
                "match": match,
                "controls": dict(controls),
                "source_task_ids": [item.task_id],
                "evidence": {
                    "reason": item.reason,
                    "wall_delta_pct": item.wall_delta_pct,
                    "token_delta_pct": item.token_delta_pct,
                    "cost_evidence_class": item.cost_evidence_class,
                },
            }
        )
    return rules


def _stable_feature_match(row: dict[str, Any]) -> dict[str, str]:
    keys = ("task_type", "difficulty", "category", "repo_kind", "fixture_kind")
    return {key: str(row.get(key)).strip() for key in keys if str(row.get(key) or "").strip()}


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in str(value).strip()).strip("-") or "unknown"


def _next_required_action(decisions: list[TaskCostDecision]) -> str:
    if any(item.decision == "reject_failed_candidate" for item in decisions):
        return "stop_and_fix_failed_candidate_before_more_cost_tuning"
    if any(item.decision == "hold_runner_overhead_polluted" for item in decisions):
        return "rerun_polluted_cost_rows_inprocess_before_promotion"
    if any(item.decision == "hold_not_model_uplift" for item in decisions):
        return "rerun_hold_tasks_with_measured_model_tokens_or_keep_out_of_model_uplift_claim"
    if any(item.decision == "hold_needs_trace_diagnosis" for item in decisions):
        return "diagnose_hold_tasks_before_promoting_cost_policy"
    if any(item.decision == "route_lite_required" for item in decisions):
        return "implement_lite_route_for_bare_already_verified_tasks"
    return "promote_cost_policy_then_rerun_12_task_fail_fast_loop"


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Nexus Route Cost Optimizer",
        "",
        f"- candidate_dir: `{payload['candidate_dir']}`",
        f"- next_required_action: `{payload['next_required_action']}`",
        "",
        "## Decision Counts",
        "",
    ]
    for name, count in sorted(payload["decision_counts"].items()):
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Cost Truth Table", "", "| Task | Raw wall | Effective wall | Runner overhead | Polluted | Tokens |", "| :--- | ---: | ---: | ---: | :--- | ---: |"])
    for row in payload.get("cost_truth_table", []) or []:
        lines.append(
            f"| {row['task_id']} | {row['candidate_wall_sec']} | {row['candidate_effective_wall_sec']} | "
            f"{row['candidate_runner_overhead_sec']} | {row['candidate_runner_overhead_polluted']} | {row['candidate_tokens']} |"
        )
    lines.extend(
        [
            "",
            "## Decisions",
            "",
            "| Task | Decision | Wall delta | Token delta | Winner | Token source | Measured-only | Reason |",
            "| :--- | :--- | ---: | ---: | :--- | :--- | :--- | :--- |",
        ]
    )
    for row in payload["decisions"]:
        lines.append(
            f"| {row['task_id']} | {row['decision']} | {row['wall_delta_pct']}% | {row['token_delta_pct']}% | "
            f"{row['candidate_success_source']} | {row['candidate_token_source']} | {row['measured_token_only']} | {row['reason']} |"
        )
    lines.extend(["", "## Promoted Policy Draft", "", "```json", json.dumps(payload["promoted_policy"], ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare a route cost tuning run against a baseline aggregate and draft route-cost policy.")
    parser.add_argument("--baseline-aggregate", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--policy-output")
    args = parser.parse_args(argv)
    payload = build_optimizer_plan(
        baseline_aggregate=_load_json(Path(args.baseline_aggregate)),
        candidate_dir=Path(args.candidate_dir),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(payload), encoding="utf-8")
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.policy_output:
        policy = Path(args.policy_output)
        policy.parent.mkdir(parents=True, exist_ok=True)
        policy.write_text(json.dumps(payload["promoted_policy"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
