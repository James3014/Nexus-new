"""#2721 L-B: the remaining learning-episode / projection writers honour NEXUS_STATE_READ_ONLY=1.

#2800 guarded the skills_router learning block.  This file covers the other in-repo
writers that had no read-only check:

* ``nexus.services.continuous_learning.persist_learning_episode`` (canonical episode
  ledger; used by ``finalize_learning_loop`` and the nightshift runner),
* ``nexus.core.capability_executor_registry._exec_meta_opt`` (outcome history + tuned
  dynamic policy),
* ``nexus.app.research_flow_service._persist_auto_flow_learning_projection`` (promoted
  policy, model-training export, outcome memory),
* the router decision log ``router_decisions.jsonl``, which lands in the project root
  when no ``run_dir`` is given.

With the switch set the whole state-root tree and the whole project-root tree hash the
same before and after, nothing raises and no write is reported as a success.  With the
switch unset the writes still happen.  The tests use a deploy-style project root
(``NEXUS_CANONICAL_SOURCE_ROOT``) whose state moves to ``NEXUS_STATE_ROOT``.  The real
writers run, except the auto-flow promoted-policy and training-export writers, which are
replaced by file-writing spies (their own behaviour is tested elsewhere).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.state_root import CANONICAL_SOURCE_ROOT_ENV, STATE_ROOT_ENV

RO = "NEXUS_STATE_READ_ONLY"
EPISODE_LOG = Path(".nexus") / "memory" / "learning_episodes.jsonl"
OUTCOME_HISTORY = Path(".nexus") / "memory" / "outcome_history.jsonl"
DYNAMIC_POLICY = Path(".nexus") / "memory" / "dynamic_learning_policy.json"


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            digest.update(f"D:{rel}\n".encode())
        else:
            digest.update(f"F:{rel}:".encode())
            digest.update(path.read_bytes())
            digest.update(b"\n")
    return digest.hexdigest()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        RO,
        STATE_ROOT_ENV,
        CANONICAL_SOURCE_ROOT_ENV,
        "NEXUS_TARGET_ROOT_OVERRIDE",
        "NEXUS_LEARNING_LOOP_WRITE_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A deploy-style project root whose learning state moves to a separate state root.

    Both trees are seeded with existing learning state, so "unchanged" also covers
    appends and rewrites, not only file creation.
    """
    project = tmp_path / "project"
    state = tmp_path / "state"
    project.mkdir()
    state.mkdir()
    monkeypatch.setenv(STATE_ROOT_ENV, str(state))
    monkeypatch.setenv(CANONICAL_SOURCE_ROOT_ENV, str(project))
    monkeypatch.chdir(project)
    for root in (project, state):
        for rel in (EPISODE_LOG, OUTCOME_HISTORY):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"seed": rel.as_posix()}) + "\n", encoding="utf-8")
    return SimpleNamespace(project=project.resolve(), state=state.resolve())


def _snapshot(roots: SimpleNamespace) -> tuple[str, str]:
    return _tree_hash(roots.state), _tree_hash(roots.project)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


# ---- continuous_learning.persist_learning_episode -------------------------------------


def _persist(project: Path) -> dict[str, Any]:
    from nexus.services.continuous_learning import persist_learning_episode

    return persist_learning_episode(
        project,
        task_id="t-2721-cl",
        attempt_id="a1",
        action_id="act1",
        source="continuous_learning",
        terminal_outcome="SUCCEEDED",
        terminal_evidence={"status": "SUCCESS", "receipt": True, "verifier_status": "pass"},
    )


