from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from nexus.services.local_heal.local_cascade_orchestrator import (
    DEFAULT_CASCADE_MODELS,
    LocalCascadeRequest,
    LocalCascadeReceipt,
    run_local_cascade,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)


def test_run_local_cascade_default_4_models():
    request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
    receipt = run_local_cascade(request)
    assert len(receipt.stages_run) == 4
    assert receipt.stages_run == DEFAULT_CASCADE_MODELS
    assert receipt.failed_at_final_stage
    assert receipt.fail_closed


def test_run_local_cascade_stops_at_first_success():
    def first_succeeds(_req: LocalModelProviderRequest) -> str:
        return "def foo(): pass"
    provider = InjectedLocalModelProvider(first_succeeds)
    request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
    receipt = run_local_cascade(request, provider=provider)
    assert receipt.winner_model == DEFAULT_CASCADE_MODELS[0]
    assert not receipt.failed_at_final_stage
    assert not receipt.fail_closed
    assert len(receipt.stages_run) == 1
    assert len(receipt.stages_failed) == 0


def test_run_local_cascade_escalates_on_failure():
    call_count = [0]
    def fail_then_succeed(req: LocalModelProviderRequest) -> str:
        call_count[0] += 1
        if call_count[0] == 1:
            return ""
        return "def bar(): pass"
    provider = InjectedLocalModelProvider(fail_then_succeed)
    request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
    receipt = run_local_cascade(request, provider=provider)
    assert receipt.winner_model == DEFAULT_CASCADE_MODELS[1]
    assert not receipt.failed_at_final_stage
    assert not receipt.fail_closed
    assert len(receipt.stages_run) == 2
    assert len(receipt.stages_failed) == 1
    assert receipt.stages_failed[0] == DEFAULT_CASCADE_MODELS[0]


def test_run_local_cascade_all_fail_returns_fail_closed():
    request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
    receipt = run_local_cascade(request)
    assert receipt.failed_at_final_stage
    assert receipt.fail_closed
    assert receipt.winner_model == ""
    assert receipt.winner_candidate_hash == ""
    assert len(receipt.stages_failed) == 4


def test_run_local_cascade_uses_inert_provider():
    request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
    receipt = run_local_cascade(request)
    assert receipt.failed_at_final_stage
    assert receipt.fail_closed




def test_local_cascade_request_frozen():
    request = LocalCascadeRequest(task_id="t1", problem_statement="fix")
    with pytest.raises(FrozenInstanceError):
        request.task_id = "t2"


def test_local_cascade_receipt_frozen():
    receipt = LocalCascadeReceipt(
        task_id="t1", stages_run=(), stages_failed=(),
        winner_model="", winner_candidate_hash="",
        failed_at_final_stage=True, fail_closed=True,
    )
    with pytest.raises(FrozenInstanceError):
        receipt.task_id = "t2"
