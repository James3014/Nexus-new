import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nexus.core.belief_contracts import AuditOutcome
from nexus.core.belief_engine import BeliefEngine
from nexus.core.config import OrchestratorConfig
from nexus.core.context_hub import ContextDependencies, ContextHub, StateView
from nexus.core.learning_evidence import LearningEvidence
from nexus.core.learning_steward import GovernanceProfile, LearningSteward
from nexus.core.orchestrator import NexusOrchestrator
from nexus.core.state_contracts import NexusState

class TestBeliefEngine(unittest.TestCase):
    def test_update_and_retrieve(self):
        engine = BeliefEngine(Path("test_belief.json"))
        engine.update_belief("task-1", "PROT-DRIFT", 0.95, "EV-123")
        self.assertEqual(engine.assess_confidence("task-2", "PROT-DRIFT"), 0.95)
        if Path("test_belief.json").exists(): Path("test_belief.json").unlink()


def test_belief_engine_processes_structured_audit_outcome(tmp_path):
    engine = BeliefEngine(tmp_path / "belief.json")

    with patch("nexus.core.belief_engine.NexusTracer.record_belief_shift") as record_shift:
        out = engine.process_audit_outcome(
            AuditOutcome(
                task_id="task-1",
                assumption="AUDIT_FAILURE_1",
                passed=False,
                evidence_id="EV-FAIL",
                reason="claim missing evidence",
            )
        )

    assert out["confidence"] == 0.1
    assert engine.get_confidence("task-1", "AUDIT_FAILURE_1") == 0.1
    assert engine.beliefs["AUDIT_FAILURE_1"]["reason"] == "claim missing evidence"
    record_shift.assert_called_once_with("task-1", 0.7, 0.1)


def test_orchestrator_records_audit_failure_through_belief_gate_without_magicmock_detection():
    class FakeGate:
        def __init__(self):
            self.outcomes = []

        def process_audit_outcome(self, outcome):
            self.outcomes.append(outcome)
            return {"confidence": 0.1}

    gate = FakeGate()
    orch = NexusOrchestrator(
        OrchestratorConfig(task="task-1", skill_id="s1"),
        infra=SimpleNamespace(),
        intel=SimpleNamespace(belief_engine=gate, llm=SimpleNamespace(), commander=SimpleNamespace()),
        gov=SimpleNamespace(),
    )

    orch._record_audit_failure(strike=1, rebuttal="missing evidence")

    assert orch.belief_engine is gate
    assert gate.outcomes[0].task_id == "task-1"
    assert gate.outcomes[0].reason == "missing evidence"


def test_orchestrator_rejects_audit_when_belief_gate_unavailable(monkeypatch):
    class WriteOnlyGate:
        def process_audit_outcome(self, outcome):
            return {"accepted": bool(outcome.passed)}

    orch = NexusOrchestrator(
        OrchestratorConfig(task="task-1", skill_id="s1"),
        infra=SimpleNamespace(),
        intel=SimpleNamespace(belief_engine=WriteOnlyGate(), llm=SimpleNamespace(), commander=SimpleNamespace()),
        gov=SimpleNamespace(),
    )
    monkeypatch.setattr(orch.palace, "audit_action", lambda *_args, **_kwargs: True)

    passed, rebuttal = orch._run_adversarial_audit({"summary": "claim with evidence"})

    assert passed is False
    assert rebuttal == "Belief gate unavailable"


def test_context_hub_accepts_injected_dependencies_and_state_view(tmp_path):
    deps = ContextDependencies(
        memory_service=SimpleNamespace(cached_search=lambda _query: {"reminders": []}),
        wisdom_vault=SimpleNamespace(),
        belief_engine=SimpleNamespace(),
        knowledge_injector=SimpleNamespace(),
    )
    hub = ContextHub(str(tmp_path), deps=deps)

    decision = hub.make_pre_routing_decision(
        "context-task",
        {"complexity_score": 0.8},
        state_view=StateView(metadata={"task_type": "conversation"}, conversation_metadata={}),
    )

    assert hub.memory_service is deps.memory_service
    assert hub.wisdom_vault is deps.wisdom_vault
    assert hub.belief_engine is deps.belief_engine
    assert decision["mode"] == "conversation"
    assert decision["audit_level"] == "skip"
    assert decision["receipt_summary"] == {"selected": 0, "invoked": 0, "evidence": 0, "gate": 0}


