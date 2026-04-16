import pytest
from pathlib import Path
from scripts.ops.content_quality_gate import check_content_quality

def test_quality_fail_too_thin(tmp_path):
    f = tmp_path / "thin.md"
    f.write_text("# Only a title", encoding="utf-8")
    ok, reason = check_content_quality(f, 100, 3, [])
    assert ok is False
    assert "Content too thin" in reason

def test_quality_fail_blacklist(tmp_path):
    f = tmp_path / "bad.md"
    f.write_text("高品質重鑄執行中\n\nMore text here to pass word count check with many many words to exceed the threshold", encoding="utf-8")
    # Fix the newlines in the test write
    f.write_text("高品質重鑄執行中\n\nMore text here to pass word count check with many many words to exceed the threshold".replace('\\n', '\n'), encoding="utf-8")
    ok, reason = check_content_quality(f, 10, 2, ["高品質重鑄執行中"])
    assert ok is False
    assert "Prohibited" in reason

def test_quality_pass_valid(tmp_path):
    f = tmp_path / "good.md"
    content = "# Title\n\nFirst paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
    f.write_text(content, encoding="utf-8")
    ok, reason = check_content_quality(f, 10, 3, ["None"])
    assert ok is True
