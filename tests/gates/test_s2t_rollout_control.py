
import hashlib
import json
import os
import pytest
from nexus.contracts.s2t_policy import S2TCandidate
from nexus.services.s2t_strict import S2TStrictRuntimeGate, S2T3BAdvisor

def _candidate(candidate_id: str, verifier_result: str = "pass") -> S2TCandidate:
    return S2TCandidate(
        candidate_id=candidate_id,
        source="repair_pass",
        content_ref=f".nexus/reports/s2t/{candidate_id}.json",
        selector_score=0.8,
        verifier_result=verifier_result,
        evidence_refs=[".nexus/reports/claim_gate.json"] if verifier_result == "pass" else [],
    )

@pytest.fixture
def mock_advisor():
    class MockAdvisor(S2T3BAdvisor):
        def advise(self, risk_tier, candidates):
            # Always suggest B
            return {
                "selected_candidate_id": "B",
                "selection_reason_codes": ["mock"],
                "required_verifier": None,
                "abstain_reason": None
            }
    return MockAdvisor()

def test_rollout_control_canary_rate(tmp_path, mock_advisor, monkeypatch):
    # Set canary rate to 50%
    monkeypatch.setenv("NEXUS_S2T_3B_CANARY_RATE", "50")
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")
    
    gate = S2TStrictRuntimeGate(advisor=mock_advisor, evidence_log_path=tmp_path / "log.jsonl")
    
    hit_count = 0
    total = 100
    for i in range(total):
        task_id = f"task-{i}"
        decision = gate.evaluate(task_id=task_id, risk_tier="low", candidates=[_candidate("A"), _candidate("B")], verifier_result="pass")
        if decision.advisor_used:
            hit_count += 1
            
    # Hash distribution should be roughly 50%
    assert 40 <= hit_count <= 60

def test_rollout_control_modes(tmp_path, mock_advisor, monkeypatch):
    candidates = [_candidate("A"), _candidate("B")]
    monkeypatch.setenv("NEXUS_S2T_3B_ADVISOR_FORCE", "1")
    
    # 1. Mode: off
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "off")
    gate = S2TStrictRuntimeGate(advisor=mock_advisor, evidence_log_path=tmp_path / "off.jsonl")
    decision = gate.evaluate(task_id="t1", risk_tier="low", candidates=candidates, verifier_result="pass")
    assert decision.advisor_used is False
    assert decision.advisor_outcome_status == "advisor_disabled_by_mode"

    # 2. Mode: observation (low risk)
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "observation")
    gate = S2TStrictRuntimeGate(advisor=mock_advisor, evidence_log_path=tmp_path / "obs.jsonl")
    decision = gate.evaluate(task_id="t2", risk_tier="low", candidates=candidates, verifier_result="pass")
    assert decision.advisor_used is True
    assert decision.selected_candidate_id == "A" # Baseline
    assert decision.advisor_selected_candidate_id == "B"
    
    # 3. Mode: low_risk (low risk)
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "low_risk")
    gate = S2TStrictRuntimeGate(advisor=mock_advisor, evidence_log_path=tmp_path / "low_risk.jsonl")
    decision = gate.evaluate(task_id="t3", risk_tier="low", candidates=candidates, verifier_result="pass")
    assert decision.advisor_used is True
    assert decision.selected_candidate_id == "B" # Override applied
    
    # 4. Mode: low_risk (medium risk) -> should not apply override
    decision = gate.evaluate(task_id="t4", risk_tier="medium", candidates=candidates, verifier_result="pass")
    assert decision.advisor_used is True
    assert decision.selected_candidate_id == "A" # Baseline kept
    
    # 5. Mode: medium_observation (medium risk)
    monkeypatch.setenv("NEXUS_S2T_3B_ASSISTED_MODE", "medium_observation")
    gate = S2TStrictRuntimeGate(advisor=mock_advisor, evidence_log_path=tmp_path / "med_obs.jsonl")
    decision = gate.evaluate(task_id="t5", risk_tier="medium", candidates=candidates, verifier_result="pass")
    assert decision.advisor_used is True
    assert decision.selected_candidate_id == "A" # Baseline kept

def test_rollout_control_kill_switch(tmp_path, mock_advisor, monkeypatch):
    monkeypatch.setenv("NEXUS_S2T_3B_ADVISOR_ENABLED", "0")
    monkeypatch.setenv("NEXUS_S2T_3B_ADVISOR_FORCE", "1")
    
    gate = S2TStrictRuntimeGate(advisor=mock_advisor, evidence_log_path=tmp_path / "kill.jsonl")
    decision = gate.evaluate(task_id="t1", risk_tier="low", candidates=[_candidate("A"), _candidate("B")], verifier_result="pass")
    assert decision.advisor_used is False
    assert decision.advisor_outcome_status == "not_run"
