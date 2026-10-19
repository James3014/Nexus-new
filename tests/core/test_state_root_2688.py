"""NEXUS_STATE_ROOT for belief, memory and learning stores (#2688).

The per-deploy roots (this checkout, the cwd, NEXUS_CANONICAL_SOURCE_ROOT) move to the
state root; any other root stays put.  Unset keeps every path as before.  Tests put
the "deploy" in ``tmp_path / "deploy-N"`` by chdir-ing into it.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.state_root import (
    CANONICAL_SOURCE_ROOT_ENV,
    STATE_ROOT_ENV,
    configured_state_root,
    persistent_state_root,
    rebase_state_path,
)

CODE_ROOT = Path(__import__("nexus").__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (STATE_ROOT_ENV, CANONICAL_SOURCE_ROOT_ENV, "NEXUS_MEMORY_DB_PATH"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def deploy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Env set, cwd = a per-deploy dir; ``next()`` switches to a fresh deploy dir."""
    state = tmp_path / "state"
    monkeypatch.setenv(STATE_ROOT_ENV, str(state))
    counter = {"n": 0}

    def next_deploy() -> Path:
        counter["n"] += 1
        ws = tmp_path / f"a1-deploy{counter['n']}"
        ws.mkdir()
        monkeypatch.chdir(ws)
        return ws

    ws = next_deploy()
    return SimpleNamespace(state=state.resolve(), ws=ws, next=next_deploy, tmp=tmp_path)


def _plan(constraints: dict[str, Any], task_id: str = "t-2688") -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id="p", task_id=task_id, phases=["R"], constraints=constraints
    )


# ── helper ────────────────────────────────────────────────────────────────────


def test_helper_unset_returns_same_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for default in (tmp_path, Path("."), ".", CODE_ROOT):
        assert persistent_state_root(default) is default
    path = tmp_path / ".nexus" / "x.json"
    assert rebase_state_path(path) is path
    monkeypatch.setenv(STATE_ROOT_ENV, "  ")
    assert persistent_state_root(tmp_path) is tmp_path


def test_helper_moves_only_deploy_roots(deploy: SimpleNamespace, monkeypatch) -> None:
    assert persistent_state_root(deploy.ws) == deploy.state
    assert persistent_state_root(Path(".")) == deploy.state
    assert persistent_state_root(str(deploy.ws)) == deploy.state
    assert persistent_state_root(CODE_ROOT) == deploy.state
    assert persistent_state_root(deploy.state) == deploy.state
    isolated = deploy.tmp / "canary"
    assert persistent_state_root(isolated) is isolated
    controller = deploy.tmp / "controller"
    assert persistent_state_root(controller) is controller
    monkeypatch.setenv(CANONICAL_SOURCE_ROOT_ENV, str(controller))
    assert persistent_state_root(controller) == deploy.state


def test_helper_expands_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv(STATE_ROOT_ENV, "~/state")
    assert configured_state_root() == (tmp_path / "state").resolve()


def test_helper_relative_value_warns_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(STATE_ROOT_ENV, "relative/state")
    with caplog.at_level("WARNING"):
        assert persistent_state_root(tmp_path) is tmp_path
    assert "not an absolute path" in caplog.text


def test_rebase_state_path(deploy: SimpleNamespace) -> None:
    rel = Path(".nexus/policy/promoted_learning_policy.json")
    assert rebase_state_path(deploy.ws / rel) == deploy.state / rel
    assert rebase_state_path(rel) == deploy.state / rel
    other = deploy.tmp / "proj" / rel
    assert rebase_state_path(other) is other
    plain = deploy.ws / "notes.txt"
    assert rebase_state_path(plain) is plain


def test_relative_env_does_not_break_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.core.capability_signal_set import CapabilitySignalSet
    from nexus.research.flow.signal_collector import collect_route_signals

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(STATE_ROOT_ENV, "relative/state")
    signals = collect_route_signals(
        repo_root=tmp_path,
        task_desc="fix bug in parser",
        task_type="bugfix",
        candidate_count=1,
        root_cause_confidence=0.5,
        findings_query="parser",
    )
    assert signals is not None
    snap = CapabilitySignalSet.from_context({"task_id": "t", "task_desc": "d"}, str(tmp_path))
    assert snap.belief_confidence == 0.7
    assert not (tmp_path / "relative").exists()


# ── belief ────────────────────────────────────────────────────────────────────


def test_belief_default_file_unchanged_when_unset() -> None:
    from nexus.core.belief_engine import BeliefEngine

    assert str(BeliefEngine().state_file) == ".nexus/belief_state.json"


