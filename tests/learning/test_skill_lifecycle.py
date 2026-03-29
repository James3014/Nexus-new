"""Tests for skill_lifecycle.py"""

import json
import tempfile
from pathlib import Path

from nexus.learning.skill_lifecycle import (
    record_usage,
    count_successful_uses,
    promote_skill,
    archive_skill,
    auto_promote_all,
    get_skills_stats,
    USAGE_LOG_FILENAME,
)


def _create_mock_skill(skills_dir: Path, skill_id: str, trust_level: str = "auto-generated", safe: bool = True) -> Path:
    content = f"""---
name: {skill_id}
description: "Test skill"
trust_level: {trust_level}
task_id: {skill_id}
---
# {skill_id}
Some safe content.
"""
    if not safe:
        content += "\nsudo rm -rf /dangerous\n"
    path = skills_dir / f"{skill_id}.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_record_and_count_usage():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        record_usage(skills_dir, "skill-1", "task-a", "success")
        record_usage(skills_dir, "skill-1", "task-b", "success")
        record_usage(skills_dir, "skill-1", "task-c", "failure")
        record_usage(skills_dir, "skill-2", "task-d", "success")

        assert count_successful_uses(skills_dir, "skill-1") == 2
        assert count_successful_uses(skills_dir, "skill-2") == 1
        assert count_successful_uses(skills_dir, "skill-3") == 0


def test_promote_skill_sequential():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        _create_mock_skill(skills_dir, "s1", "auto-generated")

        # auto-generated -> reviewed (human approval, always allowed)
        result = promote_skill(skills_dir, "s1", "reviewed")
        assert result["success"] is True

        # reviewed -> tested (needs 1 successful use + scan)
        record_usage(skills_dir, "s1", "t1", "success")
        result = promote_skill(skills_dir, "s1", "tested")
        assert result["success"] is True

        # tested -> production (needs 3 successful uses + scan)
        record_usage(skills_dir, "s1", "t2", "success")
        record_usage(skills_dir, "s1", "t3", "success")
        result = promote_skill(skills_dir, "s1", "production")
        assert result["success"] is True


def test_promote_blocks_skip():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        _create_mock_skill(skills_dir, "s1", "auto-generated")

        # Cannot skip levels
        result = promote_skill(skills_dir, "s1", "tested")
        assert result["success"] is False


def test_promote_blocks_unsafe():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        _create_mock_skill(skills_dir, "s1", "reviewed", safe=False)
        record_usage(skills_dir, "s1", "t1", "success")

        # Unsafe skills cannot be promoted to tested
        result = promote_skill(skills_dir, "s1", "tested")
        assert result["success"] is False
        assert "安全掃描" in result["message"]


def test_archive_skill():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / "learned"
        skills_dir.mkdir()
        _create_mock_skill(skills_dir, "old-skill")

        result = archive_skill(skills_dir, "old-skill")
        assert result["success"] is True
        assert not (skills_dir / "old-skill.md").exists()
        assert (skills_dir.parent / "archived" / "old-skill.md").exists()


def test_get_skills_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir)
        _create_mock_skill(skills_dir, "s1", "auto-generated")
        _create_mock_skill(skills_dir, "s2", "reviewed")
        _create_mock_skill(skills_dir, "s3", "production")

        stats = get_skills_stats(skills_dir)
        assert stats["total"] == 3
        assert stats["by_level"]["auto-generated"] == 1
        assert stats["by_level"]["reviewed"] == 1
        assert stats["by_level"]["production"] == 1
        assert stats["scan_results"]["safe"] == 3
