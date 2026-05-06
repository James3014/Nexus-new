from __future__ import annotations

from typing import Any

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
