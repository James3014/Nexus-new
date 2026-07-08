from __future__ import annotations

import pytest
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol


def test_classify_format_empty_via_output_understanding():
    assert SolidSearchReplaceProtocol.classify_format("") == "EMPTY"
    assert SolidSearchReplaceProtocol.classify_format("   ") == "EMPTY"


def test_classify_format_refusal_via_output_understanding():
    raw = "I apologize, but I cannot fix this issue."
    assert SolidSearchReplaceProtocol.classify_format(raw) == "REFUSAL"


def test_classify_format_unified_diff_via_output_understanding():
    raw = "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n"
    assert SolidSearchReplaceProtocol.classify_format(raw) == "UNIFIED_DIFF"


def test_classify_format_search_replace_via_output_understanding():
    raw = "<<<<<<< SEARCH\nold code\n=======\nnew code\n>>>>>>> REPLACE"
    assert SolidSearchReplaceProtocol.classify_format(raw) == "VALID_SEARCH_REPLACE"


def test_classify_format_fenced_search_replace_via_output_understanding():
    raw = "```python\n<<<<<<< SEARCH\nold code\n=======\nnew code\n>>>>>>> REPLACE\n```"
    assert SolidSearchReplaceProtocol.classify_format(raw) == "FENCED_SEARCH_REPLACE"


def test_classify_format_malformed_search_replace_preserved():
    raw = "<<<<<<< SEARCH\nold code"
    assert SolidSearchReplaceProtocol.classify_format(raw) == "MALFORMED_SEARCH_REPLACE"


def test_classify_format_markdown_fenced_preserved():
    raw = "```python\nx = 1\n```"
    assert SolidSearchReplaceProtocol.classify_format(raw) == "MARKDOWN_FENCED"


def test_classify_format_plain_text_preserved():
    raw = "def foo():\n    return 42"
    assert SolidSearchReplaceProtocol.classify_format(raw) == "PLAIN_TEXT"


def test_classify_format_natural_language_preserved():
    raw = "The quick brown fox jumps over the lazy dog."
    assert SolidSearchReplaceProtocol.classify_format(raw) == "NATURAL_LANGUAGE"


@pytest.mark.parametrize("raw,expected", [
    ("", "EMPTY"),
    ("   ", "EMPTY"),
    ("I apologize, but I cannot fix this.", "REFUSAL"),
    ("--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n old\n-new\n+new\n", "UNIFIED_DIFF"),
    ("<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE", "VALID_SEARCH_REPLACE"),
    ("```python\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n```", "FENCED_SEARCH_REPLACE"),
    ("<<<<<<< SEARCH\nold", "MALFORMED_SEARCH_REPLACE"),
    ("```python\nx = 1\n```", "MARKDOWN_FENCED"),
    ("def foo():\n    return 42", "PLAIN_TEXT"),
    ("The quick brown fox.", "NATURAL_LANGUAGE"),
])
def test_classify_format_returns_same_as_old_for_all_cases(raw, expected):
    assert SolidSearchReplaceProtocol.classify_format(raw) == expected
