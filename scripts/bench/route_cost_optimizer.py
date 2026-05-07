from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOCAL_SUCCESS_SOURCES = {"local", "local_only", "local_hidden_shadow", "local_deterministic_success", "nexus_tool_success"}


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
    wall_delta_pct: float
    token_delta_pct: float
    candidate_model_calls: int
    candidate_success_source: str

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
            "wall_delta_pct": self.wall_delta_pct,
            "token_delta_pct": self.token_delta_pct,
            "candidate_model_calls": self.candidate_model_calls,
            "candidate_success_source": self.candidate_success_source,
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
        baseline_tokens = float(baseline.get("with_tokens") or 0.0)
        candidate_tokens = _num(candidate, "total_tokens")
        source = str(candidate.get("nexus_winner_source") or "")
        calls = int(_num(candidate, "model_calls"))
        wall_delta = _pct_delta(candidate_wall, baseline_wall)
        token_delta = _pct_delta(candidate_tokens, baseline_tokens)
        if not candidate_verified:
            decision = "reject_failed_candidate"
            reason = "candidate route did not preserve verified delivery"
        elif source in LOCAL_SUCCESS_SOURCES:
            decision = "hold_not_model_uplift"
            reason = f"candidate success source {source} is not model uplift"
        elif str(candidate.get("token_capture_status") or "") != "measured":
            decision = "hold_not_model_uplift"
            reason = "candidate token capture is not measured"
        elif wall_delta <= -15.0 and token_delta <= 5.0:
            decision = "promote_cost_tune"
            reason = f"verified with wall improvement {abs(wall_delta):.2f}% and token delta {token_delta:.2f}%"
        elif token_delta <= -15.0 and wall_delta <= 10.0:
            decision = "promote_cost_tune"
            reason = f"verified with token improvement {abs(token_delta):.2f}% and wall delta {wall_delta:.2f}%"
        elif bare_verified and candidate_verified:
            decision = "route_lite_required"
            reason = "bare also verified; Nexus should use lighter governance for this class"
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
                wall_delta_pct=wall_delta,
                token_delta_pct=token_delta,
                candidate_model_calls=calls,
                candidate_success_source=source,
            )
        )
    counts: dict[str, int] = {}
    for item in decisions:
        counts[item.decision] = counts.get(item.decision, 0) + 1
    promoted = [item.task_id for item in decisions if item.decision == "promote_cost_tune"]
    lite = [item.task_id for item in decisions if item.decision == "route_lite_required"]
    hold = [item.task_id for item in decisions if item.decision.startswith("hold") or item.decision.startswith("reject")]
    return {
        "schema_version": "nexus_route_cost_optimizer_v1",
        "baseline_schema": baseline_aggregate.get("schema_version", ""),
        "candidate_dir": str(candidate_dir),
        "decision_counts": counts,
        "promoted_task_ids": promoted,
        "lite_required_task_ids": lite,
        "hold_task_ids": hold,
        "decisions": [item.to_dict() for item in decisions],
        "promoted_policy": {
            "schema_version": "nexus_promoted_route_cost_policy.v1",
            "source": str(candidate_dir),
            "candidate_cap_overrides": {task_id: 1 for task_id in promoted},
            "lite_route_tasks": lite,
            "hold_tasks": hold,
            "promotion_gate": {
                "verified_delivery_preserved": all(item.candidate_verified for item in decisions),
                "trust_mismatch_zero_required": True,
                "reject_unreliable_local_fallback": True,
            },
        },
        "next_required_action": _next_required_action(decisions),
    }


def _next_required_action(decisions: list[TaskCostDecision]) -> str:
    if any(item.decision == "reject_failed_candidate" for item in decisions):
        return "stop_and_fix_failed_candidate_before_more_cost_tuning"
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
    lines.extend(["", "## Decisions", "", "| Task | Decision | Wall delta | Token delta | Source | Reason |", "| :--- | :--- | ---: | ---: | :--- | :--- |"])
    for row in payload["decisions"]:
        lines.append(
            f"| {row['task_id']} | {row['decision']} | {row['wall_delta_pct']}% | {row['token_delta_pct']}% | "
            f"{row['candidate_success_source']} | {row['reason']} |"
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
