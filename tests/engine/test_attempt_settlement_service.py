import json
from pathlib import Path
from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.attempt_settlement_service import AttemptSettlementService


def _make_service(tmp_path: Path):
    metrics_agg = MagicMock()
    crystallize_fn = MagicMock()
    transaction_mgr = MagicMock()
    learning_finalize_fn = MagicMock()
    reflex_loop = MagicMock()
    service = AttemptSettlementService(
        project_root=tmp_path,
        run_dir=tmp_path / ".nexus" / "runs" / "t1",
        metrics_agg=metrics_agg,
        crystallize_fn=crystallize_fn,
        transaction_mgr=transaction_mgr,
        learning_finalize_fn=learning_finalize_fn,
        reflex_loop=reflex_loop,
    )
    return service, metrics_agg, crystallize_fn, transaction_mgr, learning_finalize_fn, reflex_loop


def test_attempt_settlement_success_path(tmp_path: Path):
    service, metrics_agg, crystallize_fn, tx, learning_finalize, reflex = _make_service(tmp_path)
    state = NexusState(task_id="task-1")
    metrics_agg.aggregate_crystallize_payload.return_value = {"task_id": "task-1", "passed": True}
    learning_finalize.return_value = {"writeback_required": False}
    gate_results = [{"cmd": "pytest", "exit_code": 0, "passed": True}]

    decision = service.settle_attempt(
        task_id="task-1",
        skill_id="nexus:bug",
        state=state,
        passed=True,
        gate_results=gate_results,
    )

    assert decision == "success"
    tx.commit_if_passed.assert_called_once_with("task-1")
    tx.audit_rollback.assert_not_called()
    crystallize_fn.assert_called_once()
    reflex.run_cycle.assert_called_once()
    evidence_path = tmp_path / ".nexus" / "reports" / "hallucination_evidence.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["_source"] == "system"
    assert payload["evidence_bundle"]["aggregates"]["success_rate"] == 1.0


def test_attempt_settlement_writeback_pending_path(tmp_path: Path):
    service, metrics_agg, _crystallize_fn, tx, learning_finalize, _reflex = _make_service(tmp_path)
    state = NexusState(task_id="task-2")
    metrics_agg.aggregate_crystallize_payload.return_value = {"task_id": "task-2", "passed": True}
    learning_finalize.return_value = {"writeback_required": True}

    decision = service.settle_attempt(
        task_id="task-2",
        skill_id="nexus:bug",
        state=state,
        passed=True,
        gate_results=[{"cmd": "pytest", "exit_code": 0, "passed": True}],
    )

    assert decision == "writeback_pending"
    assert state.metadata["delivery_status"] == "code_done_writeback_pending"
    tx.commit_if_passed.assert_not_called()
    tx.audit_rollback.assert_called_once_with("task-2")


def test_attempt_settlement_retry_path(tmp_path: Path):
    service, metrics_agg, _crystallize_fn, tx, learning_finalize, _reflex = _make_service(tmp_path)
    state = NexusState(task_id="task-3")
    metrics_agg.aggregate_crystallize_payload.return_value = {"task_id": "task-3", "passed": False}
    learning_finalize.return_value = {"writeback_required": False}

    decision = service.settle_attempt(
        task_id="task-3",
        skill_id="nexus:bug",
        state=state,
        passed=False,
        gate_results=[{"cmd": "pytest", "exit_code": 1, "passed": False}],
    )

    assert decision == "retry"
    tx.commit_if_passed.assert_not_called()
    tx.audit_rollback.assert_called_once_with("task-3")
