"""#2721 measurement snapshot of the worker's raw Target diff.

Runs through the real ``_run_default_resumable`` path (runtime coordination
bridge, nexus-runtime ``ExecutionCoordinator``) with a real git Target lease and
a fake ``WorkerRegistry.invoke`` that edits the Target.  Finalization is a
recorder, so each test sees the task state exactly as verification would.
"""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.orchestrator import measurement_worktree_diff as mwd
from nexus.orchestrator import runtime_coordination_bridge as bridge
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from tests.nexus.orchestrator.test_self_hosted_task_service import _m3c_receipt, _setup_lc2_task

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(cwd, *args, env=None):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, capture_output=True, check=True
    ).stdout


def _bare_arm_diff(worktree, base) -> bytes:
    """The bare arm's ``capture_diff`` (scripts/bench/measure_2721/common.py)."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(worktree, "read-tree", base, env=env)
        _git(worktree, "add", "-A", "--", ".", env=env)
        return _git(
            worktree, "diff", "--cached", "--binary", "--no-color", "--no-ext-diff", base, env=env
        )


def _index_bytes(worktree) -> bytes:
    path = _git(worktree, "rev-parse", "--git-path", "index").decode().strip()
    index = Path(path) if Path(path).is_absolute() else Path(worktree) / path
    return index.read_bytes()


def _is_snapshot_git(args) -> bool:
    safe = list(mwd._GIT_SAFE_CONFIG)
    return str(args[1]).startswith("--attr-source=") and list(args[2 : 2 + len(safe)]) == safe


def _shared_rule_diff(worktree, base) -> bytes:
    """Reference for the shared rule: base attributes, no global/system config."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(
            GIT_INDEX_FILE=str(Path(tmp) / "index"),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL="/dev/null",
        )
        attr = f"--attr-source={base}"
        _git(worktree, attr, "read-tree", base, env=env)
        _git(worktree, attr, "add", "-A", "--", ".", env=env)
        return _git(
            worktree, attr, "diff", "--cached", "--binary", "--no-color", "--no-ext-diff",
            "--no-textconv", base, env=env,
        )  # fmt: skip


def _controller(h) -> str:
    return str(h.contract.controller_repo_root)


def _capture(h, **kwargs):
    return mwd.capture_worktree_diff(
        h.lease.target_worktree, h.lease.initial_head, controller_root=_controller(h), **kwargs
    )


def _edit_target(worktree):
    Path(worktree, "README").write_text("base\nworker edit\n")
    Path(worktree, "new_file.py").write_text("print('untracked')\n")


@pytest.fixture
def harness(tmp_path, monkeypatch):
    return _make_harness(tmp_path, monkeypatch)


def _make_harness(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str((tmp_path / "targets").resolve()))
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False
    )
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, "mwd-task")
    state = service._read_state(contract.task_id)
    assert state is not None
    state.update(
        status="WORKER_RUNNING",
        active_provider="codex",
        attempts=[{"attempt_id": attempt_id}],
        executions=[],
        target_initial_revision=lease.initial_head,
    )
    service._write_state(contract.task_id, state)
    monkeypatch.setattr(
        "nexus.orchestrator.self_hosted_task_service.CandidateVerifier",
        SimpleNamespace(validate_static_contract=lambda *_: None),
    )
    seen: dict = {}

    def finalize(contract, request, lease, state, attempts, update, **kwargs):
        seen["state"] = service._read_state(contract.task_id)
        return {"finalized": True}

    monkeypatch.setattr(service, "_finalize_runtime_candidate", finalize)

    def run():
        return service._run_default_resumable(
            contract,
            state["request"],
            lambda *_: None,
            task_id=contract.task_id,
            attempt_id=attempt_id,
        )

    return SimpleNamespace(
        service=service, contract=contract, lease=lease, attempt_id=attempt_id, seen=seen, run=run
    )


def _invoke_editing(receipt_factory=None):
    def invoke(provider, contract, lease, **kwargs):
        _edit_target(lease.target_worktree)
        if receipt_factory is not None:
            return receipt_factory(contract, lease)
        return _m3c_receipt(contract.task_id, lease.target_worktree)

    return invoke


