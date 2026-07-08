from __future__ import annotations

from dataclasses import dataclass


@dataclass
class P5MemoryBridgePayload:
    """Bridge payload for P5 selection → LearningClosure / FindingsMemory."""
    lesson_type: str = "p5_selection_effect"
    task_id: str = ""
    selection_strategy: str = ""
    selection_changed: bool = False
    selected_model: str = ""
    counterfactual_model: str = ""
    trace_ref: str = "p5_trace_events"
    score_breakdown_ref: str = "p5_score_breakdown"
    claim_level: str = "controlled"
    eligible_for_findings_memory: bool = False


def build_p5_memory_bridge_payload(
    *,
    task_id: str,
    selection_strategy: str,
    selection_changed: bool,
    selected_model: str,
    counterfactual_model: str,
    claim_level: str = "controlled",
) -> P5MemoryBridgePayload:
    """Build a bridge payload for P5 selection effect.

    Does NOT write to FindingsMemory directly — produces payload for caller.
    Caller (LearningClosure or test) decides whether to persist.
    """
    # Rules for eligible_for_findings_memory
    eligible = False
    if claim_level == "verified":
        eligible = True
    # controlled-only P5 fixtures → not eligible
    # real shadow (no verifier) → not eligible
    # Only verified apply/verifier/claim cases → eligible

    return P5MemoryBridgePayload(
        lesson_type="p5_selection_effect",
        task_id=task_id,
        selection_strategy=selection_strategy,
        selection_changed=selection_changed,
        selected_model=selected_model,
        counterfactual_model=counterfactual_model,
        trace_ref="p5_trace_events",
        score_breakdown_ref="p5_score_breakdown",
        claim_level=claim_level,
        eligible_for_findings_memory=eligible,
    )
