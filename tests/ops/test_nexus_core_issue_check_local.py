from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-core-issue-check-local"
PIN = "a" * 40
WORKFLOW = ".github/workflows/nexus-core-issue-completion.yml"

FAKE_CERTIFY = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

sub = sys.argv[1]
if os.environ.get("FAKE_MATERIAL_CHECK") and not os.environ.get("NEXUS_CORE_MATERIAL_PYTHON"):
    sys.exit(9)
Path(os.environ["FAKE_CALLS"]).open("a").write(sub + " " + os.getcwd() + "\\n")
if sub == "issue-check":
    d = Path(".nexus-core/receipts")
    d.mkdir(parents=True, exist_ok=True)
    status = os.environ.get("FAKE_STATUS", "VERIFIED")
    (d / "r1.json").write_text(json.dumps({
        "receipt_hash": "rh123",
        "target": {"target_tree": "tt456"},
        "outcome": {"status": status},
    }))
    print("claim ceiling: ISSUE_BOUND_VERIFIED")
    sys.exit(0 if status == "VERIFIED" else 3)
print("init ok")
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def env(tmp_path: Path):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / WORKFLOW).write_text(f"env:\n  NEXUS_CORE_TOOL_PIN: {PIN}\n")
    (repo / ".gitignore").write_text("ignored/\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin", "main")
    certify = tmp_path / "fake-certify"
    certify.write_text(FAKE_CERTIFY)
    certify.chmod(certify.stat().st_mode | stat.S_IXUSR)
    calls = tmp_path / "calls.log"
    penv = dict(os.environ, GITHUB_TOKEN="tok", FAKE_CALLS=str(calls), FAKE_MATERIAL_CHECK="1")
    return {"repo": repo, "certify": certify, "calls": calls, "env": penv, "tmp": tmp_path}


def run(env, *extra: str, **envover: str):
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--issue",
        "7",
        "--repo-root",
        str(env["repo"]),
        "--certify-bin",
        str(env["certify"]),
        "--material-python",
        sys.executable,
        "--output-dir",
        str(env["tmp"] / "out"),
        *extra,
    ]
    penv = dict(env["env"], PYTHONDONTWRITEBYTECODE="1", **envover)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=penv)
    return proc, json.loads(proc.stdout)


def test_success_path(env):
    proc, out = run(env)
    assert proc.returncode == 0, proc.stderr
    assert out["schema"] == "nexus.core_issue_check_local.v1"
    assert out["pin"] == PIN
    assert out["status"] == "VERIFIED"
    assert out["claim"] == "ISSUE_BOUND_VERIFIED"
    assert out["issue"] == 7
    assert out["head"] == git(env["repo"], "rev-parse", "HEAD")
    assert out["head_tree"] == git(env["repo"], "rev-parse", "HEAD^{tree}")
    assert out["base_sha"] == git(env["repo"], "rev-parse", "origin/main")
    assert out["receipt_hash"] == "rh123"
    assert out["target_tree"] == "tt456"
    receipt = Path(out["receipt_path"])
    assert receipt.parent == env["tmp"] / "out"
    assert out["receipt_sha256"] == hashlib.sha256(receipt.read_bytes()).hexdigest()
    assert Path(out["log_path"]).read_text().count("init ok") == 1
    subs = [line.split()[0] for line in env["calls"].read_text().splitlines()]
    assert subs == ["issue-init", "issue-check"]


def test_worktree_removed_after_success(env):
    run(env)
    assert len(git(env["repo"], "worktree", "list").splitlines()) == 1
    cwd = env["calls"].read_text().split()[1]
    assert not Path(cwd).exists()


def test_dirty_tracked_fails_closed(env):
    (env["repo"] / WORKFLOW).write_text("changed\n")
    proc, out = run(env)
    assert proc.returncode == 2
    assert out["error_code"] == "WORKTREE_DIRTY"
    assert not env["calls"].exists()


def test_untracked_fails_closed_but_ignored_ok(env):
    (env["repo"] / "ignored").mkdir()
    (env["repo"] / "ignored" / "x").write_text("x")
    proc, _ = run(env)
    assert proc.returncode == 0
    (env["repo"] / "new.txt").write_text("x")
    proc, out = run(env)
    assert proc.returncode == 2
    assert out["error_code"] == "WORKTREE_DIRTY"


def test_pin_unresolved(env):
    repo = env["repo"]
    (repo / WORKFLOW).write_text("env:\n  NEXUS_CORE_TOOL_PIN: notahash\n")
    git(repo, "commit", "-q", "-am", "bad pin")
    git(repo, "push", "-q", "origin", "main")
    proc, out = run(env)
    assert proc.returncode == 2
    assert out["error_code"] == "CORE_PIN_UNRESOLVED"
    assert not env["calls"].exists()


def test_pin_read_from_base_not_head(env):
    repo = env["repo"]
    (repo / WORKFLOW).write_text("env:\n  NEXUS_CORE_TOOL_PIN: " + "b" * 40 + "\n")
    git(repo, "commit", "-q", "-am", "head pin differs")
    proc, out = run(env, "--no-fetch")
    assert proc.returncode == 0, proc.stderr
    assert out["pin"] == PIN


def test_core_failure_exit_one_and_cleanup(env):
    proc, out = run(env, FAKE_STATUS="FAILED_CLOSED")
    assert proc.returncode == 1
    assert out["status"] == "FAILED_CLOSED"
    assert Path(out["receipt_path"]).exists()
    assert len(git(env["repo"], "worktree", "list").splitlines()) == 1
    assert not Path(env["calls"].read_text().split()[-1]).exists()


def test_cleanup_on_tooling_error(env):
    env["certify"].chmod(0o644)
    proc, out = run(env)
    assert proc.returncode == 2
    assert out["error_code"] == "CORE_EXEC_FAILED"
    assert len(git(env["repo"], "worktree", "list").splitlines()) == 1
