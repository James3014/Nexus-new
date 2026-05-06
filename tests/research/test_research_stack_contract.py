from nexus.research.research_stack_contract import research_stack_checkpoint_ids, research_stack_contract, research_stack_source_projects
from nexus.app.research_receipt_runtime import build_capability_receipt_payloads
from nexus.research.research_runtime_contracts import (
    build_claim_probe,
    build_nexus_failure_analysis,
    build_research_doctor,
)


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


def test_nexus_failure_analysis_requires_root_cause_after_flash_fail():
    out = build_nexus_failure_analysis(
        artifact_verified=False,
        tests_passed=False,
        artifact_summary={"changed": False, "mutation_required": True},
        research_doctor={"status": "FAIL", "failures": ["artifact_not_verified"]},
        claim_probe={"decision": "block_patch"},
        gemini_invoked=True,
        nexus_context_delivered=True,
        self_heal_used=False,
        result_report={"model_patch_generated": False},
    )

    assert out["schema"] == "nexus_failure_analysis_v1"
    assert out["status"] == "ACTION_REQUIRED"
    assert out["primary_cause"] == "flash_no_verified_mutation"
    assert out["owner"] == "nexus_retry_policy"
    assert out["nexus_gap"] == "bounded_self_heal_not_triggered"
    assert out["nexus_blocked_unsafe_delivery"] is True
    assert out["next_action"] == "trigger_bounded_self_heal_before_accepting_flash_failure"
    assert set(out["reasons"]) >= {
        "required_mutation_missing",
        "model_patch_not_generated",
        "claim_probe_blocked_patch",
    }


def test_hyper_runtime_usage_backfills_receipt_when_planner_omits_hyper():
    receipts = build_capability_receipt_payloads(
        {
            "selected_capabilities": ["research", "delivery_gate"],
        },
        {
            "capabilities": {
                "claim_verified": True,
                "research_used": True,
                "research_refs": ["research:task:route_selected"],
                "research_gate_passed": True,
                "delivery_refs": ["delivery:task:artifact_tests_passed"],
                "delivery_gate_passed": True,
                "hyper_used": True,
                "winner_source": "llm",
                "attempt_count": 1,
            }
        },
    )

    hyper = next(item for item in receipts if item["name"] == "hyper")
    assert hyper["invoked"] is True
    assert hyper["public_claim_safe"] is True
    assert "llm" in hyper["evidence_refs"]
