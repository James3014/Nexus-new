"""Nightly quarantine entry: tests/unit/local_heal/test_c6bb_target_grounding.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_c6bb_target_grounding.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: needs the real astropy git workspace (.nexus/workspaces/astropy at fix commit a04fb7c355) to read pre-fix source; cannot be rebuilt in tmp without cloning astropy",
    "tests": (
        "test_grounding_locked_search_exists_in_real_source",
        "test_grounding_not_classified_as_search_span_mismatch",
    ),
}
