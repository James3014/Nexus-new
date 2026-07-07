"""
C6AZ: Apply mismatch forensics.
Forensic-only tests for the apply failure classifier.
This task is forensic-only. No behavior-changing patch shipped.
"""
import pytest
from nexus.services.local_heal.local_model_executor import forensic_apply_mismatch


# ─── Case 1: locked_search not in source → search_span_mismatch ───

def test_locked_search_absent_from_source_classifies_as_search_span_mismatch():
    """C6AZ astropy-13236 real case: locked_search is synthetic code that
    doesn't exist in the 4247-line real source file."""
    apply_error = "error: patch failed: astropy/table/table.py:4\nerror: astropy/table/table.py: patch does not apply\n"
    locked_search = "if hasattr(data, 'dtype') and len(getattr(data, 'dtype', [])) > 1:\n            self._data = data.view(type('NdarrayMixin', (), {}))"
    source_text = "# Licensed under a 3-clause BSD style license\nimport itertools\nimport sys\nimport types\n"
    result = forensic_apply_mismatch(
        apply_error=apply_error,
        locked_search=locked_search,
        source_text=source_text,
        target_file="astropy/table/table.py",
    )
    assert result == "search_span_mismatch"


# ─── Case 2: corrupt patch → syntax_shape_invalid ───

def test_corrupt_patch_classifies_as_syntax_shape_invalid():
    apply_error = "error: corrupt patch at line 6"
    result = forensic_apply_mismatch(
        apply_error=apply_error,
        locked_search="some code",
        source_text="some code\nmore code",
        target_file="mod.py",
    )
    assert result == "syntax_shape_invalid"


# ─── Case 3: wrong target file → wrong_target_file ───

def test_wrong_target_file_classifies_correctly():
    apply_error = "error: no such file or directory: wrong/path.py"
    result = forensic_apply_mismatch(
        apply_error=apply_error,
        locked_search="x = 1",
        source_text="x = 1",
        target_file="correct/path.py",
    )
    assert result == "wrong_target_file"


# ─── Case 4: partial match but anchor rejected ───

def test_partial_match_classifies_as_partial_match_but_anchor_rejected():
    apply_error = "error: patch does not apply\n"
    locked_search = "def compute(self, x, y, z):\n    result = x * y\n    return result + offset_constant"
    # Source has first 50 chars but diverges at 'offset_constant' vs 'different_value'
    source_text = "def compute(self, x, y, z):\n    result = x * y\n    return result + different_value"
    result = forensic_apply_mismatch(
        apply_error=apply_error,
        locked_search=locked_search,
        source_text=source_text,
        target_file="mod.py",
    )
    assert result == "partial_match_but_anchor_rejected"


# ─── Case 5: unknown apply failure ───

def test_unknown_error_classifies_as_unknown():
    result = forensic_apply_mismatch(
        apply_error="some weird error",
        locked_search="x = 1",
        source_text="x = 1",
        target_file="mod.py",
    )
    assert result == "unknown_apply_failure"


# ─── Forensic verification: C6AX and C6AY both hit same root cause ───

def test_c6ax_c6ay_both_classify_as_search_span_mismatch():
    """Both C6AX and C6AY live runs had identical apply errors and the same
    locked_search that doesn't exist in the real source file."""
    apply_error = "error: patch failed: astropy/table/table.py:4\nerror: astropy/table/table.py: patch does not apply\n"
    locked_search = "if hasattr(data, 'dtype') and len(getattr(data, 'dtype', [])) > 1:\n            self._data = data.view(type('NdarrayMixin', (), {'__array__': lambda self: self._data})())"
    # Real source file first 10 lines (line 4 = import types)
    real_source = "# Licensed under a 3-clause BSD style license - see LICENSE.rst\nimport itertools\nimport sys\nimport types\nimport warnings\nimport weakref\n"
    result = forensic_apply_mismatch(
        apply_error=apply_error,
        locked_search=locked_search,
        source_text=real_source,
        target_file="astropy/table/table.py",
    )
    assert result == "search_span_mismatch"
