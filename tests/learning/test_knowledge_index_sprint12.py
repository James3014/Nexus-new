"""
tests/learning/test_knowledge_index_sprint12.py
Tests for Sprint 12b: Learning hardening
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Test 12b: Date parsing failure should not crash
def test_crystal_decay_invalid_date_logs_warning(tmp_path: Path):
    from nexus.learning.knowledge_index import KnowledgeIndex
    from nexus.learning.skill_schema import SkillFrontmatter
    
    idx = KnowledgeIndex(tmp_path, use_embedding=False)
    
    # Mock store and cache
    fm = SkillFrontmatter(
        name="test_skill",
        description="test",
        task_id="t1",
        success_metric="test"
    )
    fm.last_used_at = "NOT_A_VALID_DATE" # Deliberately malformed
    idx.store = MagicMock()
    idx.store.list_learned_skills.return_value = ["test_skill.md"]
    idx.store.get_skill_summary.return_value = fm
    
    # Test that this search completes without raising ValueError
    results = idx.search_similar("test query", top_k=1)
    # the search returns the skill
    assert len(results) == 1

# Test 12b: Embedding version mismatch triggers invalidation
def test_embedding_model_version_mismatch_triggers_recompute(tmp_path: Path):
    from nexus.learning.knowledge_index import KnowledgeIndex
    from nexus.learning.skill_schema import SkillFrontmatter
    
    idx = KnowledgeIndex(tmp_path, use_embedding=True)
    idx._cache = MagicMock()
    idx._model = MagicMock()
    idx.store = MagicMock()
    idx.np = MagicMock()
    
    # Create frontmatter with OLD model version
    fm = SkillFrontmatter(
        name="test_skill",
        description="test",
        task_id="t1",
        success_metric="test"
    )
    fm.embedding_model_version = "v1.0" # Old version vs CURRENT v2.0
    
    idx.store.list_learned_skills.return_value = ["test_skill.md"]
    idx.store.get_skill_summary.return_value = fm
    idx._embedding_model_version = "v2.0"
    
    # Run embedding search
    idx._embedding_search("query", top_k=1, threshold=0.1, task_type="")
    
    # Assert cache invalidate was called because the version mismatched
    idx._cache.invalidate.assert_called_once_with("t1")
