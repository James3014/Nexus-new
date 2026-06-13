from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.contracts.s2t_policy import S2TCandidate, S2TSelector
from nexus.contracts.s2t_trace import S2TDecisionSpan, S2TEpisodeTrace, S2TTraceEvent, S2TTraceWriter


def _clamp_score(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def autoreason_s2t_candidates(
    *,
    autoreason_payload: dict[str, Any],
    artifact_verified: bool,
    receipt_slug: str,
) -> list[S2TCandidate]:
    factory = autoreason_payload.get("candidate_factory", {}) if isinstance(autoreason_payload, dict) else {}
    factory = factory if isinstance(factory, dict) else {}
    raw_candidates = factory.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return []

    winner = str(autoreason_payload.get("winner") or "").strip()
    raw_borda = autoreason_payload.get("borda_scores", {})
    borda_scores = raw_borda if isinstance(raw_borda, dict) else {}
    numeric_borda: list[float] = []
    for score in borda_scores.values():
        try:
            numeric_borda.append(max(0.0, float(score or 0.0)))
        except (TypeError, ValueError):
            continue
    max_borda = max(numeric_borda, default=0.0)

    out: list[S2TCandidate] = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("candidate_id") or item.get("id") or "").strip()
        if not candidate_id:
            continue
        refs = [str(ref).strip() for ref in item.get("evidence_refs", []) or [] if str(ref).strip()]
        selector_score = (
            _clamp_score(float(borda_scores.get(candidate_id, 0) or 0) / max_borda)
            if max_borda
            else _clamp_score(item.get("score", 0.0))
        )
        verifier_result = "pass" if artifact_verified and candidate_id == winner else ("fail" if winner else "not_run")
        risk_flags = [] if refs else ["missing_test_evidence"]
        if winner and candidate_id != winner:
            risk_flags.append("not_selected_by_autoreason")
        out.append(
            S2TCandidate(
                candidate_id=candidate_id,
                source="autoreason_candidate_factory",
                content_ref=f"autoreason:{receipt_slug}:{candidate_id}",
                claimed_outcome=str(item.get("summary") or item.get("claimed_outcome") or ""),
                static_score=_clamp_score(item.get("score", 0.0)),
                selector_score=selector_score,
                verifier_result=verifier_result,
                evidence_refs=refs,
                risk_flags=risk_flags,
            )
        )
    return out


def record_autoreason_s2t_trace(
    *,
    repo_root: Path,
    task_id: str | None,
    receipt_slug: str,
    autoreason_payload: dict[str, Any],
    result_report: dict[str, Any],
    artifact_verified: bool,
    normalized_success_criteria: str,
    route_decision_ref: str,
) -> dict[str, Any]:
    candidates = autoreason_s2t_candidates(
        autoreason_payload=autoreason_payload,
        artifact_verified=artifact_verified,
        receipt_slug=receipt_slug,
    )
    if not candidates:
        return {}

    import os
    from nexus.services.s2t_strict import S2TStrictRuntimeGate
    verifier_result = "pass" if artifact_verified else "fail"
    
    old_force = os.environ.get("NEXUS_S2T_3B_ADVISOR_FORCE")
    if old_force != "0":
        os.environ["NEXUS_S2T_3B_ADVISOR_FORCE"] = "1"
    try:
        gate = S2TStrictRuntimeGate()
        decision = gate.evaluate(
            task_id=task_id or receipt_slug or "",
            risk_tier="high",
            candidates=candidates,
            verifier_result=verifier_result,
            verifier_evidence_ref=f"artifact:{receipt_slug}:tests_passed" if artifact_verified else "",
        )
    finally:
        if old_force != "0":
            if old_force is None:
                os.environ.pop("NEXUS_S2T_3B_ADVISOR_FORCE", None)
            else:
                os.environ["NEXUS_S2T_3B_ADVISOR_FORCE"] = old_force
    
    trace_rel = Path(".nexus") / "reports" / "s2t" / "runtime_trace.jsonl"
    event = S2TTraceEvent(
        task_id=task_id or receipt_slug,
        run_id=receipt_slug,
        model=str(result_report.get("model_name") or result_report.get("model") or "unknown"),
        mode="shadow",
        phase="R",
        risk_tier="high",
        route_decision_ref=route_decision_ref,
        candidate_set_id=f"{receipt_slug}:autoreason",
        candidates=candidates,
        selected_candidate_id=decision.selected_candidate_id,
        selection_reason_codes=decision.reason_codes,
        verifier_name=normalized_success_criteria,
        verifier_result=verifier_result,
        verifier_evidence_ref=f"artifact:{receipt_slug}:tests_passed" if artifact_verified else "",
        semantic_verified=artifact_verified,
        trust_mismatch=not artifact_verified,
        delivery_gate="pass" if artifact_verified else "fail",
    )
    S2TTraceWriter(repo_root / trace_rel).append(event)
    episode = S2TEpisodeTrace(
        episode_id=receipt_slug,
        task_id=task_id or receipt_slug,
        model=event.model,
        mode="shadow",
        spans=[
            S2TDecisionSpan(
                node="autoreason_candidate",
                phase="R",
                candidate_set_id=event.candidate_set_id,
                selected_candidate_id=decision.selected_candidate_id,
                gate_passed=bool(decision.passed and artifact_verified),
                verifier_result=verifier_result,
                reason_codes=decision.reason_codes,
                reward=1.0 if decision.passed and artifact_verified else -1.0,
            )
        ],
        benchmark_split=str(result_report.get("benchmark_split") or ""),
        cost={
            "model_calls": int(result_report.get("model_calls", 0) or 0),
            "total_tokens": int(result_report.get("total_tokens", 0) or 0),
        },
    )
    return {
        "schema_version": episode.schema_version,
        "trace_path": str(trace_rel),
        "event": event.to_dict(),
        "episode": episode.to_dict(),
        "candidate_count": len(candidates),
        "selected_candidate_id": decision.selected_candidate_id,
        "mode": "shadow",
    }
