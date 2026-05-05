from nexus.research.research_stack_contract import research_stack_checkpoint_ids, research_stack_contract, research_stack_source_projects
from nexus.research.research_runtime_contracts import build_claim_probe, build_research_doctor


def test_research_stack_contract_covers_four_external_projects():
    contract = research_stack_contract()

    assert contract["schema"] == "nexus_research_stack_contract_v1"
    assert research_stack_source_projects() == [
        "autoresearch",
        "codex-autoresearch",
        "AutoResearchClaw",
        "autoreason",
    ]
    assert research_stack_checkpoint_ids() == [
        "fixed_budget_metric_contract",
        "packet_session_ledger",
        "claim_citation_verification",
        "candidate_tournament_receipt",
    ]
    assert {item["source_project"] for item in contract["checkpoints"]} == set(contract["source_projects"])
    assert all(item["required_for_public_route"] is True for item in contract["checkpoints"])


def test_research_doctor_passes_complete_runtime_packets():
    preflight = {"present": True, "research_stack": research_stack_contract()}
    session = {"logged": True}

    out = build_research_doctor(research_preflight=preflight, research_session=session, artifact_verified=True)

    assert out["schema"] == "nexus_research_doctor_v1"
    assert out["status"] == "PASS"
    assert out["score"] == 1.0
    assert out["metric_lint"]["decision"] == "keep"


def test_claim_probe_blocks_uncertain_claim_without_artifact_evidence():
    route = {"research_context": {"risk_flags": ["claim_uncertainty"], "blocked_assumptions": ["api_contract_not_verified"]}}

    out = build_claim_probe(task_desc="Verify SDK API before patch", route=route, artifact_verified=False)

    assert out["schema"] == "nexus_claim_probe_v1"
    assert out["eligible"] is True
    assert out["invoked"] is True
    assert out["gate_passed"] is False
    assert out["decision"] == "block_patch"