def _measurement_keys(state):
    return sorted(key for key in state if key.startswith("measurement_worktree_diff"))


def test_disabled_records_nothing_and_runs_no_git(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", False)
    monkeypatch.setattr(
        mwd.subprocess, "run", lambda *a, **k: pytest.fail("no git when the switch is off")
    )
    monkeypatch.setattr(
        mwd, "record_after_worker", lambda **_: pytest.fail("no snapshot when the switch is off")
    )
    monkeypatch.setattr(harness.service.worker_registry, "invoke", _invoke_editing())
    assert harness.run() == {"finalized": True}
    assert _measurement_keys(harness.seen["state"]) == []
    assert _measurement_keys(harness.service._read_state(harness.contract.task_id)) == []


def test_switch_is_snapshotted_at_import():
    code = (
        "import os\n"
        "from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService\n"
        "from nexus.orchestrator import measurement_worktree_diff as m\n"
        "os.environ['NEXUS_MEASUREMENT_WORKTREE_DIFF'] = '1'\n"
        "env = m.align_child_env(dict(os.environ))\n"
        "print(m.enabled(), 'NEXUS_MEASUREMENT_WORKTREE_DIFF' in env)\n"
    )
    base_env = {k: v for k, v in os.environ.items() if k != "NEXUS_MEASUREMENT_WORKTREE_DIFF"}
    base_env["PYTHONPATH"] = str(REPO_ROOT)

    def run(env):
        return subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    assert run(base_env) == "False False"
    assert run({**base_env, "NEXUS_MEASUREMENT_WORKTREE_DIFF": "1"}) == "True True"
    assert run({**base_env, "NEXUS_MEASUREMENT_WORKTREE_DIFF": "yes"}) == "False False"


def test_child_env_unchanged_when_off(monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", False)
    env = {"PATH": "/bin", "PYTHONPATH": "x"}
    assert mwd.align_child_env(dict(env)) == env
    assert mwd.align_child_env({**env, mwd.MEASUREMENT_WORKTREE_DIFF_ENV: "1"}) == env
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    assert mwd.align_child_env(dict(env)) == {**env, mwd.MEASUREMENT_WORKTREE_DIFF_ENV: "1"}


def test_enabled_records_tracked_and_untracked_before_finalize(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    worktree = harness.lease.target_worktree
    index_before = _index_bytes(worktree)
    monkeypatch.setattr(harness.service.worker_registry, "invoke", _invoke_editing())
    assert harness.run() == {"finalized": True}

    state = harness.seen["state"]  # as finalization (verification) sees it
    expected = _bare_arm_diff(worktree, harness.lease.initial_head)
    diff = state["measurement_worktree_diff"]
    assert diff == expected.decode()
    assert "diff --git a/README b/README" in diff and "+worker edit" in diff
    assert "diff --git a/new_file.py b/new_file.py" in diff and "new file mode" in diff
    assert state["measurement_worktree_diff_sha256"] == hashlib.sha256(expected).hexdigest()
    assert state["measurement_worktree_diff_bytes"] == len(expected)
    assert state["measurement_worktree_diff_truncated"] is False
    assert state["measurement_worktree_diff_base"] == harness.lease.initial_head
    assert state["measurement_worktree_diff_attempt_id"] == harness.attempt_id
    assert state["measurement_worktree_diff_invocation"] == 0
    assert state["measurement_worktree_diff_lossy"] is False
    assert 0 <= state["measurement_worktree_diff_elapsed_ms"] < 30_000
    assert "measurement_worktree_diff_error" not in state
    # The worktree's own index and files are untouched.
    assert _index_bytes(worktree) == index_before
    status = _git(worktree, "status", "--porcelain").decode()
    assert " M README" in status and "?? new_file.py" in status


def test_timed_out_worker_still_records_diff(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)

    def timed_out(contract, lease):
        return replace(
            _m3c_receipt(contract.task_id, lease.target_worktree),
            worker_status="timed_out",
            outcome="INCOMPLETE",
            timed_out=True,
            exit_code=-9,
            evidence_complete=False,
        )

    monkeypatch.setattr(harness.service.worker_registry, "invoke", _invoke_editing(timed_out))
    with pytest.raises(RuntimeError):
        harness.run()
    state = harness.service._read_state(harness.contract.task_id)
    assert "+worker edit" in state["measurement_worktree_diff"]
    assert "new_file.py" in state["measurement_worktree_diff"]
    assert "measurement_worktree_diff_error" not in state


def test_raising_worker_still_records_diff_and_reraises(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)

    def invoke(provider, contract, lease, **kwargs):
        _edit_target(lease.target_worktree)
        raise RuntimeError("worker crashed")

    monkeypatch.setattr(harness.service.worker_registry, "invoke", invoke)
    with pytest.raises(RuntimeError, match="worker crashed"):
        harness.run()
    state = harness.service._read_state(harness.contract.task_id)
    assert "+worker edit" in state["measurement_worktree_diff"]
    assert "new_file.py" in state["measurement_worktree_diff"]


def test_reinvoked_worker_overwrites_snapshot(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    monkeypatch.setattr(harness.service.worker_registry, "invoke", _invoke_editing())
    assert harness.run() == {"finalized": True}
    first = harness.seen["state"]
    assert "+worker edit" in first["measurement_worktree_diff"]
    assert "second_run.py" not in first["measurement_worktree_diff"]

    # A resume that really re-invokes the worker (same invocation number):
    # the worker edits more, and the snapshot is the diff after that run.
    def invoke_again(provider, contract, lease, **kwargs):
        Path(lease.target_worktree, "second_run.py").write_text("x = 2\n")
        return _m3c_receipt(contract.task_id, lease.target_worktree)

    monkeypatch.setattr(harness.service.worker_registry, "invoke", invoke_again)
    assert harness.run() == {"finalized": True}
    second = harness.seen["state"]
    assert (
        second["measurement_worktree_diff_invocation"]
        == first["measurement_worktree_diff_invocation"]
    )
    assert "second_run.py" in second["measurement_worktree_diff"]
    assert "+worker edit" in second["measurement_worktree_diff"]
    assert second["measurement_worktree_diff_sha256"] != first["measurement_worktree_diff_sha256"]
    assert (
        second["measurement_worktree_diff"]
        == _shared_rule_diff(harness.lease.target_worktree, harness.lease.initial_head).decode()
    )


def test_earlier_persist_failed_does_not_block_later_capture(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    state = harness.service._read_state(harness.contract.task_id)
    assert state is not None
    state.update(
        measurement_worktree_diff_error="persist_failed",
        measurement_worktree_diff_attempt_id=harness.attempt_id,
        measurement_worktree_diff_invocation=0,
    )
    harness.service._write_state(harness.contract.task_id, state)
    monkeypatch.setattr(harness.service.worker_registry, "invoke", _invoke_editing())
    assert harness.run() == {"finalized": True}
    seen = harness.seen["state"]
    assert "+worker edit" in seen["measurement_worktree_diff"]
    assert "measurement_worktree_diff_error" not in seen


def test_failed_later_invocation_clears_earlier_diff(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    _edit_target(harness.lease.target_worktree)
    _record(harness, invocation=0)
    state = harness.service._read_state(harness.contract.task_id)
    assert state is not None and "+worker edit" in state["measurement_worktree_diff"]
    real_run = subprocess.run

    def failing_git(args, **kwargs):
        if _is_snapshot_git(args):
            return subprocess.CompletedProcess(args, 128)
        return real_run(args, **kwargs)

    monkeypatch.setattr(mwd.subprocess, "run", failing_git)
    _record(harness, invocation=1)
    state = harness.service._read_state(harness.contract.task_id)
    assert state is not None
    assert state["measurement_worktree_diff_error"] == "git_failed:read_tree"
    assert state["measurement_worktree_diff_invocation"] == 1
    for key in ("", "_sha256", "_bytes", "_truncated", "_lossy"):
        assert "measurement_worktree_diff" + key not in state


def test_git_failure_records_error_and_outcome_is_unchanged(harness, monkeypatch, tmp_path):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    real_run = subprocess.run

    def failing_git(args, **kwargs):
        if _is_snapshot_git(args):  # only the snapshot's git
            return subprocess.CompletedProcess(args, 128)
        return real_run(args, **kwargs)

    monkeypatch.setattr(mwd.subprocess, "run", failing_git)
    monkeypatch.setattr(harness.service.worker_registry, "invoke", _invoke_editing())
    assert harness.run() == {"finalized": True}
    state = harness.seen["state"]
    assert state["measurement_worktree_diff_error"] == "git_failed:read_tree"
    assert "measurement_worktree_diff" not in state

    # Same run with the switch off: identical result and state apart from the error key.
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", False)
    (tmp_path / "off").mkdir()
    off = _make_harness(tmp_path / "off", monkeypatch)
    monkeypatch.setattr(off.service.worker_registry, "invoke", _invoke_editing())
    assert off.run() == {"finalized": True}

    on_state = {k: v for k, v in state.items() if not k.startswith("measurement_worktree_diff")}
    off_state = off.seen["state"]
    assert sorted(on_state) == sorted(off_state)
    for key in ("status", "active_provider", "execution_lane"):
        assert on_state.get(key) == off_state.get(key)
    assert [e["outcome"] for e in on_state["executions"]] == [
        e["outcome"] for e in off_state["executions"]
    ]


def test_git_timeout_records_error(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)

    real_run = subprocess.run

    def slow(args, **kwargs):
        if _is_snapshot_git(args):  # only the snapshot's git
            raise subprocess.TimeoutExpired(args, float(kwargs.get("timeout") or 0))
        return real_run(args, **kwargs)

    monkeypatch.setattr(mwd.subprocess, "run", slow)
    monkeypatch.setattr(harness.service.worker_registry, "invoke", _invoke_editing())
    assert harness.run() == {"finalized": True}
    assert harness.seen["state"]["measurement_worktree_diff_error"] == "git_timeout"


def test_cap_truncates_text_but_hashes_full_diff(harness):
    worktree = harness.lease.target_worktree
    Path(worktree, "big.txt").write_text("x" * 5000 + "\n")
    full = _bare_arm_diff(worktree, harness.lease.initial_head)
    values = _capture(harness, max_bytes=1000)
    assert values["measurement_worktree_diff"] == full[:1000].decode()
    assert values["measurement_worktree_diff_bytes"] == len(full) > 1000
    assert values["measurement_worktree_diff_sha256"] == hashlib.sha256(full).hexdigest()
    assert values["measurement_worktree_diff_truncated"] is True
    untruncated = _capture(harness)
    assert untruncated["measurement_worktree_diff"] == full.decode()
    assert untruncated["measurement_worktree_diff_truncated"] is False


def test_git_runs_hardened(harness, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/nonexistent")
    monkeypatch.setenv("GIT_WORK_TREE", "/nonexistent")
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", "/nonexistent")
    calls, timeouts = [], []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def spy_run(args, **kwargs):
        timeouts.append(kwargs.get("timeout"))
        return real_run(args, **kwargs)

    def spy_popen(args, **kwargs):  # subprocess.run goes through Popen too
        calls.append((list(args), kwargs))
        return real_popen(args, **kwargs)

    monkeypatch.setattr(mwd.subprocess, "run", spy_run)
    monkeypatch.setattr(mwd.subprocess, "Popen", spy_popen)
    values = _capture(harness)
    assert values["measurement_worktree_diff"] == ""
    safe = list(mwd._GIT_SAFE_CONFIG)
    assert all(args[1] == f"--attr-source={harness.lease.initial_head}" for args, _ in calls)
    assert [args[2 + len(safe)] for args, _ in calls] == ["read-tree", "add", "diff"]
    assert "--no-textconv" in calls[2][0] and "--no-ext-diff" in calls[2][0]
    worktree = Path(harness.lease.target_worktree).resolve()
    common = Path(harness.contract.controller_repo_root).resolve() / ".git"
    for args, kwargs in calls:
        assert args[2 : 2 + len(safe)] == safe
        env = kwargs["env"]
        assert sorted(k for k in env if k.startswith("GIT_")) == [
            "GIT_ATTR_NOSYSTEM",
            "GIT_CEILING_DIRECTORIES",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_DIR",
            "GIT_INDEX_FILE",
            "GIT_TERMINAL_PROMPT",
            "GIT_WORK_TREE",
        ]
        assert Path(env["GIT_DIR"]).parent == common / "worktrees"
        assert env["GIT_WORK_TREE"] == str(worktree)
        assert env["GIT_CONFIG_GLOBAL"] == "/dev/null" and env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert kwargs["stdin"] is subprocess.DEVNULL
    assert len(timeouts) == 2 and all(0 < t <= 30 for t in timeouts)


def _hostile_target(harness, marker_dir: Path):
    """A worker-written .gitattributes whose filter and textconv touch markers."""
    worktree = Path(harness.lease.target_worktree)
    clean_marker, textconv_marker = marker_dir / "clean-ran", marker_dir / "textconv-ran"
    (worktree / ".gitattributes").write_text("*.txt filter=evil diff=evil\n")
    (worktree / "payload.txt").write_text("payload\n")
    _git(worktree, "config", "filter.evil.clean", f"touch {clean_marker}; cat")
    _git(worktree, "config", "diff.evil.textconv", f"touch {textconv_marker}; cat")
    return clean_marker, textconv_marker


def test_worker_attributes_run_no_filter_or_textconv(harness, tmp_path):
    clean_marker, textconv_marker = _hostile_target(harness, tmp_path)
    values = _capture(harness)
    assert not clean_marker.exists() and not textconv_marker.exists()
    assert "+payload" in values["measurement_worktree_diff"]
    # Control: the same hostile tree does run both commands under the bare rule.
    _bare_arm_diff(harness.lease.target_worktree, harness.lease.initial_head)
    assert clean_marker.exists() and textconv_marker.exists()


def test_repository_info_attributes_is_refused(harness, tmp_path):
    clean_marker, _ = _hostile_target(harness, tmp_path)
    (Path(harness.lease.target_worktree) / ".gitattributes").unlink()
    common = Path(
        _git(harness.lease.target_worktree, "rev-parse", "--git-common-dir").decode().strip()
    )
    common = common if common.is_absolute() else Path(harness.lease.target_worktree) / common
    (common / "info").mkdir(exist_ok=True)
    (common / "info" / "attributes").write_text("*.txt filter=evil\n")
    with pytest.raises(mwd.MeasurementDiffError, match="info_attributes_present"):
        _capture(harness)
    assert not clean_marker.exists()


def test_target_gitdir_pointer_swap_is_refused(harness, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    dotgit = Path(harness.lease.target_worktree) / ".git"
    original = dotgit.read_text()
    dotgit.write_text(f"gitdir: {other / '.git'}\n")
    with pytest.raises(mwd.MeasurementDiffError, match="gitdir_untrusted"):
        _capture(harness)
    dotgit.write_text(original)
    assert _capture(harness)["measurement_worktree_diff"] == ""


def test_fake_gitdir_inside_worktree_runs_no_worker_command(harness, tmp_path):
    """Opus review repro: ``.git`` -> ``<worktree>/fake`` with hostile config."""
    worktree = Path(harness.lease.target_worktree)
    real_common = Path(harness.contract.controller_repo_root).resolve() / ".git"
    clean_marker, textconv_marker = tmp_path / "clean-ran", tmp_path / "textconv-ran"
    fake = worktree / "fake"
    (fake / "objects" / "info").mkdir(parents=True)
    (fake / "refs").mkdir()
    (fake / "HEAD").write_text(harness.lease.initial_head + "\n")
    (fake / "objects" / "info" / "alternates").write_text(str(real_common / "objects") + "\n")
    (fake / "config").write_text(
        "[core]\n\trepositoryformatversion = 0\n\tbare = false\n"
        f'[filter "x"]\n\tclean = touch {clean_marker}; cat\n'
        f'[diff "y"]\n\ttextconv = touch {textconv_marker}; cat\n'
    )
    (worktree / ".gitattributes").write_text("*.txt filter=x diff=y\n")
    (worktree / "payload.txt").write_text("payload\n")
    (worktree / ".git").write_text("gitdir: fake\n")
    # Control: plain git in this worktree does follow the fake gitdir.
    _bare_arm_diff(worktree, harness.lease.initial_head)
    assert clean_marker.exists() and textconv_marker.exists()
    clean_marker.unlink()
    textconv_marker.unlink()

    with pytest.raises(mwd.MeasurementDiffError, match="gitdir_untrusted"):
        _capture(harness)
    assert not clean_marker.exists() and not textconv_marker.exists()


def test_symlinked_target_is_refused(harness, tmp_path):
    link = tmp_path / "link-target"
    link.symlink_to(harness.lease.target_worktree)
    with pytest.raises(mwd.MeasurementDiffError, match="worktree_symlink"):
        mwd.capture_worktree_diff(
            str(link), harness.lease.initial_head, controller_root=_controller(harness)
        )


def test_total_limit_kills_git_and_marks_partial(harness, monkeypatch):
    Path(harness.lease.target_worktree, "big.txt").write_text("y\n" * 200_000)
    killed = []
    real_popen = subprocess.Popen

    def spy_popen(args, **kwargs):
        proc = real_popen(args, **kwargs)
        real_kill = proc.kill
        proc.kill = lambda: (killed.append(proc.pid), real_kill())[1]
        return proc

    monkeypatch.setattr(mwd.subprocess, "Popen", spy_popen)
    with pytest.raises(mwd.MeasurementDiffError, match="too_large") as info:
        _capture(harness, max_total_bytes=4096)
    assert info.value.partial_bytes is not None and info.value.partial_bytes > 4096
    assert len(killed) == 1

    # Through the recorder: an error, partial bytes, and no diff/sha/bytes.
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    monkeypatch.setattr(mwd, "MAX_TOTAL_DIFF_BYTES", 4096)
    _record(harness)
    state = harness.service._read_state(harness.contract.task_id)
    assert state["measurement_worktree_diff_error"] == "too_large"
    assert state["measurement_worktree_diff_partial_bytes"] > 4096
    for key in ("", "_sha256", "_bytes", "_truncated"):
        assert "measurement_worktree_diff" + key not in state


def test_stream_deadline_kills_git(harness, monkeypatch):
    clock = {"calls": 0}
    real_monotonic = time.monotonic

    def fake_monotonic():
        clock["calls"] += 1
        # read-tree and add see real time; the diff stream sees the deadline pass.
        return real_monotonic() + (10_000 if clock["calls"] > 4 else 0)

    monkeypatch.setattr(mwd.time, "monotonic", fake_monotonic)
    Path(harness.lease.target_worktree, "f.txt").write_text("z\n")
    with pytest.raises(mwd.MeasurementDiffError, match="git_timeout") as info:
        _capture(harness)
    assert info.value.partial_bytes is not None


def test_non_utf8_diff_is_flagged_lossy_with_exact_bytes(harness):
    worktree = harness.lease.target_worktree
    Path(worktree, "latin1.txt").write_bytes(b"caf\xe9 \xff\n")
    full = _bare_arm_diff(worktree, harness.lease.initial_head)
    values = _capture(harness)
    assert values["measurement_worktree_diff_lossy"] is True
    assert "\ufffd" in values["measurement_worktree_diff"]
    assert base64.b64decode(values["measurement_worktree_diff_b64"]) == full
    assert values["measurement_worktree_diff_sha256"] == hashlib.sha256(full).hexdigest()
    clean = Path(worktree, "latin1.txt")
    clean.write_text("cafe\n")
    values = _capture(harness)
    assert values["measurement_worktree_diff_lossy"] is False
    assert "measurement_worktree_diff_b64" not in values


def _record(harness, invocation=0):
    mwd.record_after_worker(
        read_state=harness.service._read_state,
        mutate_state=harness.service._mutate_state,
        task_id=harness.contract.task_id,
        attempt_id=harness.attempt_id,
        lease=harness.lease,
        invocation=invocation,
    )


def test_every_worker_return_rewrites_snapshot(monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    store: dict[str, dict] = {"t": {"attempt_id": "a", "measurement_worktree_diff": "first",
                   "measurement_worktree_diff_invocation": 0,
                   "measurement_worktree_diff_attempt_id": "a"}}  # fmt: skip
    captured = []

    def fake_capture(worktree, base, *, controller_root):
        captured.append(base)
        return {"measurement_worktree_diff": "second", "measurement_worktree_diff_base": base}

    monkeypatch.setattr(mwd, "capture_worktree_diff", fake_capture)

    def mutate(task_id, mutator):
        mutator(store[task_id])
        return store[task_id]

    lease = SimpleNamespace(initial_head="b" * 40, target_worktree="/w")

    def record(invocation):
        mwd.record_after_worker(
            read_state=store.get,
            mutate_state=mutate,
            task_id="t",
            attempt_id="a",
            lease=lease,
            invocation=invocation,
        )

    record(0)  # a re-invoke under the same invocation number rewrites
    assert store["t"]["measurement_worktree_diff"] == "second" and len(captured) == 1
    store["t"]["measurement_worktree_diff"] = "first"
    record(1)  # an escalated worker rewrites
    assert store["t"]["measurement_worktree_diff"] == "second"
    assert store["t"]["measurement_worktree_diff_invocation"] == 1
    # Another attempt's state is never written.
    store["t"] = {"attempt_id": "other"}
    record(0)
    assert store["t"] == {"attempt_id": "other"}


def test_record_never_raises(monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)

    def boom(*_a, **_k):
        raise OSError("state store down")

    mwd.record_after_worker(
        read_state=boom,
        mutate_state=boom,
        task_id="t",
        attempt_id="a",
        lease=SimpleNamespace(initial_head="b" * 40, target_worktree="/w"),
        invocation=0,
    )


def test_bridge_child_process_gets_start_time_switch(monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", False)
    seen = {}

    class FakeProcess:
        pid = os.getpid()

    def fake_popen(command, **kwargs):
        seen.update(kwargs["env"])
        return FakeProcess()

    monkeypatch.setattr(bridge.subprocess, "Popen", fake_popen)
    bridge._Processes().start_process(
        ["true"], cwd="/", env={"PATH": "/bin", mwd.MEASUREMENT_WORKTREE_DIFF_ENV: "1"}
    )
    assert seen == {"PATH": "/bin"}


def test_older_attempt_snapshot_does_not_suppress_capture(monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    store: dict[str, dict] = {
        "t": {
            "attempt_id": "new",
            "measurement_worktree_diff": "old attempt",
            "measurement_worktree_diff_invocation": 5,
            "measurement_worktree_diff_attempt_id": "old",
        }
    }
    monkeypatch.setattr(
        mwd,
        "capture_worktree_diff",
        lambda worktree, base, *, controller_root: {"measurement_worktree_diff": "new attempt"},
    )

    def mutate(task_id, mutator):
        mutator(store[task_id])
        return store[task_id]

    mwd.record_after_worker(
        read_state=store.get,
        mutate_state=mutate,
        task_id="t",
        attempt_id="new",
        lease=SimpleNamespace(initial_head="b" * 40, target_worktree="/w"),
        invocation=0,
    )
    assert store["t"]["measurement_worktree_diff"] == "new attempt"
    assert store["t"]["measurement_worktree_diff_attempt_id"] == "new"
    assert store["t"]["measurement_worktree_diff_invocation"] == 0


def test_persist_failed_fallback_never_lands_on_another_attempt(monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    store: dict[str, dict] = {"t": {"attempt_id": "other"}}

    def read_state(task_id):
        raise OSError("read failed")

    def mutate(task_id, mutator):
        mutator(store[task_id])
        return store[task_id]

    kwargs = dict(
        read_state=read_state,
        mutate_state=mutate,
        task_id="t",
        lease=SimpleNamespace(initial_head="b" * 40, target_worktree="/w"),
        invocation=0,
    )
    mwd.record_after_worker(attempt_id="mine", **kwargs)  # pyright: ignore[reportArgumentType]
    assert store["t"] == {"attempt_id": "other"}
    # The same fallback does land on the owning attempt, once.
    store["t"] = {"attempt_id": "mine"}
    mwd.record_after_worker(attempt_id="mine", **kwargs)  # pyright: ignore[reportArgumentType]
    assert store["t"]["measurement_worktree_diff_error"] == "persist_failed"
    assert store["t"]["measurement_worktree_diff_attempt_id"] == "mine"
    # A later failed write clears a stale diff of this attempt, never keeps it.
    store["t"].update(measurement_worktree_diff="stale", measurement_worktree_diff_sha256="x")
    store["t"].pop("measurement_worktree_diff_error")
    mwd.record_after_worker(attempt_id="mine", **kwargs)  # pyright: ignore[reportArgumentType]
    assert store["t"]["measurement_worktree_diff_error"] == "persist_failed"
    assert "measurement_worktree_diff" not in store["t"]
    assert "measurement_worktree_diff_sha256" not in store["t"]


def _registration(harness) -> Path:
    dotgit = Path(harness.lease.target_worktree) / ".git"
    gitdir = Path(dotgit.read_text().split(":", 1)[1].strip())
    return gitdir if gitdir.is_absolute() else (dotgit.parent / gitdir).resolve()


def test_registration_commondir_elsewhere_is_refused(harness, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    commondir = _registration(harness) / "commondir"
    original = commondir.read_text()
    commondir.write_text(str(other / ".git") + "\n")
    with pytest.raises(mwd.MeasurementDiffError, match="gitdir_untrusted"):
        _capture(harness)
    commondir.write_text(original)
    assert _capture(harness)["measurement_worktree_diff"] == ""


def test_registration_back_pointer_elsewhere_is_refused(harness, tmp_path):
    back = _registration(harness) / "gitdir"
    original = back.read_text()
    back.write_text(str(tmp_path / "elsewhere" / ".git") + "\n")
    with pytest.raises(mwd.MeasurementDiffError, match="gitdir_untrusted"):
        _capture(harness)
    back.write_text(original)
    assert _capture(harness)["measurement_worktree_diff"] == ""


def _commit_base_attributes(harness, text: str) -> str:
    """A base commit (on the Target branch) whose tree carries ``.gitattributes``."""
    worktree = harness.lease.target_worktree
    Path(worktree, ".gitattributes").write_text(text)
    _git(worktree, "-c", "core.hooksPath=/dev/null", "add", ".gitattributes")
    _git(
        worktree, "-c", "core.hooksPath=/dev/null", "-c", "user.name=t", "-c",
        "user.email=t@example.test", "commit", "-q", "-m", "attributes",
    )  # fmt: skip
    return _git(worktree, "rev-parse", "HEAD").decode().strip()


def test_base_attributes_match_shared_rule_for_eol_and_binary(harness):
    worktree = harness.lease.target_worktree
    base = _commit_base_attributes(harness, "* text=auto eol=lf\n*.bin -diff\n")
    Path(worktree, "crlf.txt").write_bytes(b"one\r\ntwo\r\n")
    Path(worktree, "blob.bin").write_bytes(b"plain text marked binary\n")
    reference = _shared_rule_diff(worktree, base)
    assert b"\r" not in reference  # text=auto normalized CRLF
    assert b"GIT binary patch" in reference  # -diff emitted a binary patch
    values = mwd.capture_worktree_diff(worktree, base, controller_root=_controller(harness))
    assert values["measurement_worktree_diff"].encode() == reference
    assert values["measurement_worktree_diff_sha256"] == hashlib.sha256(reference).hexdigest()


def test_worker_gitattributes_cannot_name_controller_filter(harness, tmp_path):
    worktree = harness.lease.target_worktree
    base = _commit_base_attributes(harness, "*.md text\n")
    marker = tmp_path / "filter-ran"
    _git(worktree, "config", "filter.ctl.clean", f"touch {marker}; cat")  # Controller config
    Path(worktree, ".gitattributes").write_text("*.txt filter=ctl\n")  # worker-written
    Path(worktree, "payload.txt").write_text("payload\n")
    values = mwd.capture_worktree_diff(worktree, base, controller_root=_controller(harness))
    assert not marker.exists()
    assert "+payload" in values["measurement_worktree_diff"]
    # Control: with the worktree's attributes (plain git), the filter runs.
    _bare_arm_diff(worktree, base)
    assert marker.exists()
