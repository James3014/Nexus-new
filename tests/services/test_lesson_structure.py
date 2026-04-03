import json
from pathlib import Path
from nexus.services.continuous_learning import (
    build_structured_lesson,
    persist_structured_lesson,
    load_jsonl,
)

def test_persist_structured_lesson_writes_jsonl_event(tmp_path: Path):
    event = persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-001",
        raw_lesson="Timeout calculation used local time instead of UTC. Normalize all expiry checks to UTC.",
        category="LOGIC",
        evidence=[".nexus/reports/acceptancecheck.json"],
        corrective_action="Normalize all expiry checks to UTC.",
        source_phase="C",
        patch_hash="abc123",
    )

    lesson_file = tmp_path / ".nexus" / "knowledge" / "lesson_events.jsonl"
    assert lesson_file.exists()

    rows = load_jsonl(lesson_file)
    assert len(rows) == 1
    assert rows[0]["task_id"] == "task-001"
    assert rows[0]["lesson_id"] == event.lesson_id
    assert rows[0]["schema_version"] == "lesson_event.v1"

def test_structured_lesson_contains_required_fields():
    event = build_structured_lesson(
        task_id="task-002",
        raw_lesson="Session expiry drift came from local timezone usage. Use UTC before comparison.",
        category="LOGIC",
    )
    data = event.to_dict()
    required = [
        "task_id", "timestamp_utc", "source_phase", "category",
        "root_cause", "corrective_action", "schema_version"
    ]
    for key in required:
        assert key in data
        assert data[key] is not None

def test_codex_lessons_markdown_syncs_with_jsonl(tmp_path: Path):
    event = persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-003",
        raw_lesson="Clock drift caused auth timeout. Use UTC normalization.",
        category="LOGIC",
        corrective_action="Use UTC normalization.",
    )

    md_file = tmp_path / ".codex_lessons.md"
    assert md_file.exists()
    text = md_file.read_text(encoding="utf-8")
    assert "### Lesson task-003" in text
    assert event.lesson_id in text

def test_duplicate_root_cause_does_not_bloat_jsonl(tmp_path: Path):
    kwargs = dict(
        repo_root=tmp_path,
        task_id="task-004",
        raw_lesson="Auth timeout came from UTC mismatch. Normalize time comparisons.",
        category="LOGIC",
        corrective_action="Normalize time comparisons.",
        patch_hash="same-patch",
    )

    persist_structured_lesson(**kwargs)
    persist_structured_lesson(**kwargs)

    rows = load_jsonl(tmp_path / ".nexus" / "knowledge" / "lesson_events.jsonl")
    assert len(rows) == 1

def test_same_task_new_patch_creates_new_event(tmp_path: Path):
    persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-005",
        raw_lesson="Auth timeout came from UTC mismatch. Normalize time comparisons.",
        category="LOGIC",
        corrective_action="Normalize time comparisons.",
        patch_hash="patch-a",
    )
    persist_structured_lesson(
        repo_root=tmp_path,
        task_id="task-005",
        raw_lesson="Auth timeout came from UTC mismatch. Add UTC parser helper.",
        category="LOGIC",
        corrective_action="Add UTC parser helper.",
        patch_hash="patch-b",
    )

    rows = load_jsonl(tmp_path / ".nexus" / "knowledge" / "lesson_events.jsonl")
    assert len(rows) == 2
