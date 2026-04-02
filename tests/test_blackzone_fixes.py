from pathlib import Path
"""Tests for Sprint 1 Black Zone fixes."""
import json
import tempfile
import logging

def test_streaming_count_handles_large_file():
    """Fix 1: count_successful_uses 能處理大型 JSONL 且不會一次載入記憶體"""
    from nexus.learning.skill_lifecycle import count_successful_uses
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / ".usage_log.jsonl"
        with open(log_path, "w", encoding="utf-8") as f:
            for i in range(1000):
                f.write(json.dumps({"skill_id": "test-bug-1", "outcome": "success"}) + "\n")
                f.write(json.dumps({"skill_id": "other-bug", "outcome": "success"}) + "\n")
        
        # Should count 1000 properly without loading entire file into memory string
        assert count_successful_uses(Path(tmpdir), "test-bug-1") == 1000


def test_promote_doesnt_corrupt_body():
    """Fix 3: promote_skill 的 trust_level 替換不會篡改文件本體中同名文字"""
    from nexus.learning.skill_lifecycle import promote_skill
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        skills_dir.mkdir(exist_ok=True)
        # Create a dummy skill log count to pass L2 requirements if tested
        # But here we just want to ensure string replacement behaves correctly.
        skill_path = skills_dir / "test.md"
        content = '---\nname: test\ntrust_level: auto-generated\n---\n# Body\n這是一份說明文件。其中提到了 trust_level: auto-generated 作為範例。\n'
        skill_path.write_text(content, encoding="utf-8")
        
        result = promote_skill(skills_dir, "test", "reviewed")
        assert result["success"] == True
        
        updated = skill_path.read_text(encoding="utf-8")
        # 標題區的變更成功
        assert "trust_level: reviewed" in updated.split("---")[1]
        # Body 區的相同字眼不會被修改
        assert " trust_level: auto-generated 作為範例" in updated


def test_silent_exceptions_log_warning(caplog):
    """Fix 4: 異常不再靜默，logger.warning 應被觸發"""
    from nexus.learning.skill_store import SkillStore
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "skills" / "learned"
        skills_dir.mkdir(parents=True)
        malformed = skills_dir / "bad.md"
        malformed.write_text("---not valid yaml at all : {{{\n---", encoding="utf-8")
        
        store = SkillStore(Path(tmpdir))
        with caplog.at_level(logging.WARNING):
            result = store.get_skill_summary("bad.md")
        
        assert result is None
        assert "skill_frontmatter_parse_failed" in caplog.text
        assert "bad.md" in caplog.text
