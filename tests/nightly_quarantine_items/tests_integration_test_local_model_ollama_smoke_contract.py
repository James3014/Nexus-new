"""Nightly quarantine entry: tests/integration/test_local_model_ollama_smoke_contract.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_local_model_ollama_smoke_contract.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_ollama_smoke_advisory_contract",
        "test_ollama_smoke_candidate_contract",
    ),
}
