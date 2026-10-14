"""Nightly quarantine entry: tests/unit/local_heal/test_c6bb_target_grounding.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_c6bb_target_grounding.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe (M4 only): hard-codes /Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy (git show a04fb7c355^:astropy/table/table.py) and /Users/jameschen/Workspace/nexus/artifacts/external_sources/astropy_13236/astropy/table/table.py; fails on any other host, Mac mini included (re-checked 2026-10-14); cannot be rebuilt in tmp without cloning astropy",
    "tests": (
        "test_grounding_locked_search_exists_in_real_source",
        "test_grounding_not_classified_as_search_span_mismatch",
    ),
}
