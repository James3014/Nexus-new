from __future__ import annotations

from nexus.app.research_receipt_runtime import build_capability_receipt_payloads, runtime_receipt_plan_payload


def test_runtime_receipt_plan_prunes_unexecuted_autoreason_and_judge_panel():
    capabilities = {}
    plan = runtime_receipt_plan_payload(
        {"selected_capabilities": ["hyper_sprint", "autoreason", "judge_panel", "llm_judge_panel", "formal_report"]},
        {
            "capabilities": capabilities,
            "autoreason": {"status": "SKIPPED", "stop_reason": "candidate_factory_skipped", "judge_votes": []},
        },
    )

    assert plan["selected_capabilities"] == ["hyper_sprint", "formal_report"]
    assert capabilities["runtime_pruned_capabilities"] == {
        "autoreason": "candidate_factory_skipped",
        "judge_panel": "candidate_factory_skipped",
        "llm_judge_panel": "candidate_factory_skipped",
    }


def test_runtime_receipt_plan_adds_runtime_autoreason_success():
    plan = runtime_receipt_plan_payload(
        {"selected_capabilities": ["hyper"]},
        {
            "capabilities": {"claim_verified": True},
            "autoreason": {
                "enabled": True,
                "status": "SUCCESS",
                "winner": "AB",
                "judge_votes": [{"judge": "deterministic", "ranking": ["AB", "B", "A"]}],
            },
        },
    )

    assert "autoreason" in plan["selected_capabilities"]


def test_build_capability_receipt_payloads_marks_runtime_autoreason_safe():
    receipts = build_capability_receipt_payloads(
        {"selected_capabilities": ["hyper"]},
        {
            "capabilities": {"claim_verified": True},
            "autoreason": {
                "enabled": True,
                "status": "SUCCESS",
                "winner": "AB",
                "judge_votes": [{"judge": "deterministic", "ranking": ["AB", "B", "A"]}],
            },
            "ddtree": {},
            "ultra_review": {},
            "codeintel": {},
        },
    )

    by_name = {item["name"]: item for item in receipts}
    assert by_name["autoreason"]["public_claim_safe"] is True
    assert by_name["autoreason"]["evidence_refs"]
