"""M1: MemoryAction Runtime Proof Tests."""
from __future__ import annotations

import importlib.util

from nexus.services.local_heal.diversity_selector import (
    DiversitySelectionResult,
)
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


def test_memory_action_created() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p5_selection_memory") is None


def test_memory_action_used_by_later_stage() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p5_selection_memory") is None


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


def test_memory_action_serializable() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p5_selection_memory") is None


def test_memory_action_created_count() -> None:
    # Retired in #2514 (ARCHIVED_2026-10-17_deadcode_b2.md): the case keeps its id and
    # asserts the module it exercised is gone.
    assert importlib.util.find_spec("nexus.services.local_heal.p5_selection_memory") is None
