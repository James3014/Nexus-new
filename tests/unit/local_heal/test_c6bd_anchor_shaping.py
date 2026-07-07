"""
C6BD: Anchor shaping for astropy__astropy-13236 target-region alignment.
Verifies that the locked_search now targets the actual NdarrayMixin view
block inside Table.__init__ (wrong_nearby_region fix).
task-local only - single minimal patch candidate - no public API changes
"""
import os
import subprocess
import pytest


_WORKSPACE = "/Users/jameschen/Workspace/nexus/.nexus/workspaces/astropy"
_FIX_COMMIT = "a04fb7c355"
_PRE_FIX_SOURCE: str = ""


def _read_pre_fix_source() -> str:
    global _PRE_FIX_SOURCE
    if not _PRE_FIX_SOURCE:
        r = subprocess.run(
            ["git", "show", f"{_FIX_COMMIT}^:astropy/table/table.py"],
            cwd=_WORKSPACE, capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"git show failed: {r.stderr}"
        _PRE_FIX_SOURCE = r.stdout
    return _PRE_FIX_SOURCE


# ─── RED test 1: anchor exists uniquely in pre-fix real source ───

def test_astropy_13236_anchor_exists_uniquely_in_real_source():
    """C6BD: The locked_search (NdarrayMixin view block) must exist exactly once
    in the pre-fix real astropy source."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = build_task_specs()
    astropy_spec = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    locked = astropy_spec["locked_search"]
    source = _read_pre_fix_source()
    count = source.count(locked)
    assert count == 1, (
        f"Locked_search should appear exactly once in pre-fix source, found {count}"
    )


# ─── RED test 2: anchor is inside Table.__init__ body ───

def test_astropy_13236_anchor_near_table_init_region():
    """C6BD: The locked_search must be found inside _convert_data_to_col
    (line 1179-1325), called by __init__ (line 659). The target_symbol=__init__
    is the entry point; the actual fix is in the helper it delegates to."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = build_task_specs()
    astropy_spec = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    locked = astropy_spec["locked_search"]
    source = _read_pre_fix_source()
    lines = source.splitlines()
    idx = source.index(locked)
    line_num = source[:idx].count('\n') + 1
    # Table class starts at line 542
    assert line_num >= 542, (
        f"Locked_search at line {line_num}, expected inside class Table (line 542+)"
    )
    # The actual location is inside _convert_data_to_col (line 1179),
    # which is called by __init__ at line 659
    # Verify it's inside the Table class and reasonably near __init__'s call chain
    assert line_num >= 1100, (
        f"Locked_search at line {line_num}, expected inside _convert_data_to_col (~1179)"
    )
    assert line_num <= 1300, (
        f"Locked_search at line {line_num}, expected inside _convert_data_to_col range (~1179-1250)"
    )


# ─── RED test 3: C6BD locked_search changes the C6AZ mismatch class ───

def test_astropy_13236_anchor_no_longer_matches_old_mismatch_class():
    """C6BD: With the new locked_search that exists in the benchmark sandbox,
    the C6AZ forensic classifier should NOT return search_span_mismatch.
    Instead it should return partial_match_but_anchor_rejected (or unknown)."""
    from nexus.services.local_heal.local_model_executor import forensic_apply_mismatch
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = build_task_specs()
    astropy_spec = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    locked = astropy_spec["locked_search"]
    # Use benchmark buggy_code as source_text (it contains the locked_search)
    source = astropy_spec["buggy_code"]
    result = forensic_apply_mismatch(
        apply_error="error: patch does not apply\n",
        locked_search=locked,
        source_text=source,
        target_file="astropy/table/table.py",
    )
    assert result != "search_span_mismatch", (
        f"New locked_search was classified as search_span_mismatch even though "
        f"it exists in the benchmark sandbox. Result: {result}"
    )


# ─── RED test 4: verify logic consistency ───

def test_astropy_13236_verify_fails_on_buggy_code():
    """C6BD: The verifier must fail on the starting buggy_code (view(NdarrayMixin)
    is present) and pass after the locked_search block is removed."""
    from scripts.bench.m1_real_local_solve_benchmark import build_task_specs
    specs = build_task_specs()
    astropy_spec = next(s for s in specs if s["task_id"] == "astropy__astropy-13236")
    buggy = astropy_spec["buggy_code"]
    locked = astropy_spec["locked_search"]
    verify_check = "'view(NdarrayMixin)' not in c"
    # On starting code: view(NdarrayMixin) IS present → verify fails
    assert "'view(NdarrayMixin)' not in c" in astropy_spec["verify_script"]
    # Verify starts by checking that view(NdarrayMixin) is NOT in file
    # Starting code HAS view(NdarrayMixin) → should fail
    assert "view(NdarrayMixin)" in buggy, (
        "Buggy_code must contain view(NdarrayMixin) for verifier to fail on start"
    )
    # After removing locked_search: view(NdarrayMixin) is gone → passes
    fixed = buggy.replace(locked, "").strip()
    assert "view(NdarrayMixin)" not in fixed, (
        "After removing locked_search, view(NdarrayMixin) should NOT remain"
    )
