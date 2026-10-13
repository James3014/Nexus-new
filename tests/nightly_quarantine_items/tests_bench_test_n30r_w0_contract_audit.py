"""Nightly quarantine entry: tests/bench/test_n30r_w0_contract_audit.py (#1925). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/bench/test_n30r_w0_contract_audit.py",
    "disposition": "quarantine",
    "issue": "#1925",
    "cause": "not the source_hash drift: planner now returns execution_topology ASSISTED_CANONICAL (expected localheal_pipeline) so the W0 lane makes no provider call; same stale-topology family as #1924, needs owner fix-or-delete decision",
    "tests": (
        "test_w0_records_actual_provider_prompt",
        "test_w0_records_exact_planner_output",
    ),
}
