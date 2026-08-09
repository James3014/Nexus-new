from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from unittest.mock import patch
from types import SimpleNamespace

from nexus.core.router import SkillsRouter


class _MockPlan:
    plan_id = "p1"
    task_id = "t001"


@dataclass(frozen=True)
class _MockCapReceipt:
    capability_name: str = "mock_cap"
    selected: bool = True
    invoked: bool = True
    evidence_id: str = "ev_001"
    gate_passed: bool = True
    outcome: dict = field(default_factory=lambda: {"status": "pass"})
    evidence_alignment: bool = True
    telemetries: dict = field(default_factory=lambda: {"wall_time_ms": 100, "token_usage": 50, "model_calls": 1, "telemetry_source": "measured"})
    timestamp: str = "2026-01-01T00:00:00"
    skill_receipts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


def _setup_router(tmp_path: Path, run_dir: str | None = None) -> SkillsRouter:
    return SkillsRouter(project_root=str(tmp_path), run_dir=run_dir or str(tmp_path / ".nexus" / "runs" / "t"))


SELECTOR_PATH = "nexus.core.capability_selector.CapabilitySelector"
EXECUTOR_PATH = "nexus.core.executor_controls.ExecutorControls"
OUTCOME_PATH = "nexus.learning.outcome_memory.OutcomeMemoryManager.save_episode_and_tune_sync"


def test_router_writes_outcome_memory_after_routing(tmp_path: Path):
    router = _setup_router(tmp_path)
    context = {"task_id": "t001", "task_desc": "test task"}
    mock_receipts = [_MockCapReceipt()]
    with patch(SELECTOR_PATH) as MockSel:
        MockSel.return_value.select_capabilities.return_value = _MockPlan()
        with patch(EXECUTOR_PATH) as MockCtrl:
            MockCtrl.return_value.execute_plan.return_value = mock_receipts
            with patch(OUTCOME_PATH) as mock_save:
                router.route_candidates("R", context)
                mock_save.assert_called_once()


def test_router_outcome_memory_failure_does_not_block(tmp_path: Path):
    router = _setup_router(tmp_path)
    context = {"task_id": "t002", "task_desc": "test task"}
    mock_receipts = [_MockCapReceipt()]
    with patch(SELECTOR_PATH) as MockSel:
        MockSel.return_value.select_capabilities.return_value = _MockPlan()
        with patch(EXECUTOR_PATH) as MockCtrl:
            MockCtrl.return_value.execute_plan.return_value = mock_receipts
            with patch(OUTCOME_PATH, side_effect=RuntimeError("boom")) as mock_save:
                candidates = router.route_candidates("R", context)
                assert candidates is not None


def test_router_outcome_memory_disabled_with_env(tmp_path: Path):
    os.environ["NEXUS_LEARNING_LOOP_WRITE_ENABLED"] = "0"
    try:
        router = _setup_router(tmp_path)
        context = {"task_id": "t003", "task_desc": "test task"}
        mock_receipts = [_MockCapReceipt()]
        with patch(SELECTOR_PATH) as MockSel:
            MockSel.return_value.select_capabilities.return_value = _MockPlan()
            with patch(EXECUTOR_PATH) as MockCtrl:
                MockCtrl.return_value.execute_plan.return_value = mock_receipts
                with patch(OUTCOME_PATH) as mock_save:
                    router.route_candidates("R", context)
                    mock_save.assert_not_called()
    finally:
        os.environ.pop("NEXUS_LEARNING_LOOP_WRITE_ENABLED", None)


