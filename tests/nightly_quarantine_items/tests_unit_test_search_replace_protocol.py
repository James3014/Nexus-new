"""Nightly quarantine entry: tests/unit/test_search_replace_protocol.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/test_search_replace_protocol.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_protocol_validate_match_chain_fallback",
        "test_protocol_validate_placeholder_in_replace",
        "test_protocol_validate_placeholder_in_search",
    ),
}
