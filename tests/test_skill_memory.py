"""Tests for Skill Memory Query Layer."""
import json
import pytest
from pathlib import Path
from nexus.learning.skill_memory_index import SkillMemoryIndex, SkillHistoryRecord


@pytest.fixture
def skill_memory_project(tmp_path):
    """Create a temporary project with skill memory data."""
    # Create outcome events
    metrics_dir = tmp_path / ".nexus" / "metrics"
    metrics_dir.mkdir(parents=True)
    
    outcomes = [
        {"skill_id": "test-skill-a", "pass": True, "status": "success", "task_id": "t1"},
        {"skill_id": "test-skill-a", "pass": True, "status": "success", "task_id": "t2"},
        {"skill_id": "test-skill-a", "pass": False, "status": "SEARCH_MISMATCH", "task_id": "t3"},
        {"skill_id": "test-skill-b", "pass": True, "status": "success", "task_id": "t4"},
    ]
    with open(metrics_dir / "skill_outcome_events.jsonl", "w") as f:
        for e in outcomes:
            f.write(json.dumps(e) + "\n")
    
    # Create usage events
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    
    usage_events = [
        {"skill_id": "test-skill-a", "used_at": "2026-06-14T10:00:00Z", "task_id": "t1", "outcome": "success"},
        {"skill_id": "test-skill-a", "used_at": "2026-06-14T11:00:00Z", "task_id": "t2", "outcome": "success"},
        {"skill_id": "test-skill-b", "used_at": "2026-06-14T12:00:00Z", "task_id": "t4", "outcome": "success"},
    ]
    with open(skills_dir / ".usage_log.jsonl", "w") as f:
        for e in usage_events:
            f.write(json.dumps(e) + "\n")
    
    return tmp_path


def test_skill_memory_index_load(skill_memory_project):
    """Index loads data correctly."""
    index = SkillMemoryIndex(skill_memory_project)
    index._load()
    assert len(index._outcome_cache) == 4
    assert len(index._usage_cache) == 3


def test_query_skill_history(skill_memory_project):
    """Query returns correct history for a skill."""
    index = SkillMemoryIndex(skill_memory_project)
    record = index.query_skill_history("test-skill-a")
    
    assert record.skill_id == "test-skill-a"
    assert record.recent_success_rate == pytest.approx(2/3, abs=0.01)
    assert record.reuse_count == 2
    assert "SEARCH_MISMATCH" in record.recent_failure_modes


def test_query_unknown_skill(skill_memory_project):
    """Query unknown skill returns empty record."""
    index = SkillMemoryIndex(skill_memory_project)
    record = index.query_skill_history("unknown-skill")
    
    assert record.skill_id == "unknown-skill"
    assert record.recent_success_rate == 0.0
    assert record.reuse_count == 0


def test_query_contextual_candidates(skill_memory_project):
    """Query returns ranked candidates."""
    index = SkillMemoryIndex(skill_memory_project)
    candidates = index.query_contextual_skill_candidates("test task", top_k=5)
    
    assert len(candidates) == 2
    # test-skill-a should rank higher (more uses, good success rate)
    assert candidates[0].skill_id == "test-skill-a"


def test_query_failure_patterns(skill_memory_project):
    """Query returns failure patterns."""
    index = SkillMemoryIndex(skill_memory_project)
    patterns = index.query_failure_patterns("test-skill-a")
    
    assert len(patterns) > 0
    assert patterns[0][0] == "SEARCH_MISMATCH"


def test_build_context_injection(skill_memory_project):
    """Context injection builds readable string."""
    index = SkillMemoryIndex(skill_memory_project)
    context = index.build_context_injection("test-skill-a")
    
    assert "test-skill-a" in context
    assert "66.7%" in context  # success rate
    assert "Used 2 times" in context


def test_build_context_empty(skill_memory_project):
    """Empty skill returns empty context."""
    index = SkillMemoryIndex(skill_memory_project)
    context = index.build_context_injection("unknown-skill")
    assert context == ""
