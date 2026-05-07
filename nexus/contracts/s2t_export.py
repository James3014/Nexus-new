from __future__ import annotations

from typing import Any

from nexus.contracts.learning_experience import (
    LearningExperience,
    apply_autodata_quality_gate,
    project_model_training,
)
from nexus.contracts.s2t_trace import S2TTraceEvent


def redact_s2t_event(event: S2TTraceEvent) -> dict[str, Any]:
    """Return a training-safe S2T event payload without secrets or private paths."""
    payload = event.to_dict()
    payload["secret_values"] = {}
    payload["private_paths"] = ["<redacted-path>" for _ in payload.get("private_paths", [])]
    return payload


def export_agent_lightning_preferences(events: list[S2TTraceEvent]) -> dict[str, Any]:
    """Convert verified S2T choices into Agent Lightning preference pairs."""
    pairs: list[dict[str, Any]] = []
    for event in events:
        chosen = next(
            (
                candidate
                for candidate in event.candidates
                if candidate.candidate_id == event.selected_candidate_id
                and candidate.verifier_result == "pass"
            ),
            None,
        )
        if chosen is None:
            continue
        rejected = sorted(
            [
                candidate
                for candidate in event.candidates
                if candidate.candidate_id != chosen.candidate_id
                and candidate.verifier_result != "pass"
            ],
            key=lambda candidate: candidate.selector_score,
            reverse=True,
        )
        if not rejected:
            continue
        pairs.append(
            {
                "task_id": event.task_id,
                "run_id": event.run_id,
                "candidate_set_id": event.candidate_set_id,
                "chosen_candidate_id": chosen.candidate_id,
                "chosen_content_ref": chosen.content_ref,
                "rejected_candidate_id": rejected[0].candidate_id,
                "rejected_content_ref": rejected[0].content_ref,
                "verifier": event.verifier_name,
                "verifier_evidence_ref": event.verifier_evidence_ref,
            }
        )
    return {"format": "agent-lightning-preferences-v1", "pair_count": len(pairs), "pairs": pairs}


def export_model_training_v2(
    events: list[S2TTraceEvent],
    experiences: list[LearningExperience] | None = None,
    quality_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Additive model-training export; v1 remains embedded for compatibility."""
    v1 = export_agent_lightning_preferences(events)
    redacted = [redact_s2t_event(event) for event in events]
    quality_by_task = {
        str(row.get("task_id", "")): row
        for row in quality_rows or []
        if isinstance(row, dict) and str(row.get("task_id", "")).strip()
    }
    experience_rows = []
    for exp in experiences or []:
        projection = apply_autodata_quality_gate(project_model_training(exp), quality_by_task.get(exp.task_id))
        experience_rows.append(
            {
                "experience": exp.to_dict(),
                "projection": projection,
            }
        )
    return {
        "schema_version": "nexus_model_training_export.v2",
        "format": "nexus-model-training-export-v2",
        "source_schema": "s2t.v1",
        "compat": {"agent_lightning_preferences_v1": v1},
        "redaction": {
            "applied": True,
            "secret_values_removed": True,
            "private_paths_redacted": True,
        },
        "redacted_source_rows": redacted,
        "experience_rows": experience_rows,
        "quality_gate": {
            "autodata_attached": bool(quality_rows),
            "training_eligible_count": sum(
                1 for row in experience_rows if row["projection"].get("training_eligible") is True
            ),
        },
    }
