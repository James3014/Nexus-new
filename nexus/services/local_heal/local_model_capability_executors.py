"""C3: Concrete capability executors for local model path.

Wraps existing Nexus services (DDTreeAdapter, AutoreasonService, gates)
into the BaseLocalCapabilityExecutor protocol.
"""
from __future__ import annotations

from typing import Any

from nexus.services.local_heal.local_model_capability_context import (
    LocalModelCapabilityContext,
    CapabilityExecutionResult,
)


class DDTreeLocalExecutor:
    """C3: DDTree executor for local model candidate pruning."""
    name = "ddtree"
    phase = "D"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        if not ctx.candidate_pool:
            return CapabilityExecutionResult(
                name="ddtree", selected=True, invoked=False,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason="no_candidates_to_prune",
            )

        try:
            from nexus.engine.ddtree_adapter import DDTreeAdapter
            adapter = DDTreeAdapter()
            candidates_dicts = [
                {
                    "candidate_id": getattr(c, "candidate_id", str(i)),
                    "score": getattr(c, "score", 0.0),
                    "evidence_refs": list(getattr(c, "evidence_refs", ())),
                }
                for i, c in enumerate(ctx.candidate_pool)
            ]
            plan_result = adapter.plan(
                candidates=candidates_dicts,
                enabled=True,
                max_candidates=min(len(candidates_dicts), 3),
                task_desc=ctx.problem_statement,
            )

            selected_ids = plan_result.get("selected_candidate_ids", [])
            saved_steps = len(candidates_dicts) - len(selected_ids)

            return CapabilityExecutionResult(
                name="ddtree", selected=True, invoked=True,
                gate_passed=True, outcome_contributed=saved_steps > 0,
                evidence_present=True,
                telemetries={
                    "selected_candidate_ids": selected_ids,
                    "saved_steps": saved_steps,
                    "reason": plan_result.get("reason", ""),
                },
            )
        except Exception as e:
            return CapabilityExecutionResult(
                name="ddtree", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason=f"ddtree_error: {e}",
            )


class AutoreasonLocalExecutor:
    """C3: Autoreason executor for local model candidate ranking."""
    name = "autoreason"
    phase = "D"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        if not ctx.candidate_pool:
            return CapabilityExecutionResult(
                name="autoreason", selected=True, invoked=False,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason="no_candidates_to_rank",
            )

        try:
            from nexus.engine.autoreason_service import AutoreasonService
            service = AutoreasonService()
            candidates_dicts = [
                {
                    "candidate_id": getattr(c, "candidate_id", str(i)),
                    "patch": getattr(c, "candidate_patch", ""),
                    "evidence_refs": list(getattr(c, "evidence_refs", ())),
                    "model": getattr(c, "model", ""),
                    "role": getattr(c, "role", ""),
                }
                for i, c in enumerate(ctx.candidate_pool)
            ]
            result = service.run(
                candidates=candidates_dicts,
                task_desc=ctx.problem_statement,
                stop_threshold=2,
            )

            winner = result.get("winner")
            borda_scores = result.get("borda_scores", {})

            return CapabilityExecutionResult(
                name="autoreason", selected=True, invoked=True,
                gate_passed=True, outcome_contributed=winner is not None,
                evidence_present=True,
                telemetries={
                    "winner": winner,
                    "borda_scores": borda_scores,
                    "stop_reason": result.get("stop_reason", ""),
                    "judge_count": len(result.get("judge_votes", [])),
                },
            )
        except Exception as e:
            return CapabilityExecutionResult(
                name="autoreason", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason=f"autoreason_error: {e}",
            )


class ArtifactGateLocalExecutor:
    """C4: Artifact gate executor for local model path."""
    name = "artifact_gate"
    phase = "A"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        # Check evidence presence
        has_evidence = bool(ctx.evidence_refs)
        has_source_anchor = ctx.source_anchor.get("present", False)

        if not has_evidence and not has_source_anchor:
            return CapabilityExecutionResult(
                name="artifact_gate", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason="missing_artifact_evidence",
            )

        return CapabilityExecutionResult(
            name="artifact_gate", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True, evidence_present=True,
            telemetries={"evidence_refs_count": len(ctx.evidence_refs)},
        )


class ClaimGateLocalExecutor:
    """C4: Claim gate executor for local model path."""
    name = "claim_gate"
    phase = "A"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        # Claim gate requires artifact gate to pass
        # In local path, we check that evidence exists and source anchor is present
        has_evidence = bool(ctx.evidence_refs)
        has_source_anchor = ctx.source_anchor.get("present", False)

        if not has_evidence or not has_source_anchor:
            return CapabilityExecutionResult(
                name="claim_gate", selected=True, invoked=True,
                gate_passed=False, outcome_contributed=False, evidence_present=False,
                failure_reason="claim_gate_requires_artifact_evidence",
            )

        return CapabilityExecutionResult(
            name="claim_gate", selected=True, invoked=True,
            gate_passed=True, outcome_contributed=True, evidence_present=True,
            telemetries={"claim_allowed": False},
        )


class DeliveryGateLocalExecutor:
    """C4: Delivery gate executor for local model path."""
    name = "delivery_gate"
    phase = "A"

    def execute(self, ctx: LocalModelCapabilityContext) -> CapabilityExecutionResult:
        # Delivery gate requires claim gate to pass
        # In local path, we always block delivery (public_claim_allowed=false)
        return CapabilityExecutionResult(
            name="delivery_gate", selected=True, invoked=True,
            gate_passed=False, outcome_contributed=False, evidence_present=True,
            failure_reason="delivery_blocked_local_model_path",
            telemetries={"delivery_allowed": False},
        )
