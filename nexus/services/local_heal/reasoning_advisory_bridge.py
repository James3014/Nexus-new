from __future__ import annotations

from typing import Any

from nexus.core.belief_contracts import AuditOutcome
from nexus.core.belief_engine import BeliefEngine
from nexus.engine.autoreason_service import AutoreasonService


def apply_autoreason_advisory(ctx: Any, service: AutoreasonService | None = None) -> dict[str, Any]:
    op = ctx.op if hasattr(ctx, "op") else ctx
    candidates = [
        {
            "candidate_id": "A",
            "summary": str(getattr(op, "final_patch", "") or getattr(op, "failure_reason", "") or "no_patch")[:500],
            "evidence_refs": list(getattr(op, "evidence_refs", []) or []),
            "score": 1.0 if getattr(op, "final_patch", "") else 0.1,
        },
        {
            "candidate_id": "B",
            "summary": "fail_closed_no_override_baseline",
            "evidence_refs": ["advisory:no_override"],
            "score": 0.5,
        },
    ]
    result = (service or AutoreasonService()).run(
        candidates=candidates,
        task_desc=str(getattr(op, "problem_statement", "") or getattr(op, "instance_id", "")),
        judge_count=3,
    )
    advisory = {
        "schema": "nexus.local_heal.autoreason_advisory.v1",
        "invoked": result.get("status") == "SUCCESS",
        "receipt_bound": True,
        "winner": result.get("winner"),
        "autoreason_advisory_score": float(result.get("borda_scores", {}).get(str(result.get("winner")), 0.0) or 0.0),
        "reasons": [str(vote.get("reason", "")) for vote in result.get("judge_votes", []) if vote.get("reason")],
        "risk": "advisory_only_no_override",
        "no_override": True,
        "cannot_override_verifier": True,
        "cannot_bypass_owner_gate": True,
    }
    setattr(op, "_autoreason_advisory", advisory)
    return advisory


def apply_belief_update(ctx: Any, engine: BeliefEngine | None = None) -> dict[str, Any]:
    op = ctx.op if hasattr(ctx, "op") else ctx
    task_id = str(getattr(op, "instance_id", "") or getattr(op, "task_id", "") or "unknown")
    assumption = f"local_heal:{task_id}:repair_outcome"
    belief = engine or BeliefEngine()
    before = float(belief.get_confidence(task_id, assumption))
    verifier_passed = bool(getattr(op, "solve_eligible", False) and not getattr(op, "failure_reason", ""))
    owner_gated = "owner" in str(getattr(op, "failure_reason", "")).lower()
    if owner_gated:
        confidence = min(before, 0.2)
    elif verifier_passed:
        confidence = max(before, 0.9)
    else:
        confidence = min(before, 0.35)
    result = belief.process_audit_outcome(
        AuditOutcome(
            task_id=task_id,
            assumption=assumption,
            passed=verifier_passed,
            confidence=confidence,
            evidence_id=str(getattr(op, "receipt_path", "") or "receipt:pending"),
            reason=str(getattr(op, "failure_reason", "") or ("verifier_pass" if verifier_passed else "verifier_fail")),
            metadata={"owner_gated": owner_gated, "source": "local_heal"},
        )
    )
    after = float(result["confidence"])
    trace = {
        "schema": "nexus.local_heal.belief_trace.v1",
        "belief_before": before,
        "belief_after": after,
        "uncertainty_delta": round((1.0 - after) - (1.0 - before), 4),
        "uncertainty_classification": "high" if after < 0.4 else "medium" if after < 0.75 else "low",
        "cannot_override_verifier": True,
        "cannot_bypass_owner_gate": True,
    }
    setattr(op, "_belief_trace", trace)
    return trace
