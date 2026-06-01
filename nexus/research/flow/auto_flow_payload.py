from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AutoFlowPayloadParts:
    task_desc: str
    task_type: str
    asi_ledger: list[dict[str, Any]]
    route: dict[str, Any]
    execution_profile: dict[str, Any]
    chosen_flow: str
    guard_hit: bool
    early_baseline_shortcut: bool
    history_forced_baseline: bool
    learn_gate_blocked: bool
    force_flow: str | None
    recent_hyper_fails: int
    nightshift_recommended: bool
    stage1_fail_signals: int
    history_window: int
    baseline_fast_sec: float
    max_time_ratio_guard: float
    baseline_probe_skipped: bool
    baseline_probe: dict[str, Any] | None
    plateau_hard_pivot: bool
    learn_phase_slo: dict[str, Any]
    result: dict[str, Any]
    claim_check: dict[str, Any]
    hitl: dict[str, Any]
    research_preflight: dict[str, Any]
    route_confidence: float
    strategy_path: str
    plateau: dict[str, Any]
    artifact_summary: dict[str, Any]
    success_criteria_name: str
    mutation_required: bool
    verification_only_allowed: bool
    nexus_usage_trace: dict[str, Any]
    cli_elapsed_sec: float
    phase_wall_sec: dict[str, float]
    timing_breakdown_sec: dict[str, float]


def build_auto_flow_payload(parts: AutoFlowPayloadParts) -> dict[str, Any]:
    learn_global = parts.learn_phase_slo.get("global", {}) if isinstance(parts.learn_phase_slo.get("global"), dict) else {}
    return {
        "schema_version": "1.0",
        "task_desc": parts.task_desc,
        "task_type": parts.task_type,
        "asi_ledger": parts.asi_ledger,
        "route": parts.route,
        "execution_profile": parts.execution_profile,
        "chosen_flow": parts.chosen_flow,
        "guard": {
            "hit": parts.guard_hit,
            "early_baseline_shortcut": parts.early_baseline_shortcut,
            "history_forced_baseline": parts.history_forced_baseline,
            "learn_forced_baseline": bool(
                parts.learn_gate_blocked
                and parts.force_flow is None
                and (not parts.execution_profile["is_hard_task"] or parts.chosen_flow == "baseline")
            ),
            "recent_hyper_failures": parts.recent_hyper_fails,
            "nightshift_recommended": parts.nightshift_recommended,
            "stage1_fail_signals": parts.stage1_fail_signals,
            "history_window": max(1, parts.history_window),
            "baseline_fast_sec": parts.baseline_fast_sec,
            "max_time_ratio_guard": parts.max_time_ratio_guard,
            "baseline_probe_skipped": parts.baseline_probe_skipped,
            "baseline_probe": parts.baseline_probe,
            "plateau_hard_pivot": parts.plateau_hard_pivot,
        },
        "learn_phase_slo": {
            "phase_slo_pass": bool(parts.learn_phase_slo.get("phase_slo_pass", False)),
            "required_done_ratio": float(learn_global.get("required_done_ratio", 0.0) or 0.0),
            "status": parts.learn_phase_slo.get("status", "UNAVAILABLE"),
            "reason": parts.learn_phase_slo.get("reason", ""),
        },
        "result": parts.result,
        "claim_check": parts.claim_check,
        "hitl": parts.hitl,
        "research_preflight": parts.research_preflight,
        "research_session": {},
        "route_confidence": parts.route_confidence,
        "strategy": {
            "path": parts.strategy_path,
            "forced_flow": parts.force_flow or "auto",
            "flow_ladder": ["baseline_probe", "hyper_sprint", "baseline_fallback"],
            "learn_gate_blocked": bool(parts.learn_gate_blocked),
            "baseline_probe_skipped": parts.baseline_probe_skipped,
            "plateau": parts.plateau,
            "distant_scout_plan": parts.route.get("distant_scout_plan", {}),
        },
        "artifact_summary": parts.artifact_summary,
        "success_criteria": {
            "name": parts.success_criteria_name,
            "mutation_required": parts.mutation_required,
            "verification_only_allowed": parts.verification_only_allowed,
        },
        "nexus_usage_trace": parts.nexus_usage_trace,
        "timing": {
            "cli_elapsed_sec": round(float(parts.cli_elapsed_sec), 4),
            "phase_wall_sec": parts.phase_wall_sec,
            "breakdown_sec": parts.timing_breakdown_sec,
        },
        "io": {
            "output_written": False,
            "output_path": None,
        },
    }
