"""Retired 2026-10-21 (#2584 Phase-2 batch B, ARCHIVED_2026-10-21_phase2_batch_B.md).

The Codex run guard ``scripts/ops/codex_run_guard.py`` (only called by the
retired ``start_codex_nexus_enforced.sh`` launcher) was deleted: no host, schedule or code launched it.
Every case keeps its test id and asserts the deleted files are gone, so a re-add is
deliberate. The live Codex run boundary (``nexus.executors.codex_run_boundary``, used by
``CodexCliExecutor``) is covered by ``tests/ops/test_codex_run_boundary.py`` and
``tests/nexus/executors/test_codex_run_boundary_executor.py``.
"""

import importlib.util
from pathlib import Path

_OPS = Path(__file__).resolve().parents[2] / "scripts" / "ops"
_GUARD = _OPS / "codex_run_guard.py"


def _guard_retired() -> None:
    assert not _GUARD.exists()
    assert importlib.util.find_spec("scripts.ops.codex_run_guard") is None


def test_codex_guard_kills_a_tagged_setsid_child_before_returning(tmp_path):
    _guard_retired()


def test_codex_guard_kills_an_untagged_setsid_child_in_the_work_copy(tmp_path):
    _guard_retired()


def test_codex_guard_kills_the_group_before_reaping_the_leader(tmp_path, monkeypatch):
    _guard_retired()


def test_codex_guard_installs_signal_handlers_before_launch(tmp_path, monkeypatch):
    _guard_retired()


def test_codex_guard_forwards_a_signal_that_arrives_during_launch(tmp_path, monkeypatch):
    _guard_retired()


def test_codex_guard_still_sweeps_when_tracking_fails(tmp_path, monkeypatch):
    _guard_retired()
