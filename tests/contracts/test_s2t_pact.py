from __future__ import annotations
import json
from pathlib import Path
from nexus.contracts.s2t_policy import S2TCandidate
from nexus.contracts.pact import pact_from_advisor_output, PACTRecord
from nexus.app.oracle_advisor import OracleAdvisor

def _candidate(candidate_id: str = "A", verifier_result: str = "pass") -> S2TCandidate:
    return S2TCandidate(
        candidate_id=candidate_id,
        source="test",
        content_ref=f".nexus/reports/s2t/{candidate_id}.json",
        selector_score=0.9,
        verifier_result=verifier_result,
        evidence_refs=[".nexus/reports/claim_gate.json"] if verifier_result == "pass" else []
    )

def test_pact_from_advisor_output_select_route() -> None:
    candidates = [_candidate("cand-A"), _candidate("cand-B", "fail")]
    result = {
        "selected_candidate_id": "cand-A",
        "selection_reason_codes": ["optimal_cost"],
        "required_verifier": "pytest",
        "abstain_reason": None,
        "_overhead_stats": {"ttft_ms": 10.0}
    }
    
    pact = pact_from_advisor_output(
        task_id="task-123",
        risk_tier="low",
        candidates=candidates,
        result=result,
        skill_hints=["cand-A:100%"],
        memory_hints=["cand-B:failures=syntax"]
    )
    
    assert pact.action_type == "select_route"
    assert pact.affected_scope == ["cand-A"]
    assert pact.risk_level == "low"
    assert pact.evidence_refs == [".nexus/reports/claim_gate.json"]
    assert pact.next_step == "run_verifier: pytest"
    assert pact.metadata["task_id"] == "task-123"
    assert pact.metadata["skill_hints"] == ["cand-A:100%"]
    assert pact.metadata["memory_hints"] == ["cand-B:failures=syntax"]
    assert pact.metadata["overhead_stats"]["ttft_ms"] == 10.0

def test_pact_from_advisor_output_abstain() -> None:
    result = {
        "selected_candidate_id": None,
        "selection_reason_codes": [],
        "required_verifier": None,
        "abstain_reason": "no_valid_candidates"
    }
    
    pact = pact_from_advisor_output(
        task_id="task-123",
        risk_tier="medium",
        candidates=[],
        result=result
    )
    
    assert pact.action_type == "abstain"
    assert pact.affected_scope == []
    assert pact.risk_level == "medium"
    assert pact.evidence_refs == []
    assert pact.next_step == "fallback_rule_selector: no_valid_candidates"

def test_pact_from_advisor_output_bypass() -> None:
    result = {
        "selected_candidate_id": None,
        "selection_reason_codes": [],
        "required_verifier": None,
        "abstain_reason": None
    }
    
    pact = pact_from_advisor_output(
        task_id="task-123",
        risk_tier="high",
        candidates=[],
        result=result
    )
    
    assert pact.action_type == "bypass"
    assert pact.affected_scope == []
    assert pact.next_step == "fallback_rule_selector"

def test_oracle_advisor_synthesize_pact(tmp_path) -> None:
    advisor = OracleAdvisor(project_root=tmp_path)
    advisor.shadow_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Test shadow pending
    res = advisor.synthesize_advice("tid-1", {"found_dimensions": {"lang": "py"}})
    pact = json.loads(res)
    assert pact["action_type"] == "pending_shadow"
    assert pact["next_step"] == "wait_for_shadow_execution"
    assert pact["metadata"]["found_dimensions"] == {"lang": "py"}
    
    # 2. Test shadow success
    log_file = advisor.shadow_dir / "tid-1.json"
    log_data = {
        "result": {
            "selected_candidate_id": "cand-99",
            "required_verifier": "claim_gate",
            "confidence": 0.85
        }
    }
    log_file.write_text(json.dumps(log_data))
    
    res = advisor.synthesize_advice("tid-1", {})
    pact = json.loads(res)
    assert pact["action_type"] == "select_route"
    assert pact["affected_scope"] == ["cand-99"]
    assert pact["next_step"] == "run_verifier: claim_gate"
    assert pact["metadata"]["confidence"] == 0.85

    # 3. Test shadow corrupt
    log_file.write_text("corrupted json data {")
    res = advisor.synthesize_advice("tid-1", {})
    pact = json.loads(res)
    assert pact["action_type"] == "error_fallback"
    assert "failed_to_parse_shadow_log" in pact["next_step"]
