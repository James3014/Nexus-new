"""Nightly quarantine entry: tests/test_nightshift_local_convergence.py (#1929). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/test_nightshift_local_convergence.py",
    "disposition": "quarantine",
    "issue": "#1929",
    "cause": "fixture Gateway is classified physical, so Workforce Admission blocks the online call (GENERATION_FAILED); also AutoResearchNightShift.hub is None without an explicit context_hub; needs governed admission fixtures or an owner decision",
    "tests": (
        "test_run_round_generates_validated_scored_candidate",
        "test_run_round_rejects_ast_no_change",
    ),
}
