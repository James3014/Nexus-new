#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

from scripts.bench.ab_eval import compare_datasets, load_runs


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _wall_speedup(delta_sec: float, baseline_sec: float) -> str:
    if baseline_sec <= 0:
        return "n/a"
    return _pct(-delta_sec / baseline_sec)


def _token_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("token_capture_status") or "unknown").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _count_text(counts: dict[str, int], key: str) -> str:
    return str(counts.get(key, 0))


def _scope_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    task_ids = {str(row.get("task_id") or "") for row in rows if row.get("task_id")}
    trials = {
        int(row.get("trial_index") or 1)
        for row in rows
        if str(row.get("trial_index") or "").strip()
    }
    return {
        "rows": len(rows),
        "unique_tasks": len(task_ids),
        "repeat_trials": max(trials) if trials else 1,
    }


def _infra_invalid_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if bool(row.get("run_eligible", True)):
            continue
        reason = str(row.get("infra_invalid_reason") or "unknown").strip() or "unknown"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _run_eligible_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if bool(row.get("run_eligible", True)))


def _is_verified(row: dict[str, Any]) -> bool:
    return str(row.get("semantic_status", "")).strip().upper() == "VERIFIED"


def _eligible_solve_rate(rows: list[dict[str, Any]]) -> float:
    eligible = [row for row in rows if bool(row.get("run_eligible", True))]
    if not eligible:
        return 0.0
    return sum(1 for row in eligible if _is_verified(row)) / len(eligible)


def _reasons_text(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{reason}:{count}" for reason, count in sorted(counts.items()))


def _public_token_claim_status(a: dict[str, Any], b: dict[str, Any], *, min_rate: float = 0.8) -> str:
    try:
        without_rate = float(a.get("token_measured_rate", 0.0) or 0.0)
        with_rate = float(b.get("token_measured_rate", 0.0) or 0.0)
    except (TypeError, ValueError):
        return "NO"
    return "YES" if without_rate >= min_rate and with_rate >= min_rate else "NO"


def _capability_label(row: dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("task_id", "category", "task_type", "fixture_kind", "task_desc", "success_criteria")
    ).lower()
    if any(token in text for token in ("belief", "confidence", "memory", "prior", "history")):
        return "Belief / Memory"
    if any(token in text for token in ("governance", "scope", "mempalace", "policy")):
        return "MemPalace / governance"
    if any(token in text for token in ("evidence", "artifact", "claim", "verify", "verification")):
        return "Artifact / Claim"
    if any(token in text for token in ("second", "round", "repair", "self-heal", "self_heal")):
        return "RLM / self-heal"
    return "General"


def _pillar_win_rows(
    rows_without: list[dict[str, Any]],
    rows_with: list[dict[str, Any]],
) -> list[dict[str, str]]:
    without_by_key = {_task_trial_key(row): row for row in rows_without}
    wins: list[dict[str, str]] = []
    for row in rows_with:
        key = _task_trial_key(row)
        baseline = without_by_key.get(key, {})
        if _is_verified(row) and not _is_verified(baseline):
            wins.append(
                {
                    "task_id": str(row.get("task_id") or key[0]),
                    "trial": str(row.get("trial_index") or key[1]),
                    "capability": _capability_label(row),
                    "without": str(baseline.get("semantic_status") or baseline.get("status") or "UNKNOWN"),
                    "with": str(row.get("semantic_status") or row.get("status") or "UNKNOWN"),
                }
            )
    return wins


def _task_trial_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("task_id") or ""), str(row.get("trial_index") or "1"))


