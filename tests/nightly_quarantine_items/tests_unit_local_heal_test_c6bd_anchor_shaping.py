"""Nightly quarantine entry: tests/unit/local_heal/test_c6bd_anchor_shaping.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_c6bd_anchor_shaping.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe (M4 only): hard-codes the astropy git workspace /Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy and runs git show a04fb7c355^:astropy/table/table.py there; fails on any other host, Mac mini included (re-checked 2026-10-14); cannot be rebuilt in tmp without cloning astropy",
    "tests": (
        "test_astropy_13236_anchor_exists_uniquely_in_real_source",
        "test_astropy_13236_anchor_near_table_init_region",
    ),
}
