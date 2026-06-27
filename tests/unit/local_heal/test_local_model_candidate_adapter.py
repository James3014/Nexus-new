from __future__ import annotations

import pytest

from nexus.services.local_heal.local_model_candidate_adapter import (
    LocalModelCandidateAdapter,
    LocalModelCandidateRequest,
)
from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider


def test_candidate_adapter_default() -> None:
    request = LocalModelCandidateRequest(
        task_id="t1",
        problem_statement="fix a bug",
        evidence_refs=("ref1",),
        prompt="gen code proposal",
    )
    response = LocalModelCandidateAdapter.run(request)
    assert response.candidate_invoked is True
    assert response.local_model_called is False
    assert response.candidate_text == ""
    assert response.applied_patch_hash == ""
    assert response.selected_candidate_hash == ""
    assert response.selected_candidate_hash_matches_applied is False
    assert "candidate_provider_missing" in response.blockers
    assert response.public_claim_allowed is False
    assert response.production_ready is False


def test_candidate_adapter_injected() -> None:
    def fake_gen(req) -> str:
        return "def hello(): pass"
        
    provider = InjectedLocalModelProvider(fake_gen)
    request = LocalModelCandidateRequest(
        task_id="t2",
        problem_statement="fix a bug",
        evidence_refs=("ref1",),
        prompt="gen code proposal",
    )
    response = LocalModelCandidateAdapter.run(request, provider=provider)
    assert response.candidate_invoked is True
    assert response.local_model_called is True
    assert response.candidate_text == "def hello(): pass"
    assert response.selected_candidate_hash != ""
    assert response.applied_patch_hash == ""
    assert response.selected_candidate_hash_matches_applied is False
    
    assert "missing_applied_patch_hash" in response.blockers
    assert "selected_reapply_not_proven" in response.blockers