def _multiset_counts(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = _task_trial_key(row)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _public_claim_gate(
    *,
    rows_without: list[dict[str, Any]],
    rows_with: list[dict[str, Any]],
    summary_without: dict[str, Any],
    summary_with: dict[str, Any],
    formal: dict[str, Any],
    min_token_rate: float = 0.8,
    min_nexus_valid_rate: float = 1.0,
) -> dict[str, Any]:
    failures: list[str] = []
    if any(str(row.get("parallel_arms_mode") or "") == "smoke-only" for row in [*rows_without, *rows_with]):
        failures.append("parallel_smoke")
    if not rows_without or not rows_with:
        failures.append("missing_rows")
    if _multiset_counts(rows_without) != _multiset_counts(rows_with):
        failures.append("task_trial_mismatch")
    try:
        if float(summary_without.get("token_measured_rate", 0.0) or 0.0) < min_token_rate:
            failures.append("without_token_measured_below_threshold")
        if float(summary_with.get("token_measured_rate", 0.0) or 0.0) < min_token_rate:
            failures.append("with_token_measured_below_threshold")
        if float(formal.get("valid_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("nexus_wearing_below_threshold")
        if float(summary_with.get("gemini_uses_nexus_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("gemini_uses_nexus_below_threshold")
        if float(summary_with.get("nexus_usage_valid_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("nexus_usage_valid_below_threshold")
        if float(summary_with.get("phase_completion_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("phase_completion_below_threshold")
        if float(summary_with.get("claim_verified_rate", 0.0) or 0.0) < min_nexus_valid_rate:
            failures.append("claim_verified_below_threshold")
    except (TypeError, ValueError):
        failures.append("metric_parse_error")
    rlm_rows = [row for row in rows_with if row.get("rlm_trace_present")]
    for row in rlm_rows:
        submit_count = int(row.get("rlm_submit_count", 0) or 0)
        verified_count = int(row.get("rlm_verified_count", 0) or 0)
        audit_rejected_count = int(row.get("rlm_audit_rejected_count", 0) or 0)
        trace_quality = int(row.get("rlm_trace_quality_score", 0) or 0)
        if submit_count > 0 and verified_count + audit_rejected_count <= 0:
            failures.append("rlm_submit_without_a_gate")
        if str(row.get("status") or row.get("semantic_status") or "") == "SUCCESS" and submit_count > 0 and verified_count <= 0:
            failures.append("rlm_success_without_verified_trace")
        if trace_quality < 60:
            failures.append("rlm_trace_quality_below_threshold")
        if bool(row.get("rlm_loop_phase") == "X") and not bool(row.get("rlm_x_loop_budget_observed", False)):
            failures.append("rlm_x_loop_budget_missing")
    return {
        "verdict": "PASS" if not failures else "FAIL",
        "failures": sorted(set(failures)),
    }


def render_markdown_report(
    *,
    without_path: str,
    with_path: str,
    label_without: str,
    label_with: str,
    benchmark_date: str,
) -> str:
    rows_without = load_runs(without_path)
    rows_with = load_runs(with_path)
    report = compare_datasets(
        label_without,
        rows_without,
        label_with,
        rows_with,
    )
    a = report["a"]["summary"]
    b = report["b"]["summary"]
    delta = report["delta"]
    formal = report["formal_treatment"]
    wall_delta = float(delta["avg_wall_duration_sec_delta"])
    baseline_wall = float(a["avg_wall_duration_sec"])
    token_without = _token_status_counts(rows_without)
    token_with = _token_status_counts(rows_with)
    without_scope = _scope_summary(rows_without)
    with_scope = _scope_summary(rows_with)
    token_public_safe = _public_token_claim_status(a, b)
    infra_without = _infra_invalid_counts(rows_without)
    infra_with = _infra_invalid_counts(rows_with)
    eligible_without = _run_eligible_count(rows_without)
    eligible_with = _run_eligible_count(rows_with)
    eligible_solve_without = _eligible_solve_rate(rows_without)
    eligible_solve_with = _eligible_solve_rate(rows_with)
    eligible_solve_delta = eligible_solve_with - eligible_solve_without
    pillar_wins = _pillar_win_rows(rows_without, rows_with)
    public_gate = _public_claim_gate(
        rows_without=rows_without,
        rows_with=rows_with,
        summary_without=a,
        summary_with=b,
        formal=formal,
    )
    gate_failures = public_gate["failures"]
    solve_delta = float(eligible_solve_delta)
    if solve_delta > 0:
        public_claim_text = (
            f"On this fixed benchmark set, `{label_with}` improved eligible solve rate from "
            f"{_pct(eligible_solve_without)} to {_pct(eligible_solve_with)} "
            f"({_pct(eligible_solve_delta)} absolute) while keeping trust mismatch at "
            f"{_pct(b['trust_mismatch_rate'])}."
        )
    elif solve_delta == 0:
        public_claim_text = (
            f"On this fixed benchmark set, `{label_with}` matched eligible solve rate at "
            f"{_pct(eligible_solve_with)} while providing Nexus wearing evidence for "
            f"{formal['valid_count']}/{formal['total_runs']} rows and keeping trust mismatch at "
            f"{_pct(b['trust_mismatch_rate'])}."
        )
    else:
        public_claim_text = (
            f"On this fixed benchmark set, `{label_with}` reduced eligible solve rate from "
            f"{_pct(eligible_solve_without)} to {_pct(eligible_solve_with)} "
            f"({_pct(eligible_solve_delta)} absolute); no positive solve-rate claim is allowed."
        )
    if public_gate["verdict"] != "PASS":
        public_claim_text = (
            "No public performance claim is allowed from this run because the public claim gate failed. "
            f"Failures: {_reasons_text({reason: 1 for reason in gate_failures})}."
        )

    lines = [
        f"# {label_with} Benchmark Report",
        "",
        f"- Date: {benchmark_date}",
        f"- Baseline: `{label_without}`",
        f"- Treatment: `{label_with}`",
        f"- Without Nexus: `{without_path}`",
        f"- With Nexus: `{with_path}`",
        f"- Without Nexus scope: {without_scope['unique_tasks']} unique tasks x {without_scope['repeat_trials']} trials = {without_scope['rows']} rows",
        f"- With Nexus scope: {with_scope['unique_tasks']} unique tasks x {with_scope['repeat_trials']} trials = {with_scope['rows']} rows",
        "",
        "## Result",
        "",
        "| Metric | Without Nexus | With Nexus | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| Usable rows | {eligible_without}/{without_scope['rows']} | {eligible_with}/{with_scope['rows']} | n/a |",
        f"| Infra invalid rows | {without_scope['rows'] - eligible_without} | {with_scope['rows'] - eligible_with} | n/a |",
        f"| Solve rate | {_pct(a['solve_rate'])} | {_pct(b['solve_rate'])} | {_pct(delta['solve_rate_delta'])} |",
        f"| Eligible solve rate | {_pct(eligible_solve_without)} | {_pct(eligible_solve_with)} | {_pct(eligible_solve_delta)} |",
        f"| Semantic verified | {_pct(a['semantic_verified_rate'])} | {_pct(b['semantic_verified_rate'])} | {_pct(delta['semantic_verified_rate_delta'])} |",
        f"| Trust mismatch | {_pct(a['trust_mismatch_rate'])} | {_pct(b['trust_mismatch_rate'])} | {_pct(delta['trust_mismatch_rate_delta'])} |",
        f"| Avg wall time | {_num(a['avg_wall_duration_sec'])}s | {_num(b['avg_wall_duration_sec'])}s | {_num(wall_delta)}s |",
        f"| Wall speedup | n/a | {_wall_speedup(wall_delta, baseline_wall)} | n/a |",
        f"| Avg model calls | {_num(a['avg_model_calls'])} | {_num(b['avg_model_calls'])} | {_num(delta['avg_model_calls_delta'])} |",
        f"| Token measured rate | {_pct(a['token_measured_rate'])} | {_pct(b['token_measured_rate'])} | {_pct(delta['token_measured_rate_delta'])} |",
        f"| Token local-only rate | {_pct(a['token_local_only_rate'])} | {_pct(b['token_local_only_rate'])} | {_pct(delta['token_local_only_rate_delta'])} |",
        f"| Cost-comparable rate | {_pct(a['cost_comparable_rate'])} | {_pct(b['cost_comparable_rate'])} | {_pct(delta['cost_comparable_rate_delta'])} |",
        f"| Model token measured rate | {_pct(a['model_token_measured_rate'])} | {_pct(b['model_token_measured_rate'])} | {_pct(delta['model_token_measured_rate_delta'])} |",
        f"| Gateway stats source rate | {_pct(a['gateway_stats_source_rate'])} | {_pct(b['gateway_stats_source_rate'])} | {_pct(delta['gateway_stats_source_rate_delta'])} |",
        f"| Gateway usage metadata source rate | {_pct(a['gateway_usage_metadata_source_rate'])} | {_pct(b['gateway_usage_metadata_source_rate'])} | {_pct(delta['gateway_usage_metadata_source_rate_delta'])} |",
        f"| Local rescue rate | {_pct(a['local_rescue_rate'])} | {_pct(b['local_rescue_rate'])} | {_pct(delta['local_rescue_rate_delta'])} |",
        f"| Guard fallback rate | {_pct(a['guard_fallback_rate'])} | {_pct(b['guard_fallback_rate'])} | {_pct(delta['guard_fallback_rate_delta'])} |",
        f"| Verification rescue rate | {_pct(a['verification_rescue_rate'])} | {_pct(b['verification_rescue_rate'])} | {_pct(delta['verification_rescue_rate_delta'])} |",
        f"| LLM self-heal rate | {_pct(a['llm_self_heal_rate'])} | {_pct(b['llm_self_heal_rate'])} | {_pct(delta['llm_self_heal_rate_delta'])} |",
        f"| RLM trace present | {_pct(a['rlm_trace_present_rate'])} | {_pct(b['rlm_trace_present_rate'])} | {_pct(delta['rlm_trace_present_rate_delta'])} |",
        f"| RLM trace quality | {_num(a['avg_rlm_trace_quality_score'])} | {_num(b['avg_rlm_trace_quality_score'])} | {_num(delta['avg_rlm_trace_quality_score_delta'])} |",
        f"| Token public-safe claim | {token_public_safe} | {token_public_safe} | n/a |",
        "",
        "## Five-Pillar Contribution",
        "",
        "| Pillar | Without Nexus | With Nexus | Delta | Evidence signal |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| LanceDB | {_pct(a['pillar_lancedb_active_rate'])} | {_pct(b['pillar_lancedb_active_rate'])} | {_pct(b['pillar_lancedb_active_rate'] - a['pillar_lancedb_active_rate'])} | tactical retrieval active |",
        f"| Memory | {_pct(a['pillar_memory_active_rate'])} | {_pct(b['pillar_memory_active_rate'])} | {_pct(b['pillar_memory_active_rate'] - a['pillar_memory_active_rate'])} | prior lessons/hits active |",
        f"| MemPalace | {_pct(a['pillar_mempalace_active_rate'])} | {_pct(b['pillar_mempalace_active_rate'])} | {_pct(b['pillar_mempalace_active_rate'] - a['pillar_mempalace_active_rate'])} | governance boundary active |",
        f"| Belief | {_pct(a['pillar_belief_active_rate'])} | {_pct(b['pillar_belief_active_rate'])} | {_pct(b['pillar_belief_active_rate'] - a['pillar_belief_active_rate'])} | confidence/budget signal active |",
        f"| Artifact / Claim | {_pct(a['pillar_artifact_active_rate'])} | {_pct(b['pillar_artifact_active_rate'])} | {_pct(b['pillar_artifact_active_rate'] - a['pillar_artifact_active_rate'])} | artifact checks + claim verification |",
        f"| Claim verified | {_pct(a['claim_verified_rate'])} | {_pct(b['claim_verified_rate'])} | {_pct(delta['claim_verified_rate_delta'])} | A/C acceptance evidence |",
        "",
        "## MSA / Orchestration Trace",
        "",
        "| Capability | Without Nexus | With Nexus | Delta | Evidence signal |",
        "| --- | ---: | ---: | ---: | --- |",
        f"| Hyper | {_pct(a['hyper_used_rate'])} | {_pct(b['hyper_used_rate'])} | {_pct(delta['hyper_used_rate_delta'])} | focused sprint route active |",
        f"| Self-heal | {_pct(a['self_heal_used_rate'])} | {_pct(b['self_heal_used_rate'])} | {_pct(delta['self_heal_used_rate_delta'])} | repair loop/self-heal active |",
        f"| Swarm | {_pct(a['swarm_used_rate'])} | {_pct(b['swarm_used_rate'])} | {_pct(delta['swarm_used_rate_delta'])} | evidence-backed swarm sandbox used |",
        f"| Drone | {_pct(a['drone_used_rate'])} | {_pct(b['drone_used_rate'])} | {_pct(delta['drone_used_rate_delta'])} | delegated worker/drone used |",
        f"| Nightshift recommended | {_pct(a['nightshift_recommended_rate'])} | {_pct(b['nightshift_recommended_rate'])} | {_pct(delta['nightshift_recommended_rate_delta'])} | escalation recommended |",
        f"| Nightshift invoked | {_pct(a['nightshift_invoked_rate'])} | {_pct(b['nightshift_invoked_rate'])} | {_pct(delta['nightshift_invoked_rate_delta'])} | nightshift report evidence exists |",
        f"| Nightshift recovered | {_pct(a['nightshift_recovery_rate'])} | {_pct(b['nightshift_recovery_rate'])} | {_pct(delta['nightshift_recovery_rate_delta'])} | nightshift recovery verified |",
        f"| Autoreason | {_pct(a['autoreason_enabled_rate'])} | {_pct(b['autoreason_enabled_rate'])} | {_pct(delta['autoreason_enabled_rate_delta'])} | candidate judge active |",
        f"| DDTree enabled | {_pct(a['ddtree_enabled_rate'])} | {_pct(b['ddtree_enabled_rate'])} | {_pct(delta['ddtree_enabled_rate_delta'])} | candidate pruning layer active |",
        f"| DDTree eligible | {_pct(a['ddtree_eligible_rate'])} | {_pct(b['ddtree_eligible_rate'])} | {_pct(delta['ddtree_eligible_rate_delta'])} | enough candidates for pruning |",
        f"| Ultra Review recommended | {_pct(a['ultra_review_recommended_rate'])} | {_pct(b['ultra_review_recommended_rate'])} | {_pct(delta['ultra_review_recommended_rate_delta'])} | high-risk governance route selected |",
        f"| Ultra Review invoked | {_pct(a['ultra_review_invoked_rate'])} | {_pct(b['ultra_review_invoked_rate'])} | {_pct(delta['ultra_review_invoked_rate_delta'])} | high-risk dry gate executed |",
        f"| RLM trace present | {_pct(a['rlm_trace_present_rate'])} | {_pct(b['rlm_trace_present_rate'])} | {_pct(delta['rlm_trace_present_rate_delta'])} | recursive trace emitted |",
        f"| RLM trace quality | {_num(a['avg_rlm_trace_quality_score'])} | {_num(b['avg_rlm_trace_quality_score'])} | {_num(delta['avg_rlm_trace_quality_score_delta'])} | trace has submit/A-gate/evidence signal |",
        "",
        "## Capability Win Map",
        "",
        "| Task | Trial | Capability | Without Nexus | With Nexus |",
        "| --- | ---: | --- | --- | --- |",
        *(
            [
                f"| {row['task_id']} | {row['trial']} | {row['capability']} | {row['without']} | {row['with']} |"
                for row in pillar_wins
            ]
            or ["| none | n/a | n/a | n/a | n/a |"]
        ),
        "",
        "## Token Telemetry",
        "",
        "| Token status | Without Nexus | With Nexus |",
        "| --- | ---: | ---: |",
        f"| measured | {_count_text(token_without, 'measured')} | {_count_text(token_with, 'measured')} |",
        f"| estimated | {_count_text(token_without, 'estimated')} | {_count_text(token_with, 'estimated')} |",
        f"| missing/unknown | {_count_text(token_without, 'missing')}/{_count_text(token_without, 'unknown')} | {_count_text(token_with, 'missing')}/{_count_text(token_with, 'unknown')} |",
        f"| not applicable local only | {_count_text(token_without, 'not_applicable_local_only')} | {_count_text(token_with, 'not_applicable_local_only')} |",
        "",
        "## Run Validity",
        "",
        f"- Public claim gate: {public_gate['verdict']}",
        f"- Public claim gate failures: {_reasons_text({reason: 1 for reason in gate_failures})}",
        f"- Without Nexus usable rows: {eligible_without}/{without_scope['rows']}",
        f"- With Nexus usable rows: {eligible_with}/{with_scope['rows']}",
        f"- Without Nexus infra invalid reasons: {_reasons_text(infra_without)}",
        f"- With Nexus infra invalid reasons: {_reasons_text(infra_with)}",
        "",
        "## Nexus Wearing Evidence",
        "",
        f"- Formal treatment valid: {formal['valid_count']}/{formal['total_runs']} ({_pct(formal['valid_rate'])})",
        f"- Gemini uses Nexus rate: {_pct(b['gemini_uses_nexus_rate'])}",
        f"- Nexus usage valid rate: {_pct(b['nexus_usage_valid_rate'])}",
        f"- Phase completion rate: {_pct(b['phase_completion_rate'])}",
        f"- Claim verified rate: {_pct(b['claim_verified_rate'])}",
        f"- Nexus rescue rate: {_pct(b['nexus_rescue_rate'])}",
        f"- Guard fallback rate: {_pct(b['guard_fallback_rate'])}",
        f"- Verification rescue rate: {_pct(b['verification_rescue_rate'])}",
        f"- LLM self-heal rate: {_pct(b['llm_self_heal_rate'])}",
        "",
        "## Public-Safe Claim",
        "",
        public_claim_text,
        "",
        "## Limits",
        "",
        "- Token/cost claims are not public-safe unless token measured rate is high enough for both arms.",
        "- Small samples need repeated trials before publication-grade claims.",
        "- This report proves benchmark-row evidence, not broad production generalization.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Gemini bare vs Gemini+Nexus benchmark markdown.")
    parser.add_argument("--without", required=True, help="Without-Nexus JSON/JSONL/CSV path")
    parser.add_argument("--with-nexus", required=True, help="With-Nexus JSON/JSONL/CSV path")
    parser.add_argument("--label-without", default="gemini_3_flash_bare")
    parser.add_argument("--label-with", default="gemini_3_flash_nexus")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--output", required=True, help="Markdown output path")
    args = parser.parse_args()

    markdown = render_markdown_report(
        without_path=args.without,
        with_path=args.with_nexus,
        label_without=args.label_without,
        label_with=args.label_with,
        benchmark_date=args.date,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
