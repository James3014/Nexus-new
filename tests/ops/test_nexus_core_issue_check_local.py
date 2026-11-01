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
        "outcome": {
            "status": status,
            **({"reason_codes": json.loads(os.environ["FAKE_REASONS"])} if "FAKE_REASONS" in os.environ else {}),
            **({"transport_error": json.loads(os.environ["FAKE_TRANSPORT"])} if "FAKE_TRANSPORT" in os.environ else {}),
        },
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


def test_pin_read_from_two_job_workflow_fields(env):
    """The two-job gate pins the tool via nexus-certify-ref and uses@sha (nexus-core#116/#120)."""
    repo = env["repo"]
    (repo / WORKFLOW).write_text(
        "jobs:\n  run:\n    steps:\n"
        f"      - uses: James3014/nexus-core/.github/actions/issue-gate@{PIN}\n"
        f'        with:\n          nexus-certify-ref: "{PIN}"\n'
        "  verify:\n    steps:\n"
        f"      - uses: James3014/nexus-core/.github/actions/receipt-verify@{PIN}  # pin\n"
        f'        with:\n          nexus-certify-ref: "{PIN}"\n'
    )
    git(repo, "commit", "-q", "-am", "two-job gate")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin", "main")
    proc, out = run(env)
    assert proc.returncode == 0, proc.stderr
    assert out["pin"] == PIN


def test_failed_receipt_reason_codes_in_summary(env):
    proc, out = run(
        env,
        FAKE_STATUS="FAILED_CLOSED",
        FAKE_REASONS='["MISSING_EVIDENCE", "STALE_HEAD"]',
        FAKE_TRANSPORT="true",
    )
    assert proc.returncode == 1
    assert out["status"] == "FAILED_CLOSED"
    assert out["reason_codes"] == ["MISSING_EVIDENCE", "STALE_HEAD"]
    assert out["transport_error"] is True


def test_verified_receipt_empty_reason_codes(env):
    proc, out = run(env)
    assert proc.returncode == 0, proc.stderr
    assert out["reason_codes"] == []
    assert out["transport_error"] is False


def test_malformed_reason_fields_are_normalised(env):
    proc, out = run(env, FAKE_STATUS="FAILED_CLOSED", FAKE_REASONS='"oops"', FAKE_TRANSPORT='"yes"')
    assert proc.returncode == 1
    assert out["reason_codes"] == []
    assert out["transport_error"] is False


def test_json_out_writes_summary_file(env):
    target = env["tmp"] / "nested" / "dir" / "summary.json"
    proc, out = run(env, "--json-out", str(target))
    assert proc.returncode == 0, proc.stderr
    assert target.read_bytes() == proc.stdout.encode("utf-8")
    assert json.loads(target.read_text(encoding="utf-8")) == out
    assert target.read_text(encoding="utf-8").endswith("}\n")


def test_json_out_written_on_tooling_error(env):
    (env["repo"] / "new.txt").write_text("x")
    target = env["tmp"] / "err" / "summary.json"
    proc, out = run(env, "--json-out", str(target))
    assert proc.returncode == 2
    assert out["error_code"] == "WORKTREE_DIRTY"
    assert json.loads(target.read_text(encoding="utf-8")) == out


def test_json_out_write_failure_keeps_exit_code(env):
    blocker = env["tmp"] / "blocker"
    blocker.write_text("file")
    proc, out = run(env, "--json-out", str(blocker / "summary.json"))
    assert proc.returncode == 0
    assert out["status"] == "VERIFIED"
    assert "warning: cannot write --json-out" in proc.stderr


# --- materials: trusted base lock files only, pinned entries only, timeout ---

GOOD_RUNTIME = (
    "# comment\n"
    "nexus-runtime @ git+https://github.com/James3014/nexus-runtime.git@" + "1" * 40 + "\n"
)
GOOD_LEARNING = (
    "nexus-learning @ git+https://github.com/James3014/nexus-learning.git@" + "2" * 40 + "\n"
)

FAKE_UV = """#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path

args = sys.argv[1:]
log = Path(os.environ["FAKE_UV_LOG"])
entry = {"args": args, "cwd": os.getcwd()}
if args[:1] == ["venv"]:
    env_dir = Path(args[-1])
    (env_dir / "bin").mkdir(parents=True, exist_ok=True)
    (env_dir / "bin" / "python").symlink_to(sys.executable)
elif args[:2] == ["pip", "install"]:
    req = args[args.index("--requirement") + 1]
    entry["requirement"] = Path(req).read_text()
    if os.environ.get("FAKE_UV_SLEEP"):
        child = subprocess.Popen(["sleep", "60"])
        Path(os.environ["FAKE_UV_PIDS"]).write_text(f"{os.getpid()} {child.pid}")
        time.sleep(60)
with log.open("a") as fh:
    fh.write(json.dumps(entry) + "\\n")
"""


def _load_module():
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("nexus_core_issue_check_local", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _with_requirements(env, runtime: str = GOOD_RUNTIME, learning: str = GOOD_LEARNING):
    repo = env["repo"]
    (repo / "requirements").mkdir(exist_ok=True)
    (repo / "requirements/canonical-runtime.txt").write_text(runtime)
    (repo / "requirements/canonical-learning.txt").write_text(learning)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "requirements")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin", "main")
    bindir = env["tmp"] / "fakebin"
    bindir.mkdir(exist_ok=True)
    uv = bindir / "uv"
    uv.write_text(FAKE_UV)
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    env["uv_log"] = env["tmp"] / "uv.log"
    env["env"] = dict(
        env["env"],
        PATH=f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
        FAKE_UV_LOG=str(env["uv_log"]),
        FAKE_UV_PIDS=str(env["tmp"] / "uv.pids"),
    )
    return env


