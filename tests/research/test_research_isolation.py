from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.capability_receipts import build_trace_receipts
from nexus.engine.pipeline_stages import PipelineStagesMixin
from nexus.research.contamination_guard import evaluate_research_contamination
from nexus.research.isolation_contracts import ResearchIsolationLevel
from nexus.research.isolation_policy import decide_research_isolation
from nexus.research.masked_brief import brief_to_research_task, build_masked_research_brief


class _Pipeline(PipelineStagesMixin):
    def __init__(self):
        self.engine = MagicMock()
        self.engine.project_root = "/tmp"
        self.engine.run_dir = None


def test_research_isolation_policy_classifies_l0_l1_l2():
    l0 = decide_research_isolation(task_desc="Fix typo", task_type="bugfix", route_features={"risk_score": 10})
    l1 = decide_research_isolation(
        task_desc="Explain failing parser behavior",
        task_type="bugfix",
        route_features={"risk_score": 45, "is_cross_module_task": True},
    )
    l2 = decide_research_isolation(
        task_desc="Change public API contract after repair loop contamination",
        task_type="feature",
        route_features={"risk_score": 80},
    )

    assert l0.level == ResearchIsolationLevel.L0
    assert l1.level == ResearchIsolationLevel.L1
    assert l1.goal_visibility.value == "masked"
    assert l2.level == ResearchIsolationLevel.L2
    assert l2.goal_visibility.value == "none"


def test_masked_brief_removes_goal_and_patch_shape():
    decision = decide_research_isolation(metadata={"research_isolation_level": "L1"})
    brief = build_masked_research_brief(
        task_desc="Build checkout discount by changing PricingEngine. Observed error: ValueError: bad total",
        metadata={"target_files": ["nexus/payments/pricing.py"], "target_symbols": ["PricingEngine"]},
        decision=decision,
    )
    rendered = brief_to_research_task(brief)

    assert brief.schema_version == "masked_research_brief.v1"
    assert "user_goal" in brief.forbidden_fields_removed
    assert "checkout discount" not in rendered
    assert "changing PricingEngine" not in rendered
    assert "ValueError" in rendered


def test_contamination_guard_blocks_design_language_and_fields():
    clean = evaluate_research_contamination(
        {
            "schema_version": "research_facts.v1",
            "observed_components": ["parser"],
            "constraints": ["literal search mismatch"],
        }
    )
    contaminated = evaluate_research_contamination(
        {
            "schema_version": "research_facts.v1",
            "observed_components": ["parser"],
            "patch_plan": "implement a replacement",
        }
    )

    assert clean.passed is True
    assert contaminated.passed is False
    assert "design_field" in contaminated.detected_terms


def test_capability_planner_exposes_research_isolation_snapshot():
    plan = CapabilityPlanner().plan(
        task_desc="Use research to inspect cross-module timeout.",
        task_type="bugfix",
        route={
            "should_research": True,
            "route_features": {
                "risk_score": 45,
                "adjusted_root_cause_confidence": 0.6,
                "is_cross_module_task": True,
            },
        },
        codeintel={"impact_report_present": True},
    ).to_dict()

    policy = plan["signal_snapshot"]["research_isolation_policy"]
    assert policy == {
        "level": "L1",
        "goal_visibility": "masked",
        "output_mode": "facts_only",
        "confirmation_required": False,
    }


def test_pipeline_l1_research_uses_masked_task_and_returns_facts():
    ctx = MagicMock()
    ctx.task_id = "research-l1-001"
    ctx.task_desc = "Build checkout discount by changing PricingEngine. Observed error: ValueError: bad total"
    ctx.task_type = "bugfix"
    ctx.state = NexusState(task_id=ctx.task_id)
    ctx.state.metadata["research_isolation_level"] = "L1"
    ctx.state.metadata["target_files"] = ["nexus/payments/pricing.py"]
    ctx.state.metadata["target_symbols"] = ["PricingEngine"]
    ctx.researcher.run.return_value = {
        "status": "SUCCESS",
        "findings": ["PricingEngine participates in total calculation"],
        "retrieval_refs": ["symbol:PricingEngine"],
    }
    decision = SimpleNamespace(reason="test", rounds=1)

    payload = _Pipeline()._run_standard_phase(ctx, decision)
    sent_task = ctx.researcher.run.call_args.args[1]["task"]

    assert payload["schema_version"] == "research_facts.v1"
    assert payload["research_isolation_receipt"]["isolation_level"] == "L1"
    assert payload["research_isolation_receipt"]["facts_only_guard_passed"] is True
    assert "checkout discount" not in sent_task
    assert "ValueError" in sent_task


def test_research_receipt_l1_requires_facts_guard_pass():
    plan = {"selected_capabilities": ["research"]}
    missing_guard = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "research_used": True,
                "research_refs": ["research:facts:t1"],
                "research_gate_passed": True,
                "research_isolation_receipt": {
                    "schema_version": "research_isolation_receipt.v1",
                    "isolation_level": "L1",
                    "artifact_schema": "research_facts.v1",
                    "facts_only_guard_passed": False,
                    "artifact_refs": ["research:facts:t1"],
                },
            },
        )
    }
    proven = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "research_used": True,
                "research_refs": ["research:facts:t1"],
                "research_gate_passed": True,
                "research_isolation_receipt": {
                    "schema_version": "research_isolation_receipt.v1",
                    "isolation_level": "L1",
                    "artifact_schema": "research_facts.v1",
                    "facts_only_guard_passed": True,
                    "artifact_refs": ["research:facts:t1"],
                },
            },
        )
    }

    assert missing_guard["research"].gate_passed is False
    assert proven["research"].gate_passed is True
    assert proven["research"].outcome_contributed is True


def test_research_receipt_l1_does_not_infer_success_from_legacy_pack():
    plan = {"selected_capabilities": ["research"]}
    receipts = {
        item.name: item
        for item in build_trace_receipts(
            plan=plan,
            capabilities={
                "claim_verified": True,
                "research_used": True,
                "research_refs": ["research:legacy-pack"],
                "research_gate_passed": True,
                "research_isolation_receipt": {
                    "schema_version": "research_isolation_receipt.v1",
                    "isolation_level": "L1",
                    "artifact_schema": "research_pack.v1",
                    "facts_only_guard_passed": True,
                    "artifact_refs": ["research:legacy-pack"],
                },
            },
        )
    }

    assert receipts["research"].gate_passed is False
    assert receipts["research"].failure_reason == "evidence_without_gate_pass"