def test_persist_learning_episode_read_only_leaves_state_and_project_unchanged(
    roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(RO, "1")
    before = _snapshot(roots)
    with caplog.at_level("INFO", logger="nexus.services.continuous_learning"):
        result = _persist(roots.project)
    assert _snapshot(roots) == before
    assert result["status"] == "SKIPPED_READ_ONLY"
    assert result["status"] != "PASS"
    assert result["learning_write_succeeded"] is False
    assert any(
        "NEXUS_STATE_READ_ONLY=1" in rec.getMessage()
        and "not a learning success" in rec.getMessage()
        for rec in caplog.records
    )


def test_persist_learning_episode_read_only_never_calls_append(
    roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RO, "1")
    with patch("nexus.learning.learning_closure_effectiveness.append_learning_episode") as append:
        _persist(roots.project)
    append.assert_not_called()


def test_persist_learning_episode_writes_when_read_only_unset(roots: SimpleNamespace) -> None:
    result = _persist(roots.project)
    assert result["status"] == "PASS"
    assert _line_count(roots.state / EPISODE_LOG) == 2
    assert (
        json.loads((roots.state / EPISODE_LOG).read_text().splitlines()[-1])["task_id"]
        == "t-2721-cl"
    )
    assert _line_count(roots.project / EPISODE_LOG) == 1  # the state moved; project untouched


def test_persist_learning_episode_read_only_zero_still_writes(
    roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RO, "0")
    assert _persist(roots.project)["status"] == "PASS"
    assert _line_count(roots.state / EPISODE_LOG) == 2


# ---- capability_executor_registry._exec_meta_opt --------------------------------------


def _meta_opt(project: Path) -> Any:
    from nexus.core.capability_executor_registry import _exec_meta_opt

    episode = {
        "task_id": "t-2721-mo",
        "task_type": "codeintel",
        "task_desc": "d",
        "solved": True,
        "receipts": [{"name": "codeintel", "invoked": True, "gate_passed": True}],
    }
    plan = CapabilityExecutionPlan(
        plan_id="p",
        task_id="t-2721-mo",
        phases=["R"],
        constraints={"workspace_root": str(project), "meta_opt_episode": episode},
    )
    return _exec_meta_opt(plan, "d")


def test_meta_opt_read_only_leaves_state_and_project_unchanged(
    roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(RO, "1")
    before = _snapshot(roots)
    with caplog.at_level("INFO", logger="nexus.core.capability_executor_registry"):
        receipt = _meta_opt(roots.project)
    assert _snapshot(roots) == before
    assert not (roots.state / DYNAMIC_POLICY).exists()
    assert receipt.gate_passed is False
    assert receipt.outcome["semantic_status"] == "SKIPPED"
    assert receipt.outcome["semantic_status"] not in {"VERIFIED", "SUCCEEDED"}
    assert receipt.outcome.get("episode_persisted") is False
    assert receipt.outcome.get("policy_persisted") is False
    assert any("NEXUS_STATE_READ_ONLY=1" in rec.getMessage() for rec in caplog.records)


def test_meta_opt_read_only_never_calls_outcome_memory(
    roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(RO, "1")
    with patch(
        "nexus.learning.outcome_memory.OutcomeMemoryManager.save_episode_and_tune_sync"
    ) as save:
        _meta_opt(roots.project)
    save.assert_not_called()


def test_meta_opt_writes_when_read_only_unset(roots: SimpleNamespace) -> None:
    receipt = _meta_opt(roots.project)
    assert receipt.gate_passed is True
    assert receipt.outcome.get("episode_persisted") is True
    assert _line_count(roots.state / OUTCOME_HISTORY) == 2
    assert (roots.state / DYNAMIC_POLICY).is_file()


# ---- research_flow_service._persist_auto_flow_learning_projection ---------------------


def _fake_policy_writer(path: Path, experiences: list[Any]) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"n": len(experiences)}), encoding="utf-8")
    return {"status": "PROMOTED", "path": str(path)}


def _fake_export_writer(*, repo_root: Path, receipt_slug: str, **_kwargs: Any) -> dict[str, Any]:
    path = Path(repo_root) / ".nexus" / "exports" / "model_training" / f"{receipt_slug}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return {"schema_version": "fake", "path": str(path)}


def _project_auto_flow(project: Path) -> dict[str, Any]:
    from nexus.app import research_flow_service as rfs
    from nexus.learning.outcome_memory import EpisodeOutcomeRecord

    projection: dict[str, Any] = {}
    rfs._persist_auto_flow_learning_projection(
        repo_root=project,
        learning_projection=projection,
        learning_decision=SimpleNamespace(nexus_action="PROMOTE_NEXUS"),
        learning_experience=SimpleNamespace(outcome="verified_success"),
        receipt_slug="slug-2721",
        s2t_trace={"event": {"id": "e"}},
        autodata_quality_row={"task_id": "t-2721-rf"},
        outcome_record_factory=lambda: EpisodeOutcomeRecord.from_task(
            task_id="t-2721-rf",
            task_type="bug",
            task_desc="d",
            solved=True,
            wall_duration_sec=1.0,
            total_tokens_used=10,
            trust_mismatch=False,
            receipts=[{"name": "codeintel", "invoked": True, "gate_passed": True}],
        ),
    )
    return projection


