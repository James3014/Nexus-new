from pathlib import Path
from unittest.mock import MagicMock

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import get_executor
from nexus.orchestrator.integration_manager import (
    LEGACY_INTEGRATION_PATH_RETIRED,
    IntegrationManager,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_legacy_batch_integrate_is_quarantined_without_side_effects(tmp_path):
    state_store = MagicMock()
    evidence_collector = MagicMock()
    manager = IntegrationManager(
        state_store,
        evidence_collector,
        repo_root=tmp_path,
        require_clean_preflight=True,
    )

    success, failed = manager.batch_integrate(["TASK-001"], target_branch="main")

    assert success == []
    assert failed == [LEGACY_INTEGRATION_PATH_RETIRED]
    assert state_store.mock_calls == []
    assert evidence_collector.mock_calls == []
    assert not hasattr(manager, "_run_git")


def test_integration_manager_capability_is_compatibility_block_not_mutation():
    executor = get_executor("integration_manager")
    assert executor is not None
    plan = CapabilityExecutionPlan(
        plan_id="legacy-integration-retired",
        task_id="legacy-integration-task",
        phases=["R"],
        constraints={
            "workspace_root": "/tmp/should-not-be-used",
            "integration_task_ids": ["TASK-001"],
            "integration_target_branch": "main",
            "integration_state_dir": "/tmp/should-not-be-used-state",
        },
    )

    receipt = executor(plan, "attempt retired legacy integration")
    outcome = dict(receipt.outcome or {})

    assert receipt.invoked is True
    assert receipt.gate_passed is False
    assert outcome["semantic_status"] == "BLOCKED"
    assert outcome["error"] == LEGACY_INTEGRATION_PATH_RETIRED
    assert outcome["mutation_performed"] is False
    assert "physical_callable" not in outcome
    assert outcome["replacement_callable"].endswith(
        "SelfHostedTaskService.integrate_approved"
    )


def test_production_surfaces_do_not_import_or_invoke_legacy_integration_manager():
    production_surfaces = (
        "scripts/engine/commands/multi_agent_actions.py",
        "nexus/core/capability_executor_registry.py",
    )

    for relative_path in production_surfaces:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "from nexus.orchestrator.integration_manager import IntegrationManager"
            not in source
        )
        assert ".batch_integrate(" not in source
