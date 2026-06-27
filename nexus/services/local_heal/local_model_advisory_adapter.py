from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class LocalModelAdvisoryRequest:
    task_id: str
    problem_statement: str
    evidence_refs: tuple[str, ...]
    candidate_summary: str = ""
    route_truth_source: str = "CapabilityPlanner"


@dataclass(frozen=True)
class LocalModelAdvisoryResponse:
    advisory_invoked: bool
    local_model_called: bool
    advisory_text: str
    advisory_blockers: tuple[str, ...]
    route_truth_source: str = "CapabilityPlanner"
    adapter_output_is_route_truth: bool = False
    behavior_changed: bool = False
    public_claim_allowed: bool = False
    production_ready: bool = False


class LocalModelAdvisoryAdapter:
    @staticmethod
    def run(
        request: LocalModelAdvisoryRequest,
        *,
        advisory_fn: Callable[[LocalModelAdvisoryRequest], str] | None = None,
    ) -> LocalModelAdvisoryResponse:
        
        if advisory_fn is None:
            return LocalModelAdvisoryResponse(
                advisory_invoked=True,
                local_model_called=False,
                advisory_text="",
                advisory_blockers=("advisory_fn_missing",),
            )
            
        try:
            advisory_text = advisory_fn(request)
            return LocalModelAdvisoryResponse(
                advisory_invoked=True,
                local_model_called=True,
                advisory_text=advisory_text,
                advisory_blockers=(),
            )
        except Exception as e:
            return LocalModelAdvisoryResponse(
                advisory_invoked=True,
                local_model_called=False,
                advisory_text="",
                advisory_blockers=(f"advisory_fn_error: {str(e)}",),
            )
