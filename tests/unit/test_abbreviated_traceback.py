"""Tests for abbreviated_traceback module."""

import pytest
from nexus.services.local_heal.abbreviated_traceback import (
    format_abbreviated_traceback,
    AbbreviatedTracebackErrorKind,
)


SAMPLE_TRACEBACK = """\
Traceback (most recent call last):
  File "test_column.py", line 100, in test_quantity_comparison
    assert a > b
AssertionError: 5 not greater than 10
FAILED astropy/table/tests/test_column.py::TestColumn::test_quantity_comparison
"""

LONG_TRACEBACK = """\
Traceback (most recent call last):
  File "/usr/lib/python3.11/site-packages/astropy/units/core.py", line 100, in __call__
    raise UnitConversionError(msg)
astropy.units.core.UnitConversionError: Can only apply 'greater' function to dimensionless quantities
  File "test_column.py", line 100, in test_quantity_comparison
    assert a > b
FAILED astropy/table/tests/test_column.py::TestColumn::test_quantity_comparison
""" * 5


def test_basic_formatting():
    result = format_abbreviated_traceback(SAMPLE_TRACEBACK, "semantic_wrong")
    assert result.error_type == "AssertionError"
    assert "5 not greater than 10" in result.message
    assert result.failure_class == "semantic_wrong"
    assert result.truncated is False


def test_failure_class_preserved():
    result = format_abbreviated_traceback(SAMPLE_TRACEBACK, "verifier_rejection")
    assert result.failure_class == "verifier_rejection"
    assert result.verifier_verdict == "VERIFIER_REJECTED"


def test_target_file_extracted():
    result = format_abbreviated_traceback(SAMPLE_TRACEBACK, "semantic_wrong")
    assert result.target_file == "test_column.py"


def test_assertion_diff_extracted():
    result = format_abbreviated_traceback(SAMPLE_TRACEBACK, "semantic_wrong")
    assert result.assertion_diff is not None


def test_max_chars_enforced():
    result = format_abbreviated_traceback(LONG_TRACEBACK, "semantic_wrong", max_chars=200)
    assert result.truncated is True
    assert result.char_count <= 200 + len("\n... (truncated)")


def test_recent_patch_diff_included():
    diff = "--- old\n+++ new\n@@ -1 +1 @@\n-old\n+new"
    result = format_abbreviated_traceback(SAMPLE_TRACEBACK, "semantic_wrong", recent_patch_diff=diff)
    assert result.recent_patch_diff == diff


def test_target_lines_included():
    result = format_abbreviated_traceback(SAMPLE_TRACEBACK, "semantic_wrong", target_lines=["line1", "line2"])
    assert result.target_lines == ["line1", "line2"]


def test_empty_traceback_handled():
    result = format_abbreviated_traceback("", "semantic_wrong")
    assert result.error_type == "EmptyTraceback"
    assert result.char_count == 0


def test_unrelated_stack_not_flooded():
    result = format_abbreviated_traceback(LONG_TRACEBACK, "semantic_wrong", max_chars=500)
    assert "site-packages" not in result.minimized_stack or result.truncated