def test_state_view_summarizes_route_and_report_receipts():
    view = StateView(
        metadata={},
        route_receipts=[{"selected": True, "invoked": True, "evidence_present": True}],
        report_receipts=[{"selected": True, "gate_passed": True}],
    )

    assert view.receipt_summary() == {"selected": 2, "invoked": 1, "evidence": 1, "gate": 1}


def test_context_hub_promotes_audit_when_receipts_have_actionable_gap(tmp_path):
    hub = ContextHub(
        str(tmp_path),
        deps=ContextDependencies(
            memory_service=SimpleNamespace(cached_search=lambda _query: {"reminders": []}),
            wisdom_vault=SimpleNamespace(),
            belief_engine=SimpleNamespace(),
            knowledge_injector=SimpleNamespace(),
        ),
    )

    decision = hub.make_pre_routing_decision(
        "receipt-gap-task",
        {},
        state_view=StateView(
            metadata={"task_type": "conversation"},
            conversation_metadata={},
            route_receipts=[{"selected": True, "invoked": False}],
        ),
    )

    assert decision["receipt_summary"] == {"selected": 1, "invoked": 0, "evidence": 0, "gate": 0}
    assert decision["audit_level"] == "full"
    assert decision["receipt_gap_reason"] == "selected_without_invocation"


def test_context_hub_ignores_non_actionable_receipt_gap(tmp_path):
    hub = ContextHub(
        str(tmp_path),
        deps=ContextDependencies(
            memory_service=SimpleNamespace(cached_search=lambda _query: {"reminders": []}),
            wisdom_vault=SimpleNamespace(),
            belief_engine=SimpleNamespace(),
            knowledge_injector=SimpleNamespace(),
        ),
    )

    decision = hub.make_pre_routing_decision(
        "non-actionable-gap",
        {},
        state_view=StateView(
            metadata={"task_type": "conversation"},
            conversation_metadata={},
            route_receipts=[{"selected": True, "invoked": False, "reason": "feature_flag_disabled"}],
        ),
    )

    assert decision["receipt_summary"] == {"selected": 1, "invoked": 0, "evidence": 0, "gate": 0}
    assert decision["audit_level"] == "skip"
    assert "receipt_gap_reason" not in decision


def test_learning_steward_emits_single_learning_action():
    state = NexusState(task_id="learn-steward")
    state.metadata["sir_veto_learning"] = True
    evidence = LearningEvidence(
        success=True,
        phases=["P", "A"],
        unique_phase_count=2,
        retry_count=0,
        policy_hit_count=0,
        patch_generated=False,
        patch_apply_success=False,
        proof_present=False,
        proof_type="",
        proof_value="",
        bayesian_aggression=0.5,
        entropy_score=0.0,
    )

    decision = LearningSteward(GovernanceProfile()).decide(state, evidence)

    assert decision.action == "FREEZE"
    assert decision.freeze_learning is True
    assert "sir_veto" in decision.reasons
    assert state.metadata["learning_frozen"] is True
    assert state.metadata["learning_action"] == "FREEZE"


def test_learning_steward_filters_successful_low_step_trajectory():
    state = NexusState(task_id="learn-low-step")
    evidence = LearningEvidence(
        success=True,
        phases=["P", "A"],
        unique_phase_count=2,
        retry_count=0,
        policy_hit_count=0,
        patch_generated=False,
        patch_apply_success=False,
        proof_present=False,
        proof_type="",
        proof_value="",
        bayesian_aggression=0.5,
        entropy_score=0.0,
        trajectory_step_count=2,
    )

    decision = LearningSteward(GovernanceProfile()).decide(state, evidence)

    assert decision.action == "FREEZE"
    assert decision.freeze_learning is True
    assert "low_step_trajectory" in decision.reasons
    assert state.metadata["low_step_filtered"] is True
    assert state.metadata["min_evolution_steps"] == 10


def test_belief_engine_promotes_semantic_searcher_refs_to_first_class_fields(tmp_path):
    engine = BeliefEngine(tmp_path / "belief.json")

    engine.process_audit_outcome(
        AuditOutcome(
            task_id="task-1",
            assumption="semantic evidence supports fix",
            passed=True,
            evidence_id="EV-1",
            metadata={
                "semantic_searcher_refs": ["semantic:policy:r1"],
                "semantic_searcher_confidence_source": "semantic_searcher:policy:r1",
            },
        )
    )

    stored = json.loads((tmp_path / "belief.json").read_text(encoding="utf-8"))
    belief = stored["semantic evidence supports fix"]
    assert belief["semantic_evidence_refs"] == ["semantic:policy:r1"]
    assert belief["semantic_confidence_source"] == "semantic_searcher:policy:r1"