def test_belief_explicit_and_default_paths_share_the_state_file(deploy: SimpleNamespace) -> None:
    """context_hub-style explicit paths and the default engine see one store."""
    from nexus.core.belief_engine import BeliefEngine

    BeliefEngine(deploy.ws / ".nexus" / "belief_state.json").update_belief("t", "k", 0.33, "e")
    deploy.next()
    assert BeliefEngine().assess_confidence("t", "k") == 0.33
    assert (deploy.state / ".nexus" / "belief_state.json").is_file()
    isolated = deploy.tmp / "iso" / ".nexus" / "belief_state.json"
    assert BeliefEngine(isolated).state_file == isolated


def test_belief_concurrent_engines_keep_each_others_keys(tmp_path: Path) -> None:
    from nexus.core.belief_engine import BeliefEngine

    path = tmp_path / "belief.json"
    first, second = BeliefEngine(path), BeliefEngine(path)
    first.update_belief("t", "a", 0.1, "e1")
    second.update_belief("t", "b", 0.2, "e2")
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["a"]["confidence"] == 0.1 and stored["b"]["confidence"] == 0.2
    assert BeliefEngine(path).assess_confidence("t", "a") == 0.1


def test_repair_target_key_normalizes_and_rejects() -> None:
    from nexus.core.belief_engine import repair_target_key

    key = "repair_outcome:file:pkg/mod.py"
    for raw in (
        "pkg/mod.py",
        "./pkg/mod.py",
        "pkg//mod.py",
        "pkg/./mod.py",
        "pkg\\mod.py",
        "pkg/x/../mod.py",
    ):
        assert repair_target_key(raw) == key, raw
    for raw in ("", ".", "/abs/pkg/mod.py", "../other/mod.py", "pkg/../../x.py", "C:/x.py", ".."):
        assert repair_target_key(raw) == "", raw


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


def test_belief_round_trip_repair_write_changes_later_read(deploy: SimpleNamespace) -> None:
    """A failed repair on a file lowers the confidence a later task reads for that file."""
    from nexus.core.belief_engine import BeliefEngine
    from nexus.core.capability_executor_registry import _exec_belief
    from nexus.core.capability_signal_set import CapabilitySignalSet
    from nexus.services.local_heal.reasoning_advisory_bridge import apply_belief_update

    plan = _plan(
        {"statement": "Fix the parser crash", "target_files": ["./pkg/target.py"]},
        task_id="later-task",
    )
    assert _exec_belief(plan, "Fix the parser crash").outcome["confidence"] == 0.7

    trace = apply_belief_update(_heal_op("earlier-task", passed=False))
    assert trace["belief_after"] < 0.7

    ws2 = deploy.next()
    after = _exec_belief(plan, "Fix the parser crash")
    assert after.outcome["confidence"] == pytest.approx(trace["belief_after"])
    other = _exec_belief(_plan({"statement": "x", "target_file": "pkg/other.py"}), "x")
    assert other.outcome["confidence"] == 0.7
    engine = BeliefEngine()
    assert engine.get_confidence(
        "new", "local_heal:new:repair_outcome", target_file="pkg/target.py"
    ) == pytest.approx(trace["belief_after"])
    snap = CapabilitySignalSet.from_context(
        {"task_id": "r", "task_desc": "route", "target_files": ["pkg/target.py"]},
        str(ws2),
        belief_engine=engine,
    )
    assert snap.belief_confidence == pytest.approx(trace["belief_after"])
    assert not (ws2 / ".nexus").exists()


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


# ── findings memory / learning closure ────────────────────────────────────────


def test_findings_writer_and_readers_share_the_state_root(deploy: SimpleNamespace) -> None:
    from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
    from nexus.services.local_heal.memory_retrieval_adapter import FindingsMemoryLessonStore

    FindingsMemoryStore(deploy.ws).write(
        FindingsCard(
            title="parser crash lesson",
            body="parser crash fixed by guard",
            retrieval_hints=["parser crash"],
            task_id="w1",
        )
    )
    deploy.next()
    hits = FindingsMemoryStore(Path(".")).search("parser crash")
    assert hits, "reader in a new deploy must see the card"
    assert FindingsMemoryLessonStore().project_root == deploy.state
    assert (deploy.state / ".nexus" / "memory").is_dir()
    isolated = deploy.tmp / "canary"
    assert FindingsMemoryStore(isolated).base_path == isolated / ".nexus" / "memory"


def test_learning_closure_bridge_one_root(deploy: SimpleNamespace) -> None:
    from nexus.services.local_heal.learning_closure_bridge import LearningClosureBridge

    jsonl = Path(".nexus/reports/learn/learning_closure.jsonl")
    bridge = LearningClosureBridge(enable_findings=False)
    assert (bridge.project_root, bridge.path) == (deploy.state, deploy.state / jsonl)
    explicit = deploy.tmp / "iso"
    bridge = LearningClosureBridge(project_root=explicit, enable_findings=False)
    assert (bridge.project_root, bridge.path) == (explicit, explicit / jsonl)


