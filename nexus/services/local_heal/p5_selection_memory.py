from __future__ import annotations

import hashlib
import json
from typing import Any

from nexus.services.local_heal.memory_action_receipt import MemoryActionReceipt
from nexus.services.local_heal.diversity_selector import DiversitySelectionResult
from nexus.services.local_heal.fuzzy_functions import evaluate as fuzzy_evaluate


def create_selection_memory_action(
    task_id: str,
    phase: str,
    selection_result: DiversitySelectionResult,
) -> MemoryActionReceipt:
    """Create a memory action for P5 selection result.

    Writes one memory_append action recording the diversity selection decision.
    """
    # Build summary content
    summary = {
        "selected_candidate_id": selection_result.selected_candidate_id,
        "selected_candidate_hash": selection_result.selected_candidate_hash,
        "selected_index": selection_result.selected_index,
        "selection_strategy": selection_result.selection_strategy,
        "candidate_count": selection_result.candidate_count,
        "duplicate_group_count": selection_result.duplicate_group_count,
        "popularity_trap_detected": selection_result.popularity_trap_detected,
        "fail_closed": selection_result.fail_closed,
        "score_breakdown_count": len(selection_result.score_breakdown),
        "trace_event_count": len(selection_result.trace_events),
    }

    return MemoryActionReceipt(
        memory_action_id=f"ma-p5-{hashlib.sha256(json.dumps(summary).encode()).hexdigest()[:8]}",
        task_id=task_id,
        phase=phase,
        action_type="memory_append",
        memory_file="p5_selection_history.jsonl",
        memory_key="p5_selection_summary",
        reason="record diversity selection decision for later replay/audit",
        input_refs=("p5_score_breakdown", "p5_trace_events"),
        output_ref=None,
        used_by_later_stage=False,
        outcome="success",
    )


def read_and_mark_used(action: MemoryActionReceipt) -> MemoryActionReceipt:
    """Simulate a later stage reading and marking the memory action as used.

    Returns a new MemoryActionReceipt with used_by_later_stage=True.
    """
    # Evaluate usefulness via fuzzy function
    usefulness = fuzzy_evaluate(
        "memory_usefulness_v1",
        used_by_later_stage=action.used_by_later_stage,
        outcome=action.outcome,
        age_hours=0.0,
    )

    # Create new receipt with used_by_later_stage=True
    from dataclasses import replace
    return replace(action, used_by_later_stage=True)
