"""Fuzzy fallback must replace exactly the matched file lines or refuse (#3099 residual)."""

from __future__ import annotations

from nexus.engine.patch.apply_engine import PatchApplyEngine
from nexus.engine.patch.bounded_fuzzy_applier import BoundedFuzzyApplier

LINES = [f"value_{i} = compute_something({i})" for i in range(10)]


def _block(search: str, replace: str) -> str:
    return f"<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE\n"


def _calc(lines):
    return "\n".join(line.replace("compute", "calc") for line in lines)


def _apply(tmp_path, raw: bytes, search: str, replace: str):
    (tmp_path / "t.py").write_bytes(raw)
    result = PatchApplyEngine(tmp_path).apply_patch("t", "t.py", _block(search, replace))
    return result, (tmp_path / "t.py").read_bytes()


def test_fuzzy_apply_on_mixed_line_endings_leaves_no_duplicated_line(tmp_path):
    raw = ("\n".join(LINES[:7]) + "\r\n" + "\n".join(LINES[7:]) + "\n").encode()
    result, after = _apply(tmp_path, raw, "\n".join(LINES[1:8]), _calc(LINES[1:8]))
    assert after.count(b"value_7 =") == 1, after
    assert result["success"] is True
    assert after.count(b"\r\n") == 1 and after.count(b"\n") == 10
    expected = raw
    for i in range(1, 8):
        expected = expected.replace(LINES[i].encode(), LINES[i].replace("compute", "calc").encode())
    assert after == expected


def test_fuzzy_apply_with_trailing_whitespace_in_file_replaces_exact_lines(tmp_path):
    raw = ("\n".join(LINES[:9]) + "   \n" + LINES[9] + "\n").encode()
    result, after = _apply(tmp_path, raw, "\n".join(LINES), _calc(LINES))
    assert result["success"] is True
    assert after == (_calc(LINES) + "\n").encode()


def test_fuzzy_apply_refuses_when_search_has_no_matching_lines(tmp_path):
    raw = ("\n".join(LINES) + "\n").encode()
    search = "\n".join(LINES[:6] + ["value_6 = something_else(6)"])
    result, after = _apply(tmp_path, raw, search, "x = 1")
    assert result["success"] is False
    assert after == raw


def test_fuzzy_apply_refuses_ambiguous_match():
    content = "a = 1  \nb = 2\nc = 3\na = 1\nb = 2  \n"
    ok, out, _ = BoundedFuzzyApplier().fuzzy_match_and_replace(content, "a = 1\nb = 2", "z = 0")
    assert ok is False and out == content


def test_fuzzy_replace_keeps_crlf_of_replaced_lines():
    content = "x\r\nold1 \r\nold2\r\ny\r\nz\n"
    ok, out, _ = BoundedFuzzyApplier().fuzzy_match_and_replace(
        content, "old1\nold2", "new1\nnew2\nnew3"
    )
    assert ok is True
    assert out == "x\r\nnew1\r\nnew2\r\nnew3\r\ny\r\nz\n"


def test_fuzzy_apply_refuses_blank_search():
    content = "a\n\n\nb\n"
    ok, out, _ = BoundedFuzzyApplier().fuzzy_match_and_replace(content, "\n", "z")
    assert ok is False and out == content


def test_fuzzy_replace_with_fewer_lines_keeps_the_last_line_ending():
    content = "a\r\nb\r\nc\nd\n"
    ok, out, _ = BoundedFuzzyApplier().fuzzy_match_and_replace(content, "a\nb\nc", "X\nY")
    assert ok
    assert out == "X\r\nY\nd\n"


def test_fuzzy_replace_with_empty_text_leaves_one_empty_line_like_exact_apply():
    content = "a \nb\nc\nd\n"
    ok, out, _ = BoundedFuzzyApplier().fuzzy_match_and_replace(content, "a\nb\nc", "")
    assert ok
    assert out == "\nd\n"
    assert "a\nb\nc\nd\n".replace("a\nb\nc", "", 1) == out
