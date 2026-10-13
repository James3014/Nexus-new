"""Nightly quarantine entry: tests/unit/local_heal/test_c6aw_da_committee_runtime_activation.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_c6aw_da_committee_runtime_activation.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "runtime contract drift, fails in isolation under nexus-runtime 6782e38 (#2016) and 68e86ed (#2071): runtime e5a755b (#183/#184) retired local_advisor_3b (qwen2.5-s2t-advisor:3b) and runtime 393d5dd (#185/#188) fails the committee judge closed (MODEL_DEFAULT_NOT_ADMITTED) -> planner sets local/diagnosis/audit_committee_enabled False; no admitted ollama judge worker exists in the bundled Workforce policy; owner decision pending",
    "tests": (
        "test_planner_injects_diagnosis_committee_enabled",
        "test_planner_injects_audit_committee_enabled",
        "test_local_committee_only_branch_bridges_da_committee",
    ),
}