def test_router_outcome_memory_episode_data_correct(tmp_path: Path):
    router = _setup_router(tmp_path)
    context = {"task_id": "t004", "task_desc": "episode test"}
    mock_receipts = [_MockCapReceipt(capability_name="cap_a")]
    with patch(SELECTOR_PATH) as MockSel:
        MockSel.return_value.select_capabilities.return_value = _MockPlan()
        with patch(EXECUTOR_PATH) as MockCtrl:
            MockCtrl.return_value.execute_plan.return_value = mock_receipts
            with patch(OUTCOME_PATH) as mock_save:
                router.route_candidates("D", context)
                (args, _kwargs) = mock_save.call_args
                episode = args[0]
                assert episode.task_id == "t004", f"expected t004 got {episode.task_id!r}"
                assert episode.task_type == "d"
                assert episode.solved is True
                assert episode.wall_duration_sec > 0
                assert episode.total_tokens_used > 0
                assert episode.trust_mismatch is False
                assert len(episode.receipts) > 0


def test_router_existing_learning_closure_unchanged(tmp_path: Path):
    router = _setup_router(tmp_path)
    context = {"task_id": "t005", "task_desc": "closure check"}
    closure_dir = tmp_path / ".nexus" / "reports" / "learn"
    closure_dir.mkdir(parents=True, exist_ok=True)
    closure_file = closure_dir / "learning_closure.jsonl"
    closure_file.write_text(json.dumps({"existing": "entry"}) + "\n", encoding="utf-8")
    mock_receipts = [_MockCapReceipt(capability_name="cap_b")]
    with patch(SELECTOR_PATH) as MockSel:
        MockSel.return_value.select_capabilities.return_value = _MockPlan()
        with patch(EXECUTOR_PATH) as MockCtrl:
            MockCtrl.return_value.execute_plan.return_value = mock_receipts
            with patch(OUTCOME_PATH):
                router.route_candidates("R", context)
                lines = closure_file.read_text(encoding="utf-8").splitlines()
                assert len(lines) == 2  # existing + new
                last_row = json.loads(lines[-1])
                assert last_row["capability_name"] == "cap_b"


def test_router_empty_receipts_are_unverified_not_success(tmp_path: Path):
    router = _setup_router(tmp_path)
    context = {"task_id": "t-empty", "task_desc": "no receipt"}
    with patch(SELECTOR_PATH) as MockSel:
        MockSel.return_value.select_capabilities.return_value = _MockPlan()
        with patch(EXECUTOR_PATH) as MockCtrl:
            MockCtrl.return_value.execute_plan.return_value = []
            with patch(OUTCOME_PATH):
                router.route_candidates("R", context)
    ledger = tmp_path / ".nexus" / "memory" / "learning_episodes.jsonl"
    episode = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert episode["terminal_outcome"] == "UNVERIFIED"
    assert episode["stages"]["outcome_measured"] is False


def test_localheal_adoption_requires_patch_and_verifier_receipts():
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from nexus.services.local_heal.memory_trace import MemoryTrace

    orchestrator = HealOrchestrator.__new__(HealOrchestrator)
    ctx = SimpleNamespace(op=SimpleNamespace(
        _memory_influence_trace=MemoryTrace(
            trace_status="TRACE_AVAILABLE",
            prompt_included=True,
            memory_evidence_ids=["lesson-1"],
        ),
        applied_patch_hash="patch-hash",
        selected_candidate_hash_matches_applied=True,
        verifier_receipt=SimpleNamespace(verifier_status="pass", receipt_id="verifier-1"),
        patch_receipt_path="patch-1",
    ))

    orchestrator._record_authoritative_memory_adoption(ctx)

    assert ctx.op.applied_lesson_ids == ["lesson-1"]
    assert ctx.op.applied_lesson_attribution["lesson-1"]["verifier_receipt"] == "verifier-1"


def test_localheal_adoption_fails_closed_without_receipts():
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from nexus.services.local_heal.memory_trace import MemoryTrace

    orchestrator = HealOrchestrator.__new__(HealOrchestrator)
    ctx = SimpleNamespace(op=SimpleNamespace(
        _memory_influence_trace=MemoryTrace(
            trace_status="TRACE_AVAILABLE",
            prompt_included=True,
            memory_evidence_ids=["lesson-1"],
        ),
        solve_eligible=True,
    ))

    orchestrator._record_authoritative_memory_adoption(ctx)

    assert ctx.op.applied_lesson_ids == []
    assert ctx.op.applied_lesson_attribution == {}
