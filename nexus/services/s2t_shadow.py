from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nexus.contracts.s2t_policy import S2TCandidate, S2TSelector
from nexus.contracts.s2t_trace import S2TTraceEvent, S2TTraceWriter


@dataclass(frozen=True)
class S2TShadowResult:
    final_candidate_id: str
    counterfactual_candidate_id: str
    trace_written: bool


class S2TShadowRecorder:
    """Record S2T counterfactual choices without changing runtime delivery."""

    def __init__(
        self,
        *,
        trace_path: str | Path,
        selector: S2TSelector | None = None,
        enabled: bool = True,
    ) -> None:
        self.trace_path = Path(trace_path)
        self.selector = selector or S2TSelector()
        self.enabled = enabled

    def record(
        self,
        *,
        task_id: str,
        run_id: str,
        model: str,
        phase: str,
        risk_tier: str,
        candidate_set_id: str,
        candidates: list[S2TCandidate],
        original_final_candidate_id: str,
        route_decision_ref: str = "",
        verifier_name: str = "",
        verifier_result: str = "not_run",
        verifier_evidence_ref: str = "",
    ) -> S2TShadowResult:
        if not self.enabled:
            return S2TShadowResult(
                final_candidate_id=original_final_candidate_id,
                counterfactual_candidate_id="",
                trace_written=False,
            )

        decision = self.selector.select(candidates)
        event = S2TTraceEvent(
            task_id=task_id,
            run_id=run_id,
            model=model,
            mode="shadow",
            phase=phase,
            risk_tier=risk_tier,
            route_decision_ref=route_decision_ref,
            candidate_set_id=candidate_set_id,
            candidates=candidates,
            selected_candidate_id=decision.selected_candidate_id,
            selection_reason_codes=decision.reason_codes,
            verifier_name=verifier_name,
            verifier_result=verifier_result,
            verifier_evidence_ref=verifier_evidence_ref,
            semantic_verified=verifier_result == "pass",
            delivery_gate="shadow_only",
        )
        S2TTraceWriter(self.trace_path).append(event)
        return S2TShadowResult(
            final_candidate_id=original_final_candidate_id,
            counterfactual_candidate_id=decision.selected_candidate_id,
            trace_written=True,
        )
