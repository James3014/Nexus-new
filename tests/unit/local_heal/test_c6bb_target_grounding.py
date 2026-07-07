"""
C6BB: Target grounding minimal patch.
Verifies that the astropy__astropy-13236 locked_search is grounded in real source
content, not synthetic code. RED tests first, then GREEN after grounding patch.
"""
import os
import subprocess
import pytest


# Real source file path (post-fix snapshot)
_REAL_SOURCE = "/Users/jameschen/Workspace/nexus/artifacts/external_sources/astropy_13236/astropy/table/table.py"
# Workspace git repo for pre-fix source extraction
_WORKSPACE = "/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy"
_FIX_COMMIT = "a04fb7c355"

# Cache for pre-fix source
_PRE_FIX_SOURCE: str = ""


def _read_pre_fix_source() -> str:
    """Return the pre-fix real source via git history."""
    global _PRE_FIX_SOURCE
    if not _PRE_FIX_SOURCE:
        r = subprocess.run(
            ["git", "show", f"{_FIX_COMMIT}^:astropy/table/table.py"],
            cwd=_WORKSPACE, capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"git show failed: {r.stderr}"
        _PRE_FIX_SOURCE = r.stdout
    return _PRE_FIX_SOURCE


def _read_real_source() -> str:
    with open(_REAL_SOURCE) as f:
        return f.read()


# ─── RED test 1: grounded locked_search must exist in pre-fix real source ───

def test_grounding_locked_search_exists_in_real_source():
    """C6BB (C6BD update): The benchmark's locked_search for astropy__astropy-13236
    must be findable in the pre-fix real source via git history.
    The C6BD locked_search targets the removed NdarrayMixin block (not in post-fix)."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = build_task_specs()
    astropy_spec = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    locked = astropy_spec["locked_search"]
    source = _read_pre_fix_source()
    assert locked in source, (
        f"Grounded locked_search not found in pre-fix real source.\n"
        f"locked_search (first 80 chars): {locked[:80]!r}"
    )


# ─── RED test 2: forensic classifier must NOT classify grounded input as search_span_mismatch ───

def test_grounding_not_classified_as_search_span_mismatch():
    """C6BB (C6BD update): With a grounded locked_search that exists in pre-fix
    source, the forensic classifier should NOT return search_span_mismatch."""
    from nexus.services.local_heal.local_model_executor import forensic_apply_mismatch
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = build_task_specs()
    astropy_spec = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    locked = astropy_spec["locked_search"]
    source = _read_pre_fix_source()
    result = forensic_apply_mismatch(
        apply_error="error: patch does not apply\n",
        locked_search=locked,
        source_text=source,
        target_file="astropy/table/table.py",
    )
    assert result != "search_span_mismatch", (
        f"Grounded locked_search was classified as search_span_mismatch — "
        f"grounding may be insufficient. Result: {result}"
    )


# ─── RED test 3: grounded span targets real NdarrayMixin block inside __init__ ───

def test_grounding_targets_real_ndarray_mixin_view_block():
    """C6BD: The grounded locked_search must reference the real NdarrayMixin
    view block inside Table.__init__, not the import line or synthetic code."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = build_task_specs()
    astropy_spec = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    locked = astropy_spec["locked_search"]
    assert "NdarrayMixin" in locked, "Grounded locked_search must reference NdarrayMixin"
    # Must reference the view() call, not just the import
    assert "view(NdarrayMixin)" in locked, (
        "C6BD locked_search should target the view(NdarrayMixin) block inside __init__"
    )
    # Must NOT be the old synthetic code
    assert "if hasattr(data, 'dtype')" not in locked, (
        "Grounded locked_search still contains old synthetic code"
    )
    # Must NOT be the old import-only locked_search from C6BB
    assert "from .ndarray_mixin" not in locked, (
        "C6BD locked_search should NOT be the import line (wrong_nearby_region fix)"
    )
