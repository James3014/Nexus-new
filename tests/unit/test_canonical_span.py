"""Tests for canonical_span module (T1.6/T1.8)."""

import tempfile
from pathlib import Path
from nexus.services.local_heal.canonical_span import (
    get_canonical_search_span,
    _extract_from_unified_diff,
    _extract_by_ast_boundary,
)


class TestExtractFromUnifiedDiff:
    def test_extracts_search_from_diff(self):
        diff = (
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -10,3 +10,3 @@\n"
            "-old_line_1\n"
            "-old_line_2\n"
            "+new_line_1\n"
            "+new_line_2\n"
        )
        result = _extract_from_unified_diff(diff)
        assert result is not None
        assert result.span == "old_line_1\nold_line_2"
        assert result.source == "unified_diff"
        assert result.file_path == "foo.py"

    def test_returns_none_for_empty_diff(self):
        assert _extract_from_unified_diff("") is None
        assert _extract_from_unified_diff("no diff here") is None


class TestExtractByAstBoundary:
    def test_finds_function_by_name(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                "def helper_func():\n"
                "    return 42\n"
                "\n"
                "def other_func():\n"
                "    pass\n"
            )
            f.flush()
            result = _extract_by_ast_boundary(Path(f.name), "helper_func")
            assert result is not None
            assert "def helper_func():" in result.span
            assert result.source == "ast_boundary"

    def test_returns_none_for_nonexistent_symbol(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def foo():\n    pass\n")
            f.flush()
            result = _extract_by_ast_boundary(Path(f.name), "bar")
            assert result is None


class TestGetCanonicalSearchSpan:
    def test_locked_search_takes_priority(self):
        result = get_canonical_search_span(locked_search="locked code")
        assert result is not None
        assert result.span == "locked code"
        assert result.source == "locked_search"
        assert result.confidence == 1.0

    def test_diff_extraction_fallback(self):
        diff = (
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "-old\n"
            "+new\n"
        )
        result = get_canonical_search_span(patch_diff=diff)
        assert result is not None
        assert result.span == "old"
        assert result.source == "unified_diff"

    def test_ast_boundary_fallback(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def target_func():\n    return 1\n")
            f.flush()
            result = get_canonical_search_span(
                source_file=Path(f.name),
                target_symbol="target_func",
            )
            assert result is not None
            assert "def target_func():" in result.span
            assert result.source == "ast_boundary"

    def test_returns_none_when_all_fail(self):
        result = get_canonical_search_span()
        assert result is None

    def test_telemetry_records_strategies_tried(self):
        result = get_canonical_search_span(locked_search="x")
        assert result is not None
        assert "strategies_tried" in result.telemetry
