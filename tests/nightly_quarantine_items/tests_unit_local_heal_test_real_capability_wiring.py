"""Nightly quarantine entry: tests/unit/local_heal/test_real_capability_wiring.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_real_capability_wiring.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_memory_retrieval_rejects_fake_lesson_without_provenance",
        "test_memory_success_and_failure_lessons_change_anchor_score",
    ),
}
