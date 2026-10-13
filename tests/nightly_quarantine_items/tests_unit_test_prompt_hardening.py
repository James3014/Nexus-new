"""Nightly quarantine entry: tests/unit/test_prompt_hardening.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/test_prompt_hardening.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_system_prompt_contains_anti_apology",
        "test_system_prompt_contains_senior_engineering_rules",
    ),
}