@pytest.fixture
def fake_projection_writers(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Record calls to the promoted-policy and training-export writers; they still write files."""
    from nexus.app import research_flow_service as rfs

    calls = SimpleNamespace(policy=0, export=0)

    def policy(path: Path, experiences: list[Any]) -> dict[str, Any]:
        calls.policy += 1
        return _fake_policy_writer(path, experiences)

    def export(**kwargs: Any) -> dict[str, Any]:
        calls.export += 1
        return _fake_export_writer(**kwargs)

    monkeypatch.setattr(rfs, "save_promoted_learning_policy", policy)
    monkeypatch.setattr(rfs, "write_auto_flow_model_training_export", export)
    return calls


def test_auto_flow_projection_read_only_leaves_state_and_project_unchanged(
    roots: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    fake_projection_writers: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(RO, "1")
    before = _snapshot(roots)
    with caplog.at_level("INFO", logger="nexus.app.research_flow_service"):
        projection = _project_auto_flow(roots.project)
    assert _snapshot(roots) == before
    assert fake_projection_writers.policy == 0
    assert fake_projection_writers.export == 0
    assert projection["promoted_policy"]["status"] == "SKIPPED_READ_ONLY"
    assert projection["outcome_memory"]["status"] == "SKIPPED_READ_ONLY"
    assert "model_training_export" not in projection
    assert any("NEXUS_STATE_READ_ONLY=1" in rec.getMessage() for rec in caplog.records)


def test_auto_flow_projection_read_only_never_calls_outcome_memory(
    roots: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    fake_projection_writers: SimpleNamespace,
) -> None:
    monkeypatch.setenv(RO, "1")
    with patch(
        "nexus.app.research_flow_service.OutcomeMemoryManager.save_episode_and_tune_sync"
    ) as save:
        _project_auto_flow(roots.project)
    save.assert_not_called()


def test_auto_flow_projection_writes_when_read_only_unset(
    roots: SimpleNamespace, fake_projection_writers: SimpleNamespace
) -> None:
    projection = _project_auto_flow(roots.project)
    assert fake_projection_writers.policy == 1
    assert fake_projection_writers.export == 1
    assert projection["promoted_policy"]["status"] == "PROMOTED"
    assert projection["model_training_export"]["schema_version"] == "fake"
    assert projection["outcome_memory"]["status"] == "PASS"
    assert _line_count(roots.state / OUTCOME_HISTORY) == 2


# ---- router decision log (router_decisions.jsonl) -------------------------------------


class _Plan:
    plan_id = "p-2721-dl"
    task_id = "t-2721-dl"
    constraints = {"selection_authority": "CapabilityPlanner"}


@dataclass(frozen=True)
class _CapReceipt:
    capability_name: str = "mock_cap"
    selected: bool = True
    invoked: bool = True
    evidence_id: str = "ev_2721_dl"
    gate_passed: bool = True
    outcome: dict = field(default_factory=lambda: {"status": "pass"})
    evidence_alignment: bool = True
    telemetries: dict = field(
        default_factory=lambda: {
            "wall_time_ms": 100,
            "token_usage": 50,
            "model_calls": 1,
            "telemetry_source": "measured",
        }
    )
    timestamp: str = "2026-10-20T00:00:00"
    skill_receipts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _route(project_root: Path, run_dir: Path | None = None) -> list:
    from nexus.core.router import SkillsRouter

    router = SkillsRouter(
        project_root=str(project_root), run_dir=str(run_dir) if run_dir is not None else None
    )
    with patch("nexus.core.capability_selector.CapabilitySelector") as selector:
        selector.return_value.select_capabilities.return_value = _Plan()
        with patch("nexus.core.executor_controls.ExecutorControls") as controls:
            controls.return_value.execute_plan.return_value = [_CapReceipt()]
            return router.route_candidates("R", {"task_id": "t-2721-dl", "task_desc": "ro"})


def test_router_decision_log_read_only_without_run_dir_leaves_project_root_unchanged(
    roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(RO, "1")
    before = _snapshot(roots)
    with caplog.at_level("INFO", logger="nexus.core.router"):
        candidates = _route(roots.project)
    assert candidates is not None
    assert _snapshot(roots) == before
    assert not (roots.project / "router_decisions.jsonl").exists()
    assert not (roots.state / "router_decisions.jsonl").exists()
    assert any("router_decisions.jsonl" in rec.getMessage() for rec in caplog.records)


def test_router_decision_log_read_only_explicit_run_dir_still_written(
    roots: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit run_dir belongs to the run, not to the project or state root."""
    monkeypatch.setenv(RO, "1")
    run_dir = tmp_path / "run"
    before = _snapshot(roots)
    _route(roots.project, run_dir=run_dir)
    assert _snapshot(roots) == before
    assert _line_count(run_dir / "router_decisions.jsonl") == 1


def test_router_decision_log_unset_writes_project_root(roots: SimpleNamespace) -> None:
    _route(roots.project)
    rows = (roots.project / "router_decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["task_id"] == "t-2721-dl"


def test_router_decision_log_unset_still_feeds_skills_autotune(tmp_path: Path) -> None:
    """skills_autotune reads <root>/scripts/core/router_decisions.jsonl and .nexus/runs/**;
    with the switch unset the router still writes both locations it reads."""
    from scripts.ops.skills_autotune import _discover_decision_logs, _load_jsonl, run_autotune

    project = tmp_path / "autotune-project"
    legacy_root = project / "scripts" / "core"
    legacy_root.mkdir(parents=True)
    run_dir = project / ".nexus" / "runs" / "r1"
    _route(legacy_root)  # no run_dir: legacy default location
    _route(project, run_dir=run_dir)
    logs = _discover_decision_logs(project)
    assert legacy_root / "router_decisions.jsonl" in logs
    assert run_dir / "router_decisions.jsonl" in logs
    for log in (legacy_root / "router_decisions.jsonl", run_dir / "router_decisions.jsonl"):
        rows = _load_jsonl(log)  # autotune's own reader parses what the router wrote
        assert len(rows) == 1
        assert rows[0]["decision_id"] and rows[0]["phase"] == "R"
        assert rows[0]["task_id"] == "t-2721-dl"
    rc = run_autotune(
        project_root=project,
        apply=False,
        min_samples=3,
        baseline=0.55,
        learning_rate=0.6,
        degrade_threshold=0.2,
        max_step=0.2,
        degrade_consecutive_rounds=3,
    )
    assert rc == 0
