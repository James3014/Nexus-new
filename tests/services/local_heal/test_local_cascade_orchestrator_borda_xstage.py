from __future__ import annotations

import hashlib
import pytest
from dataclasses import FrozenInstanceError

from nexus.services.local_heal.local_cascade_orchestrator import (
    DEFAULT_CASCADE_MODELS,
    LocalCascadeRequest,
    LocalCascadeReceipt,
    run_local_cascade,
    run_local_cascade_with_borda,
)
from nexus.services.local_heal.local_model_provider import (
    InjectedLocalModelProvider,
    LocalModelProviderRequest,
)


def _all_succeed(req: LocalModelProviderRequest) -> str:
    if "3b" in req.model_name:
        return "minimal fix"
    if "7b" in req.model_name:
        return "better fix with error handling"
    if "9b" in req.model_name:
        return "comprehensive fix with tests"
    return "def foo(): pass"


class TestRunLocalCascadeWithBordaXStage:
    def test_run_local_cascade_with_borda_all_stages_succeed(self) -> None:
        provider = InjectedLocalModelProvider(_all_succeed)
        request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
        receipt, diversity_result = run_local_cascade_with_borda(request, provider=provider)
        assert len(receipt.stages_run) == 4
        assert not receipt.fail_closed
        assert receipt.winner_candidate_hash
        assert diversity_result is not None

    def test_run_local_cascade_with_borda_only_first_succeeds(self) -> None:
        def first_only(req: LocalModelProviderRequest) -> str:
            return "patch from first model"
        provider = InjectedLocalModelProvider(first_only)
        request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
        receipt, diversity_result = run_local_cascade_with_borda(request, provider=provider)
        assert len(receipt.stages_run) == 4
        assert not receipt.fail_closed
        assert diversity_result is not None

    def test_run_local_cascade_with_borda_no_candidates(self) -> None:
        provider = InjectedLocalModelProvider(lambda _: "")
        request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
        receipt, diversity_result = run_local_cascade_with_borda(request, provider=provider)
        assert receipt.fail_closed
        assert receipt.winner_model == ""
        assert diversity_result is None

    def test_run_local_cascade_with_borda_cross_stage_winner_field(self) -> None:
        provider = InjectedLocalModelProvider(_all_succeed)
        request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
        receipt, _ = run_local_cascade_with_borda(request, provider=provider)
        assert receipt.cross_stage_winner_stage
        assert receipt.cross_stage_winner_stage in DEFAULT_CASCADE_MODELS

    def test_run_local_cascade_with_borda_diversity_aware(self) -> None:
        def same_output(_req: LocalModelProviderRequest) -> str:
            return "identical patch from all models"
        provider = InjectedLocalModelProvider(same_output)
        request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
        receipt, diversity_result = run_local_cascade_with_borda(request, provider=provider)
        assert not receipt.fail_closed
        assert diversity_result is not None
        assert diversity_result.selection_strategy == "diversity_aware"

    def test_existing_run_local_cascade_unchanged(self) -> None:
        request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
        receipt = run_local_cascade(request)
        assert receipt.fail_closed
        assert len(receipt.stages_run) == 4

    def test_run_local_cascade_with_borda_uses_borda_count(self) -> None:
        def varied_quality(req: LocalModelProviderRequest) -> str:
            if "3b" in req.model_name:
                return "quick hack"
            if "7b" in req.model_name:
                return "proper fix"
            if "9b" in req.model_name:
                return "comprehensive solution"
            return "enterprise-grade refactor"
        provider = InjectedLocalModelProvider(varied_quality)
        request = LocalCascadeRequest(task_id="t1", problem_statement="fix bug")
        receipt, diversity_result = run_local_cascade_with_borda(request, provider=provider)
        assert not receipt.fail_closed
        assert receipt.winner_candidate_hash
        assert diversity_result is not None
        assert diversity_result.selected_index >= 0
