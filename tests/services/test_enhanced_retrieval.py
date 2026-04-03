import pytest
import json
from pathlib import Path
from nexus.services.lesson_retrieval import retrieve_enhanced_lessons
from nexus.services.continuous_learning import persist_structured_lesson

@pytest.fixture
def repo_with_lessons(tmp_path):
    (tmp_path / ".nexus" / "knowledge").mkdir(parents=True)
    (tmp_path / ".nexus" / "learning").mkdir(parents=True)
    
    # 1. Local Lesson (Strong match)
    persist_structured_lesson(
        repo_root=tmp_path, 
        task_id="task-local", 
        raw_lesson="Local root cause", 
        category="LOGIC", 
        corrective_action="Fix locally"
    )
    
    # 2. Shared Envelope (Strong match)
    shared_envelope = {
        "cache_id": "cache-abc",
        "lesson": {
            "lesson_id": "sha-shared",
            "task_id": "task-shared",
            "category": "LOGIC",
            "root_cause": "Local root cause", # Same for match
            "corrective_action": "Fix shared",
            "confidence": 0.9,
            "timestamp_utc": "2026-04-03T12:00:00Z",
            "schema_version": "lesson_event.v1",
            "outcome": "success"
        },
        "source_type": "p2p",
        "source_repo": "ws-primary",
        "trust_tier": "peer",
        "local_weight": 0.85
    }
    shared_path = tmp_path / ".nexus" / "learning" / "shared_lessons.jsonl"
    with open(shared_path, "w") as f:
        f.write(json.dumps(shared_envelope) + "\n")
        
    return tmp_path

def test_enhanced_prefers_local_over_shared(repo_with_lessons):
    # Search for "Local root cause"
    results = retrieve_enhanced_lessons(repo_with_lessons, "Local root cause", max_results=3)
    
    # Assert Local is first (due to 1.0 vs 0.85 weight)
    assert results[0]["_memory_source"] == "local"
    assert results[0]["_trust_weight"] == 1.0

def test_enhanced_limits_to_one_shared_lesson(repo_with_lessons):
    # Add another shared lesson
    extra_shared = {
        "cache_id": "cache-extra",
        "lesson": {
            "lesson_id": "sha-extra",
            "task_id": "task-extra",
            "category": "LOGIC",
            "root_cause": "Local root cause",
            "corrective_action": "Fix extra",
            "confidence": 0.95,
            "timestamp_utc": "2026-04-03T12:00:00Z",
            "schema_version": "lesson_event.v1",
            "outcome": "success"
        },
        "source_type": "p2p",
        "source_repo": "ws-secondary",
        "trust_tier": "peer",
        "local_weight": 0.85
    }
    shared_path = repo_with_lessons / ".nexus" / "learning" / "shared_lessons.jsonl"
    with open(shared_path, "a") as f:
        f.write(json.dumps(extra_shared) + "\n")
        
    # Search
    results = retrieve_enhanced_lessons(repo_with_lessons, "Local root cause", max_results=5)
    
    # Assert only 1 shared lesson is used (Guard check)
    shared_results = [r for r in results if r["_memory_source"] == "shared"]
    assert len(shared_results) == 1

def test_enhanced_skips_shared_if_local_sufficient(repo_with_lessons):
    # Add a second local lesson
    persist_structured_lesson(
        repo_root=repo_with_lessons, 
        task_id="task-local-2", 
        raw_lesson="Local root cause also", 
        category="LOGIC", 
        corrective_action="Fix local 2"
    )
    
    # Search
    results = retrieve_enhanced_lessons(repo_with_lessons, "Local root cause", max_results=5)
    
    # Assert 0 shared results because we have 2 local matching hits (Safety guard)
    shared_results = [r for r in results if r["_memory_source"] == "shared"]
    assert len(shared_results) == 0
    assert len(results) == 2
