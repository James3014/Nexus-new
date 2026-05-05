from nexus.research.research_stack_contract import research_stack_checkpoint_ids, research_stack_contract, research_stack_source_projects


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
