import json
from pathlib import Path
from nexus.services.lesson_retrieval import (
    retrieve_relevant_lessons,
    inject_lesson_context,
)
from nexus.services.continuous_learning import persist_structured_lesson

def test_lesson_retrieval_matches_keywords(tmp_path: Path):
    # Setup: Create a lesson event
    jsonl_path = tmp_path / ".nexus" / "knowledge" / "lesson_events.jsonl"
    persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-auth-101",
        raw_lesson="Timeout drift due to timezone. Use UTC.",
        category="LOGIC",
        corrective_action="Normalization to UTC",
    )

    # Retrieval
    retrieved = retrieve_relevant_lessons(
        jsonl_path, "Fix auth session timeout drift with normalization"
    )
    
    assert len(retrieved) == 1
    assert retrieved[0]["task_id"] == "task-auth-101"

def test_lesson_retrieval_applies_category_bonus(tmp_path: Path):
    jsonl_path = tmp_path / ".nexus" / "knowledge" / "lesson_events.jsonl"
    # Lesson A: Logic category
    persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-001",
        raw_lesson="Generic fix",
        category="LOGIC",
        corrective_action="Use type hinting",
    )
    # Lesson B: Format category
    persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-002",
        raw_lesson="Generic fix",
        category="FORMAT",
        corrective_action="Use black",
    )

    # Query with Logic category
    retrieved = retrieve_relevant_lessons(
        jsonl_path, "Fix generic pattern", diagnosis={"category": "LOGIC"}
    )
    
    assert retrieved[0]["task_id"] == "task-001"

def test_inject_lesson_context_populates_metadata():
    state = {"metadata": {}}
    lessons = [{
        "task_id": "task-test",
        "category": "TEST",
        "root_cause": "Bad mocking",
        "corrective_action": "Use patch.object",
        "lesson_id": "mock-abc",
        "reusable_when": ["testing"]
    }]
    
    state, tokens = inject_lesson_context(state, lessons)
    
    assert tokens > 0
    assert state["metadata"]["retrieved_lessons"]["count"] == 1
    assert "Root cause: Bad mocking" in state["metadata"]["retrieved_lessons"]["prompt_context"]

def test_inject_lesson_context_honors_max_tokens():
    state = {"metadata": {}}
    lessons = [{
        "task_id": f"task-{i}",
        "category": "TEST",
        "root_cause": "Long repetition text to fill token window. " * 5,
        "corrective_action": "Simple fix.",
        "lesson_id": f"id-{i}"
    } for i in range(10)]
    
    # Use very small token limit
    state, tokens = inject_lesson_context(state, lessons, max_tokens=100)
    
    # Each lesson block is ~150-200 chars (~40-50 tokens). 
    # With 100 limit, should probably only fit 1 or 2.
    assert state["metadata"]["retrieved_lessons"]["used"] < 10
    assert tokens <= 100
