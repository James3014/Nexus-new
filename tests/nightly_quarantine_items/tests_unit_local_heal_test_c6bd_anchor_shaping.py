"""Nightly quarantine entry: tests/unit/local_heal/test_c6bd_anchor_shaping.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_c6bd_anchor_shaping.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: needs the real astropy git workspace (.nexus/workspaces/astropy at fix commit a04fb7c355) to read pre-fix source; cannot be rebuilt in tmp without cloning astropy",
    "tests": (
        "test_astropy_13236_anchor_exists_uniquely_in_real_source",
        "test_astropy_13236_anchor_near_table_init_region",
    ),
}
