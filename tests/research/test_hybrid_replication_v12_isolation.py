"""V12 (#1216): source-checkout isolation and total-deadline process termination."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nexus.research import hybrid_replication_live as live


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(
        repo,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "commit",
        "-m",
        name,
    )
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def origin_clone(tmp_path: Path) -> tuple[Path, str, str]:
    """A clone whose origin carries a later branch and tag (the V11 leak shape)."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    base = _commit(origin, "base.txt")
    _git(origin, "checkout", "-q", "-b", "fix/answer-branch")
    later = _commit(origin, "answer.txt")
    _git(origin, "tag", "answer-tag")
    _git(origin, "checkout", "-q", "main")
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True, capture_output=True)
    assert "refs/remotes/origin/fix/answer-branch" in _git(repo, "for-each-ref")
    return repo, base, later


def _assert_isolated(shadow: Path, base: str, later: str) -> None:
    assert _git(shadow, "rev-parse", "HEAD") == base
    assert _git(shadow, "for-each-ref") == ""
    assert _git(shadow, "remote") == ""
    assert _git(shadow, "tag") == ""
    git_dir = Path(_git(shadow, "rev-parse", "--absolute-git-dir"))
    for leftover in ("FETCH_HEAD", "ORIG_HEAD"):
        assert not (git_dir / leftover).exists()
    packed = git_dir / "packed-refs"
    if packed.exists():
        assert [ln for ln in packed.read_text().splitlines() if not ln.startswith("#")] == []
    subprocess.run(["git", "cat-file", "-e", base], cwd=shadow, check=True)
    gone = subprocess.run(["git", "cat-file", "-e", later], cwd=shadow, capture_output=True)
    assert gone.returncode != 0
    assert not (shadow / "answer.txt").exists()


def test_shadow_checkout_contains_only_base_revision(
    tmp_path: Path, origin_clone: tuple[Path, str, str]
) -> None:
    repo, base, later = origin_clone
    shadow = tmp_path / "shadow"
    live._prepare_shadow_checkout(repo=repo, revision=base, source=shadow)
    _assert_isolated(shadow, base, later)


def test_shadow_checkout_hydration_path_is_isolated(
    tmp_path: Path, origin_clone: tuple[Path, str, str]
) -> None:
    repo, base, later = origin_clone
    # Base reachable only via refs/remotes/origin/main: drop local main and tags.
    _git(repo, "checkout", "-q", "--detach", base)
    _git(repo, "branch", "-D", "main")
    shadow = tmp_path / "shadow"
    live._prepare_shadow_checkout(repo=repo, revision=base, source=shadow)
    _assert_isolated(shadow, base, later)


def test_codex_arm_no_longer_shares_repo_refs() -> None:
    source = Path(live.__file__).read_text(encoding="utf-8")
    assert '"worktree", "add"' not in source


_FAKE_PROVIDER = """
import json, os, signal, sys, time
ignore_term = sys.argv[3] == "ignore"
if ignore_term:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
op, tree = sys.argv[1], sys.argv[2]
rec = {"status": "RUNNING", "pid": os.getpid(), "provider_pgid": os.getpgrp()}
open(op, "w").write(json.dumps(rec))
n = 0
while True:
    n += 1
    open(tree, "a").write("x")
    time.sleep(0.05)
"""


def _spawn_provider(tmp_path: Path, mode: str) -> tuple[subprocess.Popen[bytes], Path, Path]:
    script = tmp_path / "fake_provider.py"
    script.write_text(_FAKE_PROVIDER, encoding="utf-8")
    op = tmp_path / "operation.json"
    tree = tmp_path / "tree.txt"
    proc = subprocess.Popen(
        [sys.executable, str(script), str(op), str(tree), mode], start_new_session=True
    )
    for _ in range(100):
        if op.is_file() and tree.is_file():
            break
        time.sleep(0.05)
    return proc, op, tree


@pytest.mark.parametrize("mode", ["term", "ignore"])
def test_terminate_agy_operation_stops_writer(tmp_path: Path, mode: str) -> None:
    proc, op, tree = _spawn_provider(tmp_path, mode)
    try:
        assert live.terminate_agy_operation(op, grace_seconds=0.5) is True
        proc.wait(timeout=5)
        size = tree.stat().st_size
        time.sleep(0.3)
        assert tree.stat().st_size == size
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)


_FAKE_DISPATCH = """#!{python}
import json, subprocess, sys
op_dir = {op_dir!r}
import os
os.makedirs(op_dir, exist_ok=True)
subprocess.Popen(
    [{python!r}, {provider!r}, op_dir + "/operation.json", {tree!r}, "ignore"],
    start_new_session=True,
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
import time
while not os.path.exists(op_dir + "/operation.json"):
    time.sleep(0.02)
print(json.dumps({{"operation_id": "op1", "stdout_path": op_dir + "/stdout.log",
                  "stderr_path": op_dir + "/stderr.log"}}))
"""


def test_run_agy_dispatch_kills_process_before_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = tmp_path / "fake_provider.py"
    provider.write_text(_FAKE_PROVIDER, encoding="utf-8")
    tree = tmp_path / "tree.txt"
    op_dir = tmp_path / "ops" / "operations" / "op1"
    dispatch = tmp_path / "nexus-agy-dispatch"
    dispatch.write_text(
        _FAKE_DISPATCH.format(
            python=sys.executable, op_dir=str(op_dir), provider=str(provider), tree=str(tree)
        ),
        encoding="utf-8",
    )
    dispatch.chmod(0o755)
    monkeypatch.setattr(live, "resolve_canonical_agy_dispatch_path", lambda _b: dispatch)
    monkeypatch.setattr(live, "AGY_PROVIDER_TERMINAL_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(live, "AGY_TERMINATION_GRACE_SECONDS", 0.3)
    cwd = tmp_path / "source"
    cwd.mkdir()

    record, _wall, _o, _e, timed_out, err, _d = live._run_agy_dispatch(
        cwd=cwd,
        prompt="p",
        mode="accept-edits",
        binding={"strong_online": {"effort": "medium"}},
        timeout=1,
        poll_timeout=1.0,
        poll_interval=0.02,
        operation_root=tmp_path / "ops",
    )
    assert timed_out is True
    assert err == "TIMEOUT"
    # Candidate sealing happens after return: the writer must already be gone.
    size = tree.stat().st_size
    time.sleep(0.4)
    assert tree.stat().st_size == size
    pgid = record["provider_pgid"]
    with pytest.raises(ProcessLookupError):
        os.killpg(pgid, 0)
