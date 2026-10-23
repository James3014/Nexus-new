"""Nightly quarantine entry: tests/ops/test_stage_f_flow.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/ops/test_stage_f_flow.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "end-to-end delivery gate against the live checkout: needs a local main branch (CI checkout lacks it, git exit 128), runs the functional suite inside, and seals governance / writes .nexus state without restoring it",
    "tests": ("test_stage_f",),
}
