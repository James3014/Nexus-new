import unittest
from pathlib import Path
from types import SimpleNamespace

from nexus.core.belief_contracts import AuditOutcome
from nexus.core.belief_engine import BeliefEngine
from nexus.core.context_hub import ContextDependencies, ContextHub, StateView
from nexus.core.learning_evidence import LearningEvidence
from nexus.core.learning_steward import GovernanceProfile, LearningSteward
from nexus.core.state_contracts import NexusState

class TestBeliefEngine(unittest.TestCase):
    def test_update_and_retrieve(self):
        engine = BeliefEngine(Path("test_belief.json"))
        engine.update_belief("task-1", "PROT-DRIFT", 0.95, "EV-123")
        self.assertEqual(engine.assess_confidence("task-2", "PROT-DRIFT"), 0.95)
        if Path("test_belief.json").exists(): Path("test_belief.json").unlink()


def test_belief_engine_processes_structured_audit_outcome(tmp_path):
    engine = BeliefEngine(tmp_path / "belief.json")

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


def test_state_view_summarizes_route_and_report_receipts():
    view = StateView(
        metadata={},
        route_receipts=[{"selected": True, "invoked": True, "evidence_present": True}],
        report_receipts=[{"selected": True, "gate_passed": True}],
    )

    assert view.receipt_summary() == {"selected": 2, "invoked": 1, "evidence": 1, "gate": 1}


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
