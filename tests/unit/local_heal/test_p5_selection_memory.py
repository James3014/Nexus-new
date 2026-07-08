"""M1: MemoryAction Runtime Proof Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p5_selection_memory import (
    create_selection_memory_action,
    read_and_mark_used,
)
from nexus.services.local_heal.diversity_selector import (
    DiversitySelectionResult,
    extract_features,
)
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
from nexus.services.local_heal.fuzzy_functions import evaluate as fuzzy_evaluate


def _make_selection_result():
    """Create a sample DiversitySelectionResult for testing."""
    return DiversitySelectionResult(
        selected_candidate_id="abc123#0",
        selected_candidate_hash="abc123",
        selected_index=0,
        selection_strategy="diversity_v1",
        candidate_count=3,
        diversity_candidate_count=3,
        duplicate_group_count=1,
        popularity_trap_detected=False,
        popularity_trap_reason="",
        score_breakdown=[{"index": 0, "score": 0.8}],
        rejected_by_diversity=[],
        fail_closed=False,
        failure_reasons=[],
        trace_events=[{"event_type": "candidate_scored"}],
    )


def test_memory_action_created():
    """M1: Memory action is created with correct fields."""
    result = _make_selection_result()
    action = create_selection_memory_action(
        task_id="t1",
        phase="P5",
        selection_result=result,
    )
    assert action.action_type == "memory_append"
    assert action.phase == "P5"
    assert action.memory_key == "p5_selection_summary"
    assert action.used_by_later_stage is False
    assert action.outcome == "success"


def test_memory_action_used_by_later_stage():
    """M1: Later stage reads and marks used_by_later_stage=True."""
    result = _make_selection_result()
    action = create_selection_memory_action(
        task_id="t1",
        phase="P5",
        selection_result=result,
    )
    used_action = read_and_mark_used(action)
    assert used_action.used_by_later_stage is True


def test_memory_usefulness_evaluates():
    """M1: memory_usefulness_v1 fuzzy function evaluates."""
    result = fuzzy_evaluate(
        "memory_usefulness_v1",
        used_by_later_stage=True,
        outcome="success",
        age_hours=1.0,
    )
    assert result.name == "memory_usefulness_v1"
    assert result.deterministic is True


def test_memory_action_serializable():
    """M1: Memory action is JSON-serializable."""
    result = _make_selection_result()
    action = create_selection_memory_action(
        task_id="t1",
        phase="P5",
        selection_result=result,
    )
    row = action.to_jsonl_row()
    json_str = json.dumps(row)
    assert len(json_str) > 0


def test_memory_action_created_count():
    """M1: memory_action_created_count > 0 (gate)."""
    result = _make_selection_result()
    action = create_selection_memory_action(
        task_id="t1",
        phase="P5",
        selection_result=result,
    )
    assert action.memory_action_id != ""
    assert action.action_type == "memory_append"
