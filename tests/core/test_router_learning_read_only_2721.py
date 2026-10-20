"""#2721 L-B: the skills_router learning block honours NEXUS_STATE_READ_ONLY=1.

``SkillsRouter.route_candidates`` writes three learning artefacts after routing:

1. the canonical learning episode (``append_learning_episode``),
2. the ``.nexus/reports/learn/learning_closure.jsonl`` projection log,
3. ``OutcomeMemoryManager.save_episode_and_tune_sync`` (outcome history + tuned policy).

With the switch set none of them may touch the state root (hash the tree before and
after), the switch is re-read at call time, and with it unset all three still write.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest

from nexus.core.router import SkillsRouter

RO = "NEXUS_STATE_READ_ONLY"
SELECTOR_PATH = "nexus.core.capability_selector.CapabilitySelector"
EXECUTOR_PATH = "nexus.core.executor_controls.ExecutorControls"
APPEND_PATH = "nexus.core.router.append_learning_episode"
OUTCOME_PATH = "nexus.learning.outcome_memory.OutcomeMemoryManager.save_episode_and_tune_sync"

EPISODE_LOG = Path(".nexus") / "memory" / "learning_episodes.jsonl"
PROJECTION_LOG = Path(".nexus") / "reports" / "learn" / "learning_closure.jsonl"
OUTCOME_HISTORY = Path(".nexus") / "memory" / "outcome_history.jsonl"


class _Plan:
    plan_id = "p-2721"
    task_id = "t-2721"
    constraints = {"selection_authority": "CapabilityPlanner"}


@dataclass(frozen=True)
class _CapReceipt:
    capability_name: str = "mock_cap"
    selected: bool = True
    invoked: bool = True
    evidence_id: str = "ev_2721"
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


def tree_hash(root: Path) -> str:
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
def _clean_env(monkeypatch):
    monkeypatch.delenv(RO, raising=False)
    monkeypatch.delenv("NEXUS_STATE_ROOT", raising=False)
    monkeypatch.delenv("NEXUS_LEARNING_LOOP_WRITE_ENABLED", raising=False)


def _state_root(tmp_path: Path) -> Path:
    root = tmp_path / "state"
    root.mkdir()
    return root


def _router(root: Path) -> SkillsRouter:
    # The per-run decision trace (router_decisions.jsonl) goes to run_dir, which a run
    # owns; keep it outside the state root so the hash covers learning state only.
    return SkillsRouter(project_root=str(root), run_dir=str(root.parent / "run"))


def _route(root: Path, *, set_read_only_after_init: object = None, monkeypatch=None) -> list:
    router = _router(root)
    if set_read_only_after_init is not None and monkeypatch is not None:
        monkeypatch.setenv(RO, "1")
    with patch(SELECTOR_PATH) as selector:
        selector.return_value.select_capabilities.return_value = _Plan()
        with patch(EXECUTOR_PATH) as controls:
            controls.return_value.execute_plan.return_value = [_CapReceipt()]
            return router.route_candidates("R", {"task_id": "t-2721", "task_desc": "ro"})


def _seed_existing_state(root: Path) -> None:
    """Pre-existing learning state, so 'unchanged' also covers appends, not just creation."""
    for rel in (EPISODE_LOG, PROJECTION_LOG, OUTCOME_HISTORY):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"seed": rel.as_posix()}) + "\n", encoding="utf-8")


# ---- read-only: no file under the state root changes ---------------------------------


def test_router_learning_read_only_leaves_state_tree_unchanged(tmp_path, monkeypatch):
    root = _state_root(tmp_path)
    _seed_existing_state(root)
    monkeypatch.setenv(RO, "1")
    _router(root)
    before = tree_hash(root)
    candidates = _route(root)
    assert candidates is not None
    assert tree_hash(root) == before


def test_router_learning_read_only_fresh_root_creates_no_learning_files(tmp_path, monkeypatch):
    root = _state_root(tmp_path)
    monkeypatch.setenv(RO, "1")
    _router(root)
    before = tree_hash(root)
    _route(root)
    assert tree_hash(root) == before
    for rel in (EPISODE_LOG, PROJECTION_LOG, OUTCOME_HISTORY):
        assert not (root / rel).exists(), rel


def test_router_read_only_skips_canonical_learning_episode_append(tmp_path, monkeypatch):
    root = _state_root(tmp_path)
    _seed_existing_state(root)
    monkeypatch.setenv(RO, "1")
    before = (root / EPISODE_LOG).read_bytes()
    with patch(APPEND_PATH) as append:
        _route(root)
    append.assert_not_called()
    assert (root / EPISODE_LOG).read_bytes() == before


def test_router_read_only_skips_learning_closure_projection(tmp_path, monkeypatch):
    root = _state_root(tmp_path)
    _seed_existing_state(root)
    monkeypatch.setenv(RO, "1")
    before = tree_hash(root / ".nexus" / "reports")
    _route(root)
    assert tree_hash(root / ".nexus" / "reports") == before
    assert (root / PROJECTION_LOG).read_text(encoding="utf-8").count("\n") == 1


def test_router_read_only_skips_outcome_memory_tuning(tmp_path, monkeypatch):
    root = _state_root(tmp_path)
    _seed_existing_state(root)
    monkeypatch.setenv(RO, "1")
    monkeypatch.setenv("NEXUS_LEARNING_LOOP_WRITE_ENABLED", "1")  # the old, only gate
    before = tree_hash(root / ".nexus" / "memory")
    with patch(OUTCOME_PATH) as save:
        _route(root)
    save.assert_not_called()
    _route(root)  # real OutcomeMemoryManager path too
    assert tree_hash(root / ".nexus" / "memory") == before


def test_router_read_only_is_reread_at_call_time(tmp_path, monkeypatch):
    """The switch set after the router was built still blocks every learning write."""
    root = _state_root(tmp_path)
    _seed_existing_state(root)
    before = tree_hash(root)
    with patch(APPEND_PATH) as append, patch(OUTCOME_PATH) as save:
        _route(root, set_read_only_after_init=True, monkeypatch=monkeypatch)
    append.assert_not_called()
    save.assert_not_called()
    assert tree_hash(root) == before


def test_router_read_only_does_not_raise_or_report_learning_success(tmp_path, monkeypatch, caplog):
    root = _state_root(tmp_path)
    monkeypatch.setenv(RO, "1")
    with caplog.at_level("INFO", logger="nexus.core.router"):
        candidates = _route(root)
    assert candidates is not None
    messages = [rec.getMessage() for rec in caplog.records if rec.name == "nexus.core.router"]
    assert any("NEXUS_STATE_READ_ONLY=1" in m and "not a learning success" in m for m in messages)
    assert not any("write failed" in m for m in messages)


# ---- unset: behaviour unchanged, all three writes happen -----------------------------


def test_router_learning_writes_all_three_when_read_only_unset(tmp_path):
    root = _state_root(tmp_path)
    _route(root)
    episodes = (root / EPISODE_LOG).read_text(encoding="utf-8").splitlines()
    assert len(episodes) == 1
    assert json.loads(episodes[0])["producer"] == "skills_router"
    projection = (root / PROJECTION_LOG).read_text(encoding="utf-8").splitlines()
    assert len(projection) == 1
    assert json.loads(projection[0])["capability_name"] == "mock_cap"
    history = (root / OUTCOME_HISTORY).read_text(encoding="utf-8").splitlines()
    assert len(history) == 1


def test_router_learning_read_only_zero_is_not_read_only(tmp_path, monkeypatch):
    root = _state_root(tmp_path)
    monkeypatch.setenv(RO, "0")
    with patch(APPEND_PATH, return_value=True) as append, patch(OUTCOME_PATH) as save:
        _route(root)
    append.assert_called_once()
    save.assert_called_once()
    assert (root / PROJECTION_LOG).exists()
