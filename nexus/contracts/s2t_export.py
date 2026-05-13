from __future__ import annotations

import json
from pathlib import Path
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


def export_model_training_v3(
    events: list[S2TTraceEvent],
    experiences: list[LearningExperience] | None = None,
    quality_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Training-facing export with preference, reward, and gated experience rows."""
    v2 = export_model_training_v2(events, experiences=experiences, quality_rows=quality_rows)
    rows: list[dict[str, Any]] = []
    for pair in v2["compat"]["agent_lightning_preferences_v1"]["pairs"]:
        rows.append({"row_type": "preference_pair", **pair})
    for event in events:
        verified = bool(event.semantic_verified or (event.verifier_result == "pass" and event.delivery_gate in {"pass", "not_run"}))
        rows.append(
            {
                "row_type": "reward_row",
                "task_id": event.task_id,
                "run_id": event.run_id,
                "model": event.model,
                "mode": event.mode,
                "selected_candidate_id": event.selected_candidate_id,
                "reward": 1.0 if verified and not event.trust_mismatch else -1.0,
                "verifier_result": event.verifier_result,
                "delivery_gate": event.delivery_gate,
                "trust_mismatch": event.trust_mismatch,
                "verifier_evidence_ref": event.verifier_evidence_ref,
            }
        )
    for row in v2["experience_rows"]:
        projection = row["projection"]
        rows.append(
            {
                "row_type": "experience_projection",
                "experience_id": projection.get("experience_id", ""),
                "training_eligible": bool(projection.get("training_eligible", False)),
                "targets": list(projection.get("targets", []) or []),
                "model_training_gate": dict(projection.get("model_training_gate", {}) or {}),
                "autodata_gate": dict(projection.get("autodata_gate", {}) or {}),
            }
        )
    return {
        "schema_version": "nexus_model_training_export.v3",
        "format": "nexus-model-training-export-v3",
        "compat": {"v2": v2},
        "training_rows": rows,
        "summary": {
            "preference_pair_count": sum(1 for row in rows if row["row_type"] == "preference_pair"),
            "reward_row_count": sum(1 for row in rows if row["row_type"] == "reward_row"),
            "experience_projection_count": sum(1 for row in rows if row["row_type"] == "experience_projection"),
            "training_eligible_count": v2["quality_gate"]["training_eligible_count"],
            "hard_negative_count": sum(1 for row in rows if "hard_negative" in row.get("targets", [])),
        },
    }


def write_model_training_export_v3(
    path: Path,
    events: list[S2TTraceEvent],
    experiences: list[LearningExperience] | None = None,
    quality_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = export_model_training_v3(events, experiences=experiences, quality_rows=quality_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload
