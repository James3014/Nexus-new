"""NEXUS_STATE_ROOT for belief, memory and learning stores (#2688).

Each site keeps its old root when the variable is unset and uses the env root
(the directory that contains ``.nexus``) when it is set.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.state_root import STATE_ROOT_ENV, persistent_state_root

LOCAL_HEAL_ROOT = Path(__import__("nexus").__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_state_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(STATE_ROOT_ENV, raising=False)


def _plan(constraints: dict[str, Any], task_id: str = "t-2688") -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id="p", task_id=task_id, phases=["R"], constraints=constraints
    )


# ── helper ────────────────────────────────────────────────────────────────────


def test_helper_unset_returns_default_object(tmp_path: Path) -> None:
    default = tmp_path / "ws"
    assert persistent_state_root(default) is default


def test_helper_empty_value_is_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_ROOT_ENV, "  ")
    default = tmp_path / "ws"
    assert persistent_state_root(default) is default


def test_helper_set_returns_resolved_env_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state" / ".." / "state"))
    assert persistent_state_root(tmp_path / "ws") == (tmp_path / "state").resolve()


def test_helper_expands_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(STATE_ROOT_ENV, "~/state")
    assert persistent_state_root(Path("x")) == (tmp_path / "state").resolve()


def test_helper_rejects_relative_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(STATE_ROOT_ENV, "relative/state")
    with pytest.raises(ValueError, match="absolute"):
        persistent_state_root(Path("x"))


# ── belief ────────────────────────────────────────────────────────────────────


def test_belief_default_file_unchanged_when_unset() -> None:
    from nexus.core.belief_engine import BeliefEngine

    engine = BeliefEngine()
    assert engine.state_file == Path(".nexus/belief_state.json")
    assert str(engine.state_file) == ".nexus/belief_state.json"


def test_belief_default_file_under_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.core.belief_engine import BeliefEngine

    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path))
    engine = BeliefEngine()
    assert engine.state_file == tmp_path.resolve() / ".nexus" / "belief_state.json"


def test_repair_target_key_is_stable() -> None:
    from nexus.core.belief_engine import repair_target_key

    assert repair_target_key("pkg/mod.py") == "repair_outcome:file:pkg/mod.py"
    assert repair_target_key("./pkg/mod.py") == repair_target_key("pkg/mod.py")
    assert repair_target_key("pkg\\mod.py") == repair_target_key("pkg/mod.py")
    assert repair_target_key("") == ""


def test_assess_confidence_exact_key_wins_over_target(tmp_path: Path) -> None:
    from nexus.core.belief_engine import BeliefEngine, repair_target_key

    engine = BeliefEngine(tmp_path / "b.json")
    engine.update_belief("t", repair_target_key("a.py"), 0.2, "ev1")
    engine.update_belief("t", "exact", 0.95, "ev2")
    assert engine.assess_confidence("t", "exact", target_file="a.py") == 0.95
    assert engine.assess_confidence("t", "other text", target_file="a.py") == 0.2
    assert engine.assess_confidence("t", "other text") == 0.7


def _heal_op(task_id: str, passed: bool) -> SimpleNamespace:
    return SimpleNamespace(
        instance_id=task_id,
        solve_eligible=passed,
        failure_reason="" if passed else "VERIFICATION_FAILED",
        receipt_path=f"receipt:{task_id}",
        localized_files=[SimpleNamespace(path="pkg/target.py")],
    )


def test_belief_round_trip_repair_write_changes_later_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed repair on a file lowers the confidence a later task reads for that file."""
    from nexus.core.belief_engine import BeliefEngine
    from nexus.core.capability_executor_registry import _exec_belief
    from nexus.services.local_heal.reasoning_advisory_bridge import apply_belief_update

    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    # Different cwd per "deploy": the store must not follow it.
    monkeypatch.chdir(tmp_path)

    plan = _plan(
        {"statement": "Fix the parser crash", "target_files": ["./pkg/target.py"]},
        task_id="later-task",
    )
    before = _exec_belief(plan, "Fix the parser crash")
    assert before.outcome["confidence"] == 0.7

    trace = apply_belief_update(_heal_op("earlier-task", passed=False))
    assert trace["belief_after"] < 0.7

    deploy2 = tmp_path / "a1-deploy2"
    deploy2.mkdir()
    monkeypatch.chdir(deploy2)
    after = _exec_belief(plan, "Fix the parser crash")
    assert after.outcome["confidence"] == pytest.approx(trace["belief_after"])
    # Other files are untouched.
    other = _exec_belief(_plan({"statement": "x", "target_file": "pkg/other.py"}), "x")
    assert other.outcome["confidence"] == 0.7
    # The repair path's own retry-budget read sees it as well.
    engine = BeliefEngine()
    assert engine.get_confidence(
        "new", "local_heal:new:repair_outcome", target_file="pkg/target.py"
    ) == pytest.approx(trace["belief_after"])
    assert (tmp_path / "state" / ".nexus" / "belief_state.json").is_file()
    assert not (deploy2 / ".nexus").exists()


def test_exec_belief_without_target_keeps_old_call_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.core import belief_engine
    from nexus.core.capability_executor_registry import _exec_belief

    calls: list[tuple[Any, ...]] = []

    class _Engine:
        def assess_confidence(self, task_id: str, assumption: str) -> float:
            calls.append((task_id, assumption))
            return 0.5

    monkeypatch.setattr(belief_engine, "BeliefEngine", _Engine)
    receipt = _exec_belief(_plan({"statement": "s"}), "s")
    assert receipt.outcome["confidence"] == 0.5
    assert calls == [("t-2688", "s")]


# ── learning closure / local_heal memory readers ──────────────────────────────


def test_learning_closure_bridge_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.services.local_heal.learning_closure_bridge import LearningClosureBridge

    bridge = LearningClosureBridge(enable_findings=False)
    assert bridge.project_root == LOCAL_HEAL_ROOT
    assert bridge.path == LOCAL_HEAL_ROOT / ".nexus/reports/learn/learning_closure.jsonl"

    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path))
    bridge = LearningClosureBridge(enable_findings=False)
    assert bridge.project_root == tmp_path.resolve()
    assert bridge.path == tmp_path.resolve() / ".nexus/reports/learn/learning_closure.jsonl"
    explicit = LearningClosureBridge(project_root=tmp_path / "x", enable_findings=False)
    assert explicit.project_root == tmp_path / "x"


def test_local_heal_memory_reader_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.services.local_heal import memory_retrieval_adapter as mra
    from nexus.services.local_heal.orchestrator import HealOrchestrator

    def roots() -> list[Path]:
        return [
            mra.LocalJsonlLessonStore().path,
            mra.FindingsMemoryLessonStore().project_root,
            mra.MemoryRepositoryLessonStore().project_root,
            mra.CanonicalEpisodicMemoryLessonStore().project_root,
            mra.CanonicalLessonStore().project_root,
            HealOrchestrator._learning_closure_path(),
        ]

    closure = Path(".nexus/reports/learn/learning_closure.jsonl")
    assert roots() == [LOCAL_HEAL_ROOT / closure] + [LOCAL_HEAL_ROOT] * 4 + [
        LOCAL_HEAL_ROOT / closure
    ]
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path))
    state = tmp_path.resolve()
    assert roots() == [state / closure] + [state] * 4 + [state / closure]


def test_runtime_compat_memory_adapter_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.services.runtime_compat import _build_default_memory_retrieval_adapter

    ws = tmp_path / "ws"
    stores = _build_default_memory_retrieval_adapter(ws).store.stores
    assert stores[1].project_root == ws.resolve()
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    stores = _build_default_memory_retrieval_adapter(ws).store.stores
    state = (tmp_path / "state").resolve()
    assert stores[0].path == state / ".nexus/reports/learn/learning_closure.jsonl"
    assert stores[1].project_root == state
    assert stores[2].project_root == state


# ── executor memory reads ─────────────────────────────────────────────────────


class _RepoSpy:
    paths: list[Path] = []

    def __init__(self, path: Path) -> None:
        type(self).paths.append(Path(path))

    def search_fts(self, *_a: Any, **_k: Any) -> list[Any]:
        return []

    def search(self, *_a: Any, **_k: Any) -> list[Any]:
        return []


@pytest.mark.parametrize("executor", ["_exec_lancedb", "_exec_semantic_searcher"])
def test_lancedb_executors_read_state_root(
    executor: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.core import capability_executor_registry as cer
    from nexus.services import memory_repository

    monkeypatch.setattr(memory_repository, "MemoryRepository", _RepoSpy)
    monkeypatch.setattr(
        cer,
        "_try_import_class",
        lambda *_a: lambda repo: SimpleNamespace(search=lambda **_k: []),
    )
    _RepoSpy.paths = []
    ws = tmp_path / "ws"
    plan = _plan({"workspace_root": str(ws), "search_query": "q"})
    getattr(cer, executor)(plan, "q")
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    getattr(cer, executor)(plan, "q")
    rel = Path(".nexus/knowledge/lancedb")
    assert _RepoSpy.paths == [ws.resolve() / rel, (tmp_path / "state").resolve() / rel]


def test_exec_memory_reads_state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.core.capability_executor_registry import _exec_memory

    ws = tmp_path / "ws"
    ws.mkdir()
    plan = _plan({"workspace_root": str(ws), "memory_query": "refund"})
    assert _exec_memory(plan, "refund").outcome["result"]["root"] == str(ws.resolve())
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    receipt = _exec_memory(plan, "refund")
    assert receipt.outcome["result"]["root"] == str((tmp_path / "state").resolve())


def test_learn_store_uses_state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.core.capability_executor_registry import _resolve_learn_store

    ws = tmp_path / "ws"
    plan = _plan({"workspace_root": str(ws)})
    assert _resolve_learn_store(plan)[:2] == (ws.resolve(), ws.resolve())
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    state = (tmp_path / "state").resolve()
    assert _resolve_learn_store(plan)[:2] == (state, state)
    isolated = _plan({"workspace_root": str(ws), "run_root": str(tmp_path / "run")})
    assert _resolve_learn_store(isolated)[1] == tmp_path / "run"


def test_capability_signal_set_memory_index_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.core import capability_signal_set as css

    seen: list[Path] = []

    def _spy(kind: str, root: Any, **_k: Any) -> Path:
        seen.append(Path(root))
        return tmp_path / "missing"

    monkeypatch.setattr(css, "resolve_lancedb_root", _spy)
    ctx = {"task_id": "t", "task_desc": "d"}
    css.CapabilitySignalSet.from_context(ctx, str(tmp_path / "ws"))
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    css.CapabilitySignalSet.from_context(ctx, str(tmp_path / "ws"))
    assert seen == [tmp_path / "ws", (tmp_path / "state").resolve()]


def test_meta_opt_writes_outcome_memory_under_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.core.capability_executor_registry import _exec_meta_opt

    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    ws = tmp_path / "ws"
    episode = {
        "task_id": "m1",
        "task_type": "codeintel",
        "task_desc": "d",
        "solved": True,
        "receipts": [{"name": "codeintel", "invoked": True, "gate_passed": True}],
    }
    receipt = _exec_meta_opt(_plan({"workspace_root": str(ws), "meta_opt_episode": episode}), "d")
    assert receipt.outcome.get("episode_persisted") is True
    state = (tmp_path / "state").resolve()
    assert (state / ".nexus" / "memory" / "outcome_history.jsonl").is_file()
    assert not (ws / ".nexus").exists()


# ── planner signals / learning policy ─────────────────────────────────────────


def test_collect_route_signals_reads_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research.flow import signal_collector as sc

    findings_roots: list[Path] = []
    history_roots: list[Path] = []

    class _Store:
        def __init__(self, root: Path) -> None:
            findings_roots.append(Path(root))

        def search(self, _q: str) -> list[Any]:
            return []

    def _history(root: Path, **_k: Any) -> dict[str, Any]:
        history_roots.append(Path(root))
        return {}

    monkeypatch.setattr(sc, "load_history_memory_signal", _history)

    def run() -> None:
        sc.collect_route_signals(
            repo_root=tmp_path / "ws",
            task_desc="fix bug in parser",
            task_type="bugfix",
            candidate_count=1,
            root_cause_confidence=0.5,
            findings_query="parser",
            findings_memory_store_cls=_Store,
        )

    run()
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    run()
    expected = [tmp_path / "ws", (tmp_path / "state").resolve()]
    assert findings_roots == expected
    assert history_roots == expected


def test_merge_runtime_learning_policy_reads_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.engine import learning_policy_loader as lpl

    seen: list[Path] = []

    def _spy(path: Path, store: Any = None) -> dict[str, Any]:
        seen.append(Path(path))
        return {}

    monkeypatch.setattr(lpl, "load_learning_policy_budget", _spy)
    lpl.merge_runtime_learning_policy(tmp_path / "ws")
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    lpl.merge_runtime_learning_policy(tmp_path / "ws")
    rel = lpl.DEFAULT_PROMOTED_POLICY_PATH
    assert seen == [tmp_path / "ws" / rel, (tmp_path / "state").resolve() / rel]
