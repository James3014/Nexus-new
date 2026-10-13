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


def test_contamination_guard_blocks_design_field_without_design_language():
    result = evaluate_research_contamination(
        {
            "schema_version": "research_facts.v1",
            "observed_components": ["parser"],
            "patch_plan": "candidate_001",
        }
    )

    assert result.passed is False
    assert result.detected_terms == ("design_field",)
    assert result.failure_reason == "research_contamination_detected"


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


def test_research_receipt_l1_requires_facts_guard_pass(tmp_path):
    """Contract: L1 research needs the facts-only guard for its gate; the pass stays fail-closed (#453)."""
    plan = {"selected_capabilities": ["research"]}
    evidence = _real_verifier_evidence(tmp_path)
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
                **evidence,
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
                **evidence,
            },
        )
    }

    assert missing_guard["research"].gate_passed is False
    assert proven["research"].gate_passed is True
    _assert_receipt_held_fail_closed(proven["research"].to_dict())


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


# ARCHIVED 2026-10-13 legacy-engine: this file tests (in whole or in part) modules archived with
# the legacy NexusEngine (nexus.engine.pipeline_stages); see ARCHIVED_2026-10-13-legacy-engine.md.
# It keeps running with unchanged node ids until the deletion PR removes it with those modules.


def _real_verifier_evidence(tmp_path) -> dict:
    """Evidence the current receipt contract asks for (#453, #1757).

    Runs a real verifier over a real source file and returns its result, the sha256 of the
    verifier artifact, the source hash and telemetry measured around the run.
    """
    import hashlib
    import subprocess
    import sys
    import time

    source = tmp_path / "target_under_verifier.py"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, "-c", "import ast, sys; ast.parse(open(sys.argv[1]).read())", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    wall_time_ms = max(1, int((time.perf_counter() - started) * 1000))
    artifact = tmp_path / "verifier.log"
    artifact.write_text(f"returncode={proc.returncode}\n{proc.stdout}{proc.stderr}", encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return {
        "verifier_status": "pass",
        "verifier_artifact": "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "source_hash": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
        "telemetries": {
            "telemetry_source": "measured",
            "wall_time_ms": wall_time_ms,
            "token_usage": 0,
            "provider_costs": 0.0,
            "overhead_ms": 0,
            "model_calls": 0,
        },
    }


def _assert_receipt_held_fail_closed(receipt: dict) -> None:
    """Contract (#453 ADVISORY_ONLY_FAIL_CLOSED): a generic adapter payload cannot mint verifier
    authority. The receipt keeps its invocation, evidence and gate pass, but it never contributes
    an outcome and is never public_claim_safe until an authenticated upstream verifier authority
    is bound."""
    assert receipt["selected"] is True
    assert receipt["invoked"] is True
    assert receipt["evidence_present"] is True
    assert receipt["gate_passed"] is True
    assert receipt["failure_reason"] == ""
    assert receipt["outcome_contributed"] is False
    assert receipt["public_claim_safe"] is False