def run_materials(env, *extra: str, **envover: str):
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--issue",
        "7",
        "--repo-root",
        str(env["repo"]),
        "--certify-bin",
        str(env["certify"]),
        "--cache-root",
        str(env["tmp"] / "cache"),
        "--output-dir",
        str(env["tmp"] / "out"),
        "--no-fetch",
        *extra,
    ]
    penv = dict(env["env"], PYTHONDONTWRITEBYTECODE="1", **envover)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=penv, timeout=120)
    return proc, json.loads(proc.stdout)


def _uv_calls(env):
    if not env["uv_log"].exists():
        return []
    return [json.loads(line) for line in env["uv_log"].read_text().splitlines()]


def test_materials_installed_from_base_not_head(env):
    """A candidate head that edits the lock files cannot change what gets installed."""
    env = _with_requirements(env)
    repo = env["repo"]
    (repo / "requirements/canonical-runtime.txt").write_text(GOOD_RUNTIME + "-e ./evil\n")
    (repo / "requirements/canonical-learning.txt").write_text(
        "--index-url https://example.invalid/simple\nx\n"
    )
    git(repo, "commit", "-q", "-am", "head edits requirements")
    proc, out = run_materials(env)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    installs = [c for c in _uv_calls(env) if c["args"][:2] == ["pip", "install"]]
    assert [c["requirement"] for c in installs] == [
        GOOD_LEARNING,
        GOOD_RUNTIME.split("\n", 1)[1],
    ]
    for call in installs:
        assert "evil" not in call["requirement"]
        assert "index-url" not in call["requirement"]
        req = Path(call["args"][call["args"].index("--requirement") + 1])
        assert repo not in req.parents
        assert Path(call["cwd"]).resolve() != repo.resolve()
        assert "--require-hashes" not in call["args"]


@pytest.mark.parametrize(
    "bad_line",
    [
        "-e ./evil",
        "-r other.txt",
        "-c constraints.txt",
        "--index-url https://example.invalid/simple",
        "--extra-index-url https://example.invalid/simple",
        "./local-pkg",
        "/abs/local-pkg",
        "file:///tmp/pkg",
        "pkg @ file:///tmp/pkg",
        "pkg",
        "pkg>=1.0",
        "pkg==1.0",
        "pkg @ git+https://github.com/James3014/nexus-runtime.git@main",
        "pkg @ git+https://github.com/other/nexus-runtime.git@" + "1" * 40,
        "pkg @ git+https://github.com/James3014/x.git@" + "1" * 40 + "#subdirectory=y",
        "pkg @ https://example.invalid/pkg-1.0.tar.gz",
    ],
)
def test_materials_untrusted_base_line_fails_closed_before_install(env, bad_line):
    env = _with_requirements(env, runtime=GOOD_RUNTIME + bad_line + "\n")
    proc, out = run_materials(env)
    assert proc.returncode == 2
    assert out["error_code"] == "MATERIALS_UNTRUSTED"
    assert not [c for c in _uv_calls(env) if c["args"][:1] in (["venv"], ["pip"])]
    assert not env["calls"].exists()


def test_materials_hash_pinned_uses_require_hashes(env):
    hashed = "pkg==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n"
    env = _with_requirements(env, runtime=hashed)
    proc, out = run_materials(env)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    installs = [c for c in _uv_calls(env) if c["args"][:2] == ["pip", "install"]]
    runtime_call = installs[1]
    assert runtime_call["requirement"] == "pkg==1.0 --hash=sha256:" + "a" * 64 + "\n"
    assert "--require-hashes" in runtime_call["args"]
    assert "--require-hashes" not in installs[0]["args"]


def test_materials_cache_reused_only_after_complete_install(env):
    env = _with_requirements(env)
    proc, _ = run_materials(env)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    first = len(_uv_calls(env))
    proc, _ = run_materials(env)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert len(_uv_calls(env)) == first


def _pid_alive(pid: int) -> bool:
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


def test_materials_install_timeout_kills_group_and_fails_closed(env):
    import time

    env = _with_requirements(env)
    started = time.monotonic()
    proc, out = run_materials(env, "--materials-timeout", "3", FAKE_UV_SLEEP="1")
    assert time.monotonic() - started < 30
    assert proc.returncode == 2
    assert out["error_code"] == "MATERIALS_FAILED"
    assert "timed out" in out["error"]
    assert not env["calls"].exists()
    pids = [int(p) for p in (env["tmp"] / "uv.pids").read_text().split()]
    deadline = time.monotonic() + 10
    while any(_pid_alive(p) for p in pids) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not any(_pid_alive(p) for p in pids)
    # The half-built venv is not reused: the next run rebuilds it.
    (env["tmp"] / "uv.log").unlink()
    proc, _ = run_materials(env)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert [c["args"][0] for c in _uv_calls(env)][:1] == ["venv"]


def test_trusted_requirements_normalizes_and_rejects():
    mod = _load_module()
    assert mod.trusted_requirements(GOOD_RUNTIME, "r.txt") == GOOD_RUNTIME.split("\n", 1)[1]
    with pytest.raises(mod.LocalCheckError) as exc:
        mod.trusted_requirements("# only a comment\n", "r.txt")
    assert exc.value.code == "MATERIALS_UNTRUSTED"
    with pytest.raises(mod.LocalCheckError) as exc:
        mod.trusted_requirements(GOOD_LEARNING.rstrip("\n") + "\x0c-e ./evil\n", "r.txt")
    assert exc.value.code == "MATERIALS_UNTRUSTED"
    with pytest.raises(mod.LocalCheckError) as exc:
        mod.trusted_requirements("pkg==1.0 \\", "r.txt")
    assert exc.value.code == "MATERIALS_UNTRUSTED"
