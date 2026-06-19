"""Tests for ast_locator module."""

import pytest
import tempfile
from pathlib import Path
from nexus.services.local_heal.ast_locator import (
    locate_symbol,
    ASTLocatorErrorKind,
)


SAMPLE_MODULE = """\
def hello():
    return "world"

class MyClass:
    def method(self):
        pass

def foo():
    return 42
"""


def test_locate_function():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_MODULE)
        f.flush()
        result = locate_symbol(f.name, "hello")
        assert result.ok is True
        assert result.kind == "function"
        assert result.span_start == 1
        assert result.span_end == 2
        assert result.source_hash is not None
        Path(f.name).unlink()


def test_locate_class():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_MODULE)
        f.flush()
        result = locate_symbol(f.name, "MyClass")
        assert result.ok is True
        assert result.kind == "class"
        Path(f.name).unlink()


def test_locate_method():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_MODULE)
        f.flush()
        result = locate_symbol(f.name, "MyClass.method")
        assert result.ok is True
        assert result.kind == "method"
        Path(f.name).unlink()


def test_symbol_not_found():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_MODULE)
        f.flush()
        result = locate_symbol(f.name, "nonexistent")
        assert result.ok is False
        assert result.error_kind == ASTLocatorErrorKind.SYMBOL_NOT_FOUND
        Path(f.name).unlink()


def test_file_not_found():
    result = locate_symbol("/nonexistent/file.py", "hello")
    assert result.ok is False
    assert result.error_kind == ASTLocatorErrorKind.FILE_NOT_FOUND


def test_syntax_error():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def broken(:\n")
        f.flush()
        result = locate_symbol(f.name, "broken")
        assert result.ok is False
        assert result.error_kind == ASTLocatorErrorKind.AST_PARSE_ERROR
        Path(f.name).unlink()


def test_source_hash_matches_span():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(SAMPLE_MODULE)
        f.flush()
        result = locate_symbol(f.name, "hello")
        assert result.ok is True
        lines = SAMPLE_MODULE.splitlines()
        span_text = "".join(lines[result.span_start - 1:result.span_end])
        import hashlib
        expected_hash = hashlib.sha256(span_text.encode()).hexdigest()[:16]
        assert result.source_hash == expected_hash
        Path(f.name).unlink()
