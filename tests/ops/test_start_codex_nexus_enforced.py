"""Retired 2026-10-21 (#2584 Phase-2 batch B, ARCHIVED_2026-10-21_phase2_batch_B.md).

The Codex launcher ``scripts/ops/start_codex_nexus_enforced.sh`` (with its
``start_antigravity_nexus_enforced.sh`` proxy and ``codex_run_guard.py`` helper) was deleted: no host, schedule or code launched it.
Every case keeps its test id and asserts the deleted files are gone, so a re-add is
deliberate. The live Codex run boundary (``nexus.executors.codex_run_boundary``, used by
``CodexCliExecutor``) is covered by ``tests/ops/test_codex_run_boundary.py`` and
``tests/nexus/executors/test_codex_run_boundary_executor.py``.
"""

import importlib.util
from pathlib import Path

_OPS = Path(__file__).resolve().parents[2] / "scripts" / "ops"
_LAUNCHER = _OPS / "start_codex_nexus_enforced.sh"
_ANTIGRAVITY_PROXY = _OPS / "start_antigravity_nexus_enforced.sh"
_GUARD = _OPS / "codex_run_guard.py"


def _launcher_retired() -> None:
    assert not _LAUNCHER.exists()
    assert not _ANTIGRAVITY_PROXY.exists()
    assert not _GUARD.exists()
    assert importlib.util.find_spec("scripts.ops.codex_run_guard") is None


def test_codex_enforced_startup_contract_block():
    _launcher_retired()


def test_antigravity_compat_proxy():
    _launcher_retired()


def test_codex_launcher_refuses_sandbox_bypass_modes(tmp_path):
    _launcher_retired()


def test_codex_launcher_runs_sandboxed_in_a_disposable_work_copy(tmp_path):
    _launcher_retired()


def test_codex_launcher_read_only_mode_uses_read_only_sandbox(tmp_path):
    _launcher_retired()


def test_codex_launcher_fails_when_canonical_checkout_changes(tmp_path):
    _launcher_retired()


def test_codex_launcher_denied_actions_are_non_delivery(tmp_path):
    _launcher_retired()


def test_codex_launcher_refuses_work_root_inside_canonical(tmp_path):
    _launcher_retired()


def test_codex_launcher_excludes_tmp_from_the_sandbox_and_state(tmp_path):
    _launcher_retired()


def test_codex_launcher_ignores_denial_markers_in_free_text(tmp_path):
    _launcher_retired()


def test_codex_launcher_propagates_a_nonzero_codex_exit(tmp_path):
    _launcher_retired()


def test_codex_launcher_fails_when_a_canonical_ref_moves(tmp_path):
    _launcher_retired()


def test_codex_launcher_refuses_when_the_canonical_snapshot_fails(tmp_path):
    _launcher_retired()


def test_codex_launcher_refuses_flag_shaped_models(tmp_path):
    _launcher_retired()


def test_codex_launcher_refuses_symlinked_work_root_into_canonical(tmp_path):
    _launcher_retired()


def test_codex_launcher_ignores_other_refs_in_the_shared_common_dir(tmp_path):
    _launcher_retired()


def test_codex_launcher_denial_classifier_failure_is_non_delivery(tmp_path):
    _launcher_retired()


def test_codex_launcher_survives_concurrent_branch_and_worktree_bookkeeping(tmp_path):
    _launcher_retired()


def test_codex_launcher_still_fails_on_code_bearing_config_changes(tmp_path):
    _launcher_retired()


def test_codex_launcher_refuses_when_the_config_fingerprint_fails(tmp_path):
    _launcher_retired()


def test_codex_launcher_fails_when_the_config_fingerprint_fails_after_the_run(tmp_path):
    _launcher_retired()


def test_guard_git_config_fingerprint_is_the_shared_definition(tmp_path):
    _launcher_retired()
