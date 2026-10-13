"""Nightly quarantine entry: tests/unit/local_heal/test_delegated_retry_signal.py (#1924). See package docstring."""

from __future__ import annotations

# Re-quarantined (#1924): the earlier tombstone (#2030) predates the runtime 6782e38 pin (#2016).
ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_delegated_retry_signal.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "runtime contract drift, fails in isolation under nexus-runtime 6782e38 (#2016) and 68e86ed (#2071): NEXUS_C15_JUDGE_MODEL=qwen2.5-s2t-advisor:3b is no longer admitted (runtime e5a755b retired local_advisor_3b; runtime 393d5dd resolve_judge_model fails closed with MODEL_DEFAULT_NOT_ADMITTED) so local_committee_enabled is False; owner decision pending",
    "tests": ("test_capability_planner_injects_committee_model_specs",),
}