def test_learning_closure_bridge_unset_unchanged(tmp_path: Path) -> None:
    from nexus.services.local_heal.learning_closure_bridge import LearningClosureBridge

    bridge = LearningClosureBridge(enable_findings=False)
    assert bridge.project_root == CODE_ROOT
    assert bridge.path == CODE_ROOT / ".nexus/reports/learn/learning_closure.jsonl"
    bridge = LearningClosureBridge(project_root=tmp_path, enable_findings=False)
    assert bridge.project_root == tmp_path
    assert bridge.path == CODE_ROOT / ".nexus/reports/learn/learning_closure.jsonl"


def test_local_heal_memory_readers(deploy: SimpleNamespace) -> None:
    from nexus.services.local_heal import memory_retrieval_adapter as mra
    from nexus.services.local_heal.orchestrator import HealOrchestrator
    from nexus.services.runtime_compat import _build_default_memory_retrieval_adapter

    closure = deploy.state / ".nexus/reports/learn/learning_closure.jsonl"
    assert mra.LocalJsonlLessonStore().path == closure
    assert HealOrchestrator._learning_closure_path() == closure
    for cls in (
        mra.FindingsMemoryLessonStore,
        mra.MemoryRepositoryLessonStore,
        mra.CanonicalEpisodicMemoryLessonStore,
        mra.CanonicalLessonStore,
    ):
        assert cls().project_root == deploy.state, cls
        assert cls(project_root=deploy.ws).project_root == deploy.state, cls
    stores = _build_default_memory_retrieval_adapter(deploy.ws).store.stores
    assert stores[0].path == closure
    assert stores[1].project_root == stores[2].project_root == deploy.state


# ── executors / lancedb / project memory ──────────────────────────────────────


def test_lancedb_roots_follow_state_root(deploy: SimpleNamespace, monkeypatch) -> None:
    from nexus.services.lancedb_roots import KNOWLEDGE, MEMORY_INDEX, resolve_lancedb_root

    assert resolve_lancedb_root(KNOWLEDGE, deploy.ws, honor_env=False) == (
        deploy.state / ".nexus/knowledge/lancedb"
    )
    assert resolve_lancedb_root(MEMORY_INDEX, ".", honor_env=False) == (
        deploy.state / ".nexus/memory/memory_index.lancedb"
    )
    canary = deploy.tmp / "canary"
    assert resolve_lancedb_root(KNOWLEDGE, canary, honor_env=False) == (
        canary / ".nexus/knowledge/lancedb"
    )
    monkeypatch.setenv("NEXUS_MEMORY_DB_PATH", str(deploy.tmp / "override"))
    assert resolve_lancedb_root(KNOWLEDGE, deploy.ws) == deploy.tmp / "override"


def test_exec_memory_reads_state_root(deploy: SimpleNamespace) -> None:
    from nexus.core.capability_executor_registry import _exec_memory
    from nexus.core.memory_manager import ProjectMemoryManager

    ProjectMemoryManager(deploy.ws).add_insight("refund", "refund window is 30 days", "RCA")
    ws2 = deploy.next()
    plan = _plan({"workspace_root": str(ws2), "memory_query": "refund window"})
    receipt = _exec_memory(plan, "refund window")
    assert receipt.outcome["result"]["root"] == str(deploy.state)
    assert receipt.outcome["hit_count"] >= 1
    assert (deploy.state / ".nexus/state/project_memory.sqlite").is_file()


def test_exec_memory_unset_unchanged(tmp_path: Path) -> None:
    from nexus.core.capability_executor_registry import _exec_memory

    plan = _plan({"workspace_root": str(tmp_path), "memory_query": "refund"})
    assert _exec_memory(plan, "refund").outcome["result"]["root"] == str(tmp_path.resolve())


def test_learn_executor_and_flow_share_phase_slo(deploy: SimpleNamespace) -> None:
    from nexus.core.capability_executor_registry import _resolve_learn_store
    from nexus.research.flow.runtime_state import read_phase_slo_summary_fast
    from nexus.research.learn_mode import LearnModeService

    project_root, run_root, _ = _resolve_learn_store(_plan({"workspace_root": str(deploy.ws)}))
    assert (project_root, run_root) == (deploy.ws.resolve(), deploy.state)
    LearnModeService(project_root=project_root, run_root=run_root).build_phase_slo_report(window=1)
    ws2 = deploy.next()
    assert LearnModeService(ws2).phase_slo_summary_path.is_file()
    assert read_phase_slo_summary_fast(ws2).get("reason") != "phase_slo_summary_missing"
    isolated = _plan({"workspace_root": str(deploy.ws), "run_root": str(deploy.tmp / "run")})
    assert _resolve_learn_store(isolated)[1] == deploy.tmp / "run"


