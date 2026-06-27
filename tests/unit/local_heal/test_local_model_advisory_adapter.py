from __future__ import annotations

from nexus.services.local_heal.local_model_advisory_adapter import (
    LocalModelAdvisoryAdapter,
    LocalModelAdvisoryRequest,
)


def test_advisory_adapter_default() -> None:
    request = LocalModelAdvisoryRequest(
        task_id="t1",
        problem_statement="refactor this logic",
        evidence_refs=("ref1",),
    )
    response = LocalModelAdvisoryAdapter.run(request)
    assert response.advisory_invoked is True
    assert response.local_model_called is False
    assert response.advisory_text == ""
    assert "advisory_fn_missing" in response.advisory_blockers
    
    assert response.adapter_output_is_route_truth is False
    assert response.behavior_changed is False
    assert response.public_claim_allowed is False
    assert response.production_ready is False
    assert response.route_truth_source == "CapabilityPlanner"


def test_advisory_adapter_injected() -> None:
    request = LocalModelAdvisoryRequest(
        task_id="t2",
        problem_statement="refactor this logic",
        evidence_refs=("ref1",),
    )
    
    def my_advisory(req: LocalModelAdvisoryRequest) -> str:
        return "advisory text: modify line 10"
        
    response = LocalModelAdvisoryAdapter.run(request, advisory_fn=my_advisory)
    assert response.advisory_invoked is True
    assert response.local_model_called is True
    assert response.advisory_text == "advisory text: modify line 10"
    assert not response.advisory_blockers
    
    assert response.adapter_output_is_route_truth is False
    assert response.behavior_changed is False
    assert response.public_claim_allowed is False
    assert response.production_ready is False
