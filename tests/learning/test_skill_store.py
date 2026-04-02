from pathlib import Path
import pytest
from nexus.learning.skill_store import SkillStore
from nexus.learning.skill_schema import SkillFrontmatter
import tempfile

def test_skill_store_operations():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        store = SkillStore(tmp_path)
        
        assert store.skills_dir.exists()
        
        # Test listing empty
        assert len(store.list_learned_skills()) == 0
        
        # Write a dummy skill
        skill_content = """---
name: test-skill
description: "A test skill"
task_id: task-1
source: nexus-auto-crystal
trust_level: auto-generated
task_type: unknown
success_metric:
  repair_success: true
  retry_count: 1
  pattern_reuse_rate: 0.0
---
# Body
Hello"""
        (store.skills_dir / "test-skill.md").write_text(skill_content)
        
        # Test list
        skills = store.list_learned_skills()
        assert len(skills) == 1
        assert skills[0] == "test-skill.md"
        
        # Test get summary
        fm = store.get_skill_summary("test-skill.md")
        assert fm is not None
        assert fm.name == "test-skill"
        assert fm.success_metric.retry_count == 1
        
        # Test delete
        deleted = store.delete_skill("test-skill.md")
        assert deleted is True
        assert len(store.list_learned_skills()) == 0
        
        # Test delete non-existent
        assert store.delete_skill("non-existent.md") is False
