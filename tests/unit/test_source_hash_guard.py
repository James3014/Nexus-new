"""Tests for source_hash_guard module."""

import pytest
import tempfile
from pathlib import Path
from nexus.services.local_heal.source_hash_guard import (
    compute_span_hash,
    verify_span_hash,
    preview_line_span_replacement,
    apply_line_span_replacement,
    SourceHashGuardErrorKind,
)


SAMPLE_CODE = """\
def hello():
    return "world"

def foo():
    return 42
"""


def test_compute_stable_hash():
    lines = SAMPLE_CODE.splitlines(keepends=True)
    h1 = compute_span_hash(lines, 1, 2)
    h2 = compute_span_hash(lines, 1, 2)
    assert h1 == h2
    assert len(h1) == 16


def test_verify_hash_correct():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_CODE)
        f.flush()
        lines = SAMPLE_CODE.splitlines(keepends=True)
        expected = compute_span_hash(lines, 1, 2)
        result = verify_span_hash(f.name, 1, 2, expected)
        assert result.ok is True
        assert result.ast_valid is None
        Path(f.name).unlink()


def test_verify_hash_wrong():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_CODE)
        f.flush()
        result = verify_span_hash(f.name, 1, 2, "wrong_hash")
        assert result.ok is False
        assert result.error_kind == SourceHashGuardErrorKind.SOURCE_STALE
        Path(f.name).unlink()


def test_verify_hash_file_not_found():
    result = verify_span_hash("/nonexistent/file.py", 1, 2, "abc")
    assert result.ok is False
    assert result.error_kind == SourceHashGuardErrorKind.FILE_NOT_FOUND


def test_verify_hash_span_out_of_range():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_CODE)
        f.flush()
        result = verify_span_hash(f.name, 1, 100, "abc")
        assert result.ok is False
        assert result.error_kind == SourceHashGuardErrorKind.SPAN_OUT_OF_RANGE
        Path(f.name).unlink()


def test_preview_does_not_write():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_CODE)
        f.flush()
        original = Path(f.name).read_text()
        lines = SAMPLE_CODE.splitlines(keepends=True)
        h = compute_span_hash(lines, 1, 2)
        result = preview_line_span_replacement(f.name, 1, 2, "replaced")
        assert result.ok is True
        assert result.wrote_file is False
        assert Path(f.name).read_text() == original
        Path(f.name).unlink()


def test_apply_write_false_does_not_write():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_CODE)
        f.flush()
        original = Path(f.name).read_text()
        lines = SAMPLE_CODE.splitlines(keepends=True)
        h = compute_span_hash(lines, 1, 2)
        result = apply_line_span_replacement(f.name, 1, 2, h, "replaced", write=False)
        assert result.ok is True
        assert result.wrote_file is False
        assert Path(f.name).read_text() == original
        Path(f.name).unlink()


def test_preview_ast_invalid():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_CODE)
        f.flush()
        lines = SAMPLE_CODE.splitlines(keepends=True)
        result = preview_line_span_replacement(f.name, 1, 2, "def broken(:\n")
        assert result.ok is False
        assert result.error_kind == SourceHashGuardErrorKind.AST_INVALID
        Path(f.name).unlink()
