"""#2721 measurement snapshot of the worker's raw Target diff.

Runs through the real ``_run_default_resumable`` path (runtime coordination
bridge, nexus-runtime ``ExecutionCoordinator``) with a real git Target lease and
a fake ``WorkerRegistry.invoke`` that edits the Target.  Finalization is a
recorder, so each test sees the task state exactly as verification would.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
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


def test_resume_does_not_overwrite_existing_snapshot(harness, monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    state = harness.service._read_state(harness.contract.task_id)
    state["measurement_worktree_diff"] = "FIRST"
    harness.service._write_state(harness.contract.task_id, state)
    monkeypatch.setattr(
        mwd.subprocess, "run", lambda *a, **k: pytest.fail("a recorded snapshot is not retaken")
    )
    monkeypatch.setattr(harness.service.worker_registry, "invoke", _invoke_editing())
    assert harness.run() == {"finalized": True}
    assert harness.seen["state"]["measurement_worktree_diff"] == "FIRST"


def test_git_failure_records_error_and_outcome_is_unchanged(harness, monkeypatch, tmp_path):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    real_run = subprocess.run

    def failing_git(args, **kwargs):
        if list(args[1:7]) == list(mwd._GIT_SAFE_CONFIG):  # only the snapshot's git
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
        if list(args[1:7]) == list(mwd._GIT_SAFE_CONFIG):  # only the snapshot's git
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
    values = mwd.capture_worktree_diff(worktree, harness.lease.initial_head, max_bytes=1000)
    assert values["measurement_worktree_diff"] == full[:1000].decode()
    assert values["measurement_worktree_diff_bytes"] == len(full) > 1000
    assert values["measurement_worktree_diff_sha256"] == hashlib.sha256(full).hexdigest()
    assert values["measurement_worktree_diff_truncated"] is True
    untruncated = mwd.capture_worktree_diff(worktree, harness.lease.initial_head)
    assert untruncated["measurement_worktree_diff"] == full.decode()
    assert untruncated["measurement_worktree_diff_truncated"] is False


def test_git_runs_hardened(harness, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/nonexistent")
    monkeypatch.setenv("GIT_WORK_TREE", "/nonexistent")
    calls = []
    real_run = subprocess.run

    def spy(args, **kwargs):
        calls.append((list(args), kwargs))
        return real_run(args, **kwargs)

    monkeypatch.setattr(mwd.subprocess, "run", spy)
    values = mwd.capture_worktree_diff(harness.lease.target_worktree, harness.lease.initial_head)
    assert values["measurement_worktree_diff"] == ""
    assert [args[7] for args, _ in calls] == ["read-tree", "add", "diff"]
    for args, kwargs in calls:
        assert args[1:7] == list(mwd._GIT_SAFE_CONFIG)
        env = kwargs["env"]
        assert sorted(k for k in env if k.startswith("GIT_")) == [
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_INDEX_FILE",
            "GIT_TERMINAL_PROMPT",
        ]
        assert env["GIT_CONFIG_GLOBAL"] == "/dev/null" and env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert kwargs["stdin"] is subprocess.DEVNULL and kwargs["timeout"] > 0


def test_escalated_worker_replaces_snapshot_but_same_invocation_does_not(monkeypatch):
    monkeypatch.setattr(mwd, "MEASUREMENT_WORKTREE_DIFF_AT_START", True)
    store: dict[str, dict] = {"t": {"attempt_id": "a", "measurement_worktree_diff": "first",
                   "measurement_worktree_diff_invocation": 0}}  # fmt: skip
    captured = []

    def fake_capture(worktree, base):
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

    record(0)
    assert store["t"]["measurement_worktree_diff"] == "first" and captured == []
    record(1)
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