def test_learn_store_unset_unchanged(tmp_path: Path) -> None:
    from nexus.core.capability_executor_registry import _resolve_learn_store

    ws = tmp_path / "ws"
    assert _resolve_learn_store(_plan({"workspace_root": str(ws)}))[:2] == (
        ws.resolve(),
        ws.resolve(),
    )


def test_auto_flow_history_shared(deploy: SimpleNamespace) -> None:
    from nexus.research.flow.history_signal_store import HistorySignalStore

    HistorySignalStore(deploy.ws).write_recent_for(
        target_file="a.py", test_file="t.py", recent=[{"x": 1}], max_items=5
    )
    ws2 = deploy.next()
    assert HistorySignalStore(ws2).recent_for(target_file="a.py", test_file="t.py") == [{"x": 1}]


# ── learning policy / outcome memory ──────────────────────────────────────────


def test_outcome_memory_dynamic_policy_visible_to_loader(
    deploy: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.core.capability_executor_registry import _exec_meta_opt
    from nexus.engine import learning_policy_loader as lpl

    episode = {
        "task_id": "m1",
        "task_type": "codeintel",
        "task_desc": "d",
        "solved": True,
        "receipts": [{"name": "codeintel", "invoked": True, "gate_passed": True}],
    }
    receipt = _exec_meta_opt(
        _plan({"workspace_root": str(deploy.ws), "meta_opt_episode": episode}), "d"
    )
    assert receipt.outcome.get("episode_persisted") is True
    assert (deploy.state / ".nexus/memory/outcome_history.jsonl").is_file()

    seen: dict[str, Any] = {}
    real_dynamic = lpl.load_dynamic_learning_policy_budget

    def _dynamic(path: Path, store: Any = None) -> dict[str, Any]:
        seen["dynamic"] = Path(path)
        return real_dynamic(path, store=store)

    def _governed(project_root: Path, **_k: Any) -> dict[str, Any]:
        seen["governed"] = Path(project_root)
        return {}

    def _route_cost(
        project_root: Path, budget: dict[str, Any], store: Any = None
    ) -> dict[str, Any]:
        seen["route_cost"] = Path(project_root)
        return budget

    monkeypatch.setattr(lpl, "load_dynamic_learning_policy_budget", _dynamic)
    monkeypatch.setattr(lpl, "load_governed_learning_adoption_budget", _governed)
    monkeypatch.setattr(lpl, "merge_runtime_route_cost_policy", _route_cost)
    ws2 = deploy.next()
    lpl.merge_runtime_learning_policy(
        ws2, task_desc="d", target_model="m", runtime_identity="r", source_revision="s"
    )
    assert seen["dynamic"] == deploy.state / lpl.DEFAULT_DYNAMIC_LEARNING_POLICY_PATH
    assert seen["dynamic"].is_file()
    # Governance and externally placed policy files stay on the passed root.
    assert seen["governed"] == ws2 and seen["route_cost"] == ws2


def test_promoted_policy_writer_and_loader_agree(deploy: SimpleNamespace) -> None:
    from nexus.contracts.learning_experience import (
        build_learning_experience,
        save_promoted_learning_policy,
    )
    from nexus.engine import learning_policy_loader as lpl

    experience = build_learning_experience(
        task_id="p1",
        capability_receipts=[{"name": "codeintel", "invoked": True, "gate_passed": True}],
    )
    # Same expression as research_flow_service's promotion writer.
    target = rebase_state_path(deploy.ws / lpl.DEFAULT_PROMOTED_POLICY_PATH)
    save_promoted_learning_policy(target, [experience])
    assert target == deploy.state / lpl.DEFAULT_PROMOTED_POLICY_PATH and target.is_file()
    ws2 = deploy.next()
    read_paths: list[Path] = []
    real = lpl.load_learning_policy_budget

    def _spy(path: Path, store: Any = None) -> dict[str, Any]:
        read_paths.append(Path(path))
        return real(path, store=store)

    lpl.load_learning_policy_budget, saved = _spy, lpl.load_learning_policy_budget
    try:
        lpl.merge_runtime_learning_policy(ws2)
    finally:
        lpl.load_learning_policy_budget = saved
    assert read_paths == [target]
    assert not (ws2 / ".nexus").exists()


def test_merge_runtime_learning_policy_unset_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.engine import learning_policy_loader as lpl

    seen: list[Path] = []
    monkeypatch.setattr(
        lpl, "load_learning_policy_budget", lambda path, store=None: seen.append(Path(path)) or {}
    )
    lpl.merge_runtime_learning_policy(tmp_path / "ws")
    assert seen == [tmp_path / "ws" / lpl.DEFAULT_PROMOTED_POLICY_PATH]
