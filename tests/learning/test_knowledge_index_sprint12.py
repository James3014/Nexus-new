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
    from nexus.learning.skill_schema import SkillFrontmatter
    from nexus.learning.search_strategies import SemanticSearchStrategy
    
    mock_model = MagicMock()
    mock_cache = MagicMock()
    mock_np = MagicMock()
    mock_store = MagicMock()
    
    # 設定 numpy mock 行為避免除零
    mock_np.dot.return_value = 0.9
    mock_np.linalg.norm.return_value = 1.0
    
    strategy = SemanticSearchStrategy(
        model=mock_model, cache=mock_cache,
        np_module=mock_np, model_version="v2.0"
    )
    
    fm = SkillFrontmatter(
        name="test_skill",
        description="test",
        task_id="t1",
        success_metric=MagicMock()
    )
    fm.embedding_model_version = "v1.0" # Old version vs CURRENT v2.0
    
    mock_store.list_learned_skills.return_value = ["test_skill.md"]
    mock_store.get_skill_summary.return_value = fm
    
    # Run embedding search
    strategy.search(mock_store, "query", top_k=1, threshold=0.1, task_type="")
    
    # Assert cache invalidate was called because the version mismatched
    mock_cache.invalidate.assert_called_once_with("t1")
