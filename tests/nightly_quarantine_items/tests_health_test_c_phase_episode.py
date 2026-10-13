"""Nightly quarantine entry: tests/health/test_c_phase_episode.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/health/test_c_phase_episode.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_record_episode_falls_back_to_review_status_when_flag_missing",
        "test_record_episode_prefers_pipeline_success_flag",
    ),
}
