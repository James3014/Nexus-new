"""Nightly quarantine entry: tests/unit/local_heal/test_c6av_committee_solve_reality_check.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_c6av_committee_solve_reality_check.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "runtime contract drift, fails in isolation under nexus-runtime 6782e38 (#2016) and 68e86ed (#2071): runtime e5a755b (#183/#184) retired local_advisor_3b (qwen2.5-s2t-advisor:3b, now REGISTERED_BLOCKED/UNAVAILABLE) and runtime 393d5dd (#185/#188) made CapabilityPlanner resolve the committee judge via resolve_judge_model, failing closed (MODEL_DEFAULT_NOT_ADMITTED) -> local_committee_enabled/diagnosis/audit_committee_enabled False; the bundled Workforce policy admits no ollama judge/committee worker at all, so the planner can no longer enable the committee; owner decision pending (reported to the runtime pin owner)",
    "tests": (
        "test_planner_does_not_inject_diagnosis_committee_enabled",
        "test_da_committee_gates_open_with_planner_snapshot",
    ),
}
