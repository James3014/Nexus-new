"""nexus-core-issue-check-local matches the CI issue gate on receipts and evidence universe.

The local tool reads only the receipt that Core's issue-check reports through
``--receipt-path-out``, fails closed when the candidate head carries anything under
``.nexus-core/receipts``, and passes the evidence universe declared by the base
workflow to both Core subcommands. Every fixture lives in tmp_path; the fake
nexus-certify only writes files inside the temporary worktree and the test's tmp dir.
"""

from __future__ import annotations

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
RECEIPT_A = "20261101T000000.000001+0000-aaaaaaaaaaaa.json"
RECEIPT_B = "20261101T000000.000002+0000-bbbbbbbbbbbb.json"

# issue-init exits FAKE_INIT_RC (after writing a receipt-named file when
# FAKE_INIT_WRITES=1). issue-check writes the receipts named in FAKE_WRITE (comma
# separated, in order, each newer than the last), reports FAKE_POINT (a name, or an
# absolute path) through --receipt-path-out when given, and exits FAKE_CHECK_RC.
FAKE_CERTIFY = """#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path

sub = sys.argv[1]
with open(os.environ["FAKE_CALLS"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
d = Path(".nexus-core/receipts")
if sub == "issue-init":
    if os.environ.get("FAKE_INIT_WRITES") == "1":
        d.mkdir(parents=True, exist_ok=True)
        (d / "20261101T000000.000009+0000-cccccccccccc.json").write_text(
            json.dumps({"outcome": {"status": "VERIFIED"}})
        )
    sys.exit(int(os.environ.get("FAKE_INIT_RC", "0")))
for name in filter(None, os.environ.get("FAKE_WRITE", "").split(",")):
    d.mkdir(parents=True, exist_ok=True)
    status = "VERIFIED" if name == os.environ.get("FAKE_VERIFIED_NAME") else "FAILED_CLOSED"
    (d / name).write_text(json.dumps({"receipt_hash": name, "outcome": {"status": status}}))
    time.sleep(0.02)
point = os.environ.get("FAKE_POINT", "")
argv = sys.argv[1:]
if point and "--receipt-path-out" in argv:
    target = Path(point) if os.path.isabs(point) else (d / point).resolve()
    Path(argv[argv.index("--receipt-path-out") + 1]).write_text(str(target) + "\\n")
sys.exit(int(os.environ.get("FAKE_CHECK_RC", "0")))
"""

PLANTED = {"receipt_hash": "planted", "outcome": {"status": "VERIFIED", "reason_codes": []}}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _workflow(universe: str | None) -> str:
    text = f"env:\n  NEXUS_CORE_TOOL_PIN: {PIN}\n"
    if universe is not None:
        text += f"jobs:\n  run:\n    with:\n      evidence-universe: {universe}\n"
    return text


def _make_repo(tmp_path: Path, base_workflow: str) -> Path:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / WORKFLOW).write_text(base_workflow)
    (repo / ".gitignore").write_text(".nexus-core/receipts/\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin", "main")
    git(repo, "checkout", "-q", "-b", "candidate")
    (repo / "a.txt").write_text("candidate\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "candidate change")
    return repo


def _commit_receipt(repo: Path, name: str = "zz-planted.json") -> None:
    receipt = repo / ".nexus-core/receipts" / name
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(PLANTED))
    git(repo, "add", "-f", str(receipt))
    git(repo, "commit", "-q", "-m", "candidate commits a receipt")


@pytest.fixture
def env(tmp_path: Path):
    repo = _make_repo(tmp_path, _workflow("trusted-config"))
    certify = tmp_path / "fake-certify"
    certify.write_text(FAKE_CERTIFY)
    certify.chmod(certify.stat().st_mode | stat.S_IXUSR)
    return {"repo": repo, "certify": certify, "tmp": tmp_path, "calls": tmp_path / "calls.log"}


def run(env, **envover: str):
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--issue",
        "7",
        "--repo-root",
        str(env["repo"]),
        "--certify-bin",
        str(env["certify"]),
        "--no-fetch",
        "--cache-root",
        str(env["tmp"] / "cache"),
        "--output-dir",
        str(env["tmp"] / "out"),
    ]
    penv = dict(
        os.environ,
        GITHUB_TOKEN="tok",
        PYTHONDONTWRITEBYTECODE="1",
        FAKE_CALLS=str(env["calls"]),
        **envover,
    )
    proc = subprocess.run(cmd, capture_output=True, text=True, env=penv, timeout=120)
    return proc, json.loads(proc.stdout)


def _calls(env) -> dict[str, list[str]]:
    if not env["calls"].exists():
        return {}
    return {
        argv[0]: argv[1:]
        for argv in (json.loads(line) for line in env["calls"].read_text().splitlines())
    }


def _flag(argv: list[str], name: str) -> str | None:
    return argv[argv.index(name) + 1] if name in argv else None


# --- receipt selection: only the receipt issue-check reports ---


def test_reported_receipt_is_the_one_summarised(env):
    """Core reports the older of two receipts it wrote: that one is summarised and copied."""
    proc, out = run(
        env,
        FAKE_WRITE=f"{RECEIPT_A},{RECEIPT_B}",
        FAKE_POINT=RECEIPT_A,
        FAKE_VERIFIED_NAME=RECEIPT_A,
    )
    assert proc.returncode == 0, (proc.stderr, out)
    assert out["status"] == "VERIFIED"
    assert out["receipt_hash"] == RECEIPT_A
    assert Path(out["receipt_path"]) == env["tmp"] / "out" / RECEIPT_A


def test_core_exit_zero_with_unreported_receipt_is_receipt_missing(env):
    """Core exits 0 and writes a receipt but reports none: fail closed, never pick by name/time."""
    proc, out = run(env, FAKE_WRITE=RECEIPT_A, FAKE_VERIFIED_NAME=RECEIPT_A, FAKE_CHECK_RC="0")
    assert proc.returncode == 2, out
    assert out["error_code"] == "RECEIPT_MISSING"
    assert out["status"] == "ERROR"


def test_core_exit_zero_without_receipt_is_not_verified_by_committed_receipt(env):
    """A head that commits a VERIFIED-looking receipt is not reported VERIFIED when Core wrote none."""
    _commit_receipt(env["repo"])
    proc, out = run(env, FAKE_CHECK_RC="0")
    assert proc.returncode != 0, out
    assert out.get("status") != "VERIFIED", out


def test_core_failure_without_receipt_reports_no_receipt(env):
    """Core exits non-zero and reports no receipt: exit 1 with no receipt in the summary."""
    proc, out = run(env, FAKE_WRITE=RECEIPT_A, FAKE_CHECK_RC="3")
    assert proc.returncode == 1, out
    assert out["status"] == "NO_RECEIPT_STATUS"
    assert out["receipt_path"] is None


def test_issue_check_gets_receipt_pointer_outside_worktree(env):
    """Only issue-check is asked for the pointer, and the pointer file lies outside the checkout."""
    proc, out = run(env, FAKE_WRITE=RECEIPT_A, FAKE_POINT=RECEIPT_A, FAKE_VERIFIED_NAME=RECEIPT_A)
    assert proc.returncode == 0, (proc.stderr, out)
    calls = _calls(env)
    assert "--receipt-path-out" not in calls["issue-init"]
    pointer = Path(_flag(calls["issue-check"], "--receipt-path-out") or "")
    assert pointer.is_absolute()
    assert ".nexus-core" not in pointer.parts


@pytest.mark.parametrize(
    "point",
    [
        "outside",  # a file outside the receipts directory
        "not-a-core-name.json",  # inside, but not a Core receipt name
        "missing",  # names a file that does not exist
    ],
)
def test_invalid_receipt_pointer_fails_closed(env, point):
    """A pointer that is not one existing Core receipt directly in the receipts dir is refused."""
    over: dict[str, str] = {"FAKE_CHECK_RC": "0", "FAKE_VERIFIED_NAME": "not-a-core-name.json"}
    if point == "outside":
        stray = env["tmp"] / RECEIPT_A
        stray.write_text(json.dumps(PLANTED))
        over["FAKE_POINT"] = str(stray)
    elif point == "missing":
        over["FAKE_POINT"] = RECEIPT_B
    else:
        over.update(FAKE_WRITE=point, FAKE_POINT=point)
    proc, out = run(env, **over)
    assert proc.returncode == 2, out
    assert out["error_code"] == "RECEIPT_POINTER_INVALID"


# --- candidate-carried receipts: refused before Core runs, like CI ---


def test_candidate_committed_receipts_fail_closed(env):
    """A head that commits files under .nexus-core/receipts is refused before Core runs."""
    _commit_receipt(env["repo"])
    proc, out = run(env, FAKE_WRITE=RECEIPT_A, FAKE_POINT=RECEIPT_A, FAKE_CHECK_RC="1")
    assert proc.returncode == 2, out
    assert out["status"] == "ERROR"
    assert out["error_code"] == "CANDIDATE_RECEIPTS_PRESENT"
    assert _calls(env) == {}


def test_candidate_symlinked_core_dir_fails_closed(env):
    """A head whose .nexus-core is a symlink is refused before Core runs."""
    repo = env["repo"]
    (repo / "elsewhere").mkdir()
    (repo / "elsewhere" / "keep").write_text("x\n")
    (repo / ".nexus-core").symlink_to("elsewhere")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "symlinked core dir")
    proc, out = run(env)
    assert proc.returncode == 2, out
    assert out["error_code"] == "CANDIDATE_RECEIPTS_PRESENT"
    assert _calls(env) == {}


def test_issue_init_failure_reports_no_receipt(env):
    """issue-init fails, so issue-check never runs: no receipt is reported as the result."""
    proc, out = run(env, FAKE_INIT_RC="5", FAKE_INIT_WRITES="1")
    assert proc.returncode == 1, out
    assert out["receipt_path"] is None
    assert out["receipt_hash"] is None
    assert out["status"] != "VERIFIED"
    assert list(_calls(env)) == ["issue-init"]


def test_issue_init_failure_with_committed_receipt_reports_no_receipt(env):
    """With a committed receipt and a failing issue-init, nothing is reported as the result."""
    _commit_receipt(env["repo"])
    proc, out = run(env, FAKE_INIT_RC="5")
    assert proc.returncode != 0
    assert out.get("receipt_path") is None, out
    assert out.get("status") != "VERIFIED", out


# --- evidence universe: read from the base workflow, passed to both subcommands ---


def test_trusted_universe_passed_to_both_subcommands(env):
    """The base workflow's evidence-universe reaches issue-init and issue-check (CI parity)."""
    proc, out = run(env, FAKE_WRITE=RECEIPT_A, FAKE_POINT=RECEIPT_A, FAKE_VERIFIED_NAME=RECEIPT_A)
    assert proc.returncode == 0, (proc.stderr, out)
    calls = _calls(env)
    assert _flag(calls["issue-init"], "--evidence-universe") == "trusted-config"
    assert _flag(calls["issue-check"], "--evidence-universe") == "trusted-config"


def test_universe_read_from_base_not_head(env):
    """A head that edits the workflow's evidence-universe does not change what is passed."""
    repo = env["repo"]
    (repo / WORKFLOW).write_text(_workflow("issue-marker"))
    git(repo, "commit", "-q", "-am", "head edits universe")
    proc, out = run(env, FAKE_WRITE=RECEIPT_A, FAKE_POINT=RECEIPT_A, FAKE_VERIFIED_NAME=RECEIPT_A)
    assert proc.returncode == 0, (proc.stderr, out)
    calls = _calls(env)
    assert _flag(calls["issue-init"], "--evidence-universe") == "trusted-config"
    assert _flag(calls["issue-check"], "--evidence-universe") == "trusted-config"


def test_universe_defaults_to_issue_marker_when_base_declares_none(tmp_path):
    """No evidence-universe in the base workflow: the CI action default, issue-marker."""
    repo = _make_repo(tmp_path, _workflow(None))
    certify = tmp_path / "fake-certify"
    certify.write_text(FAKE_CERTIFY)
    certify.chmod(0o755)
    env = {"repo": repo, "certify": certify, "tmp": tmp_path, "calls": tmp_path / "calls.log"}
    proc, out = run(env, FAKE_WRITE=RECEIPT_A, FAKE_POINT=RECEIPT_A, FAKE_VERIFIED_NAME=RECEIPT_A)
    assert proc.returncode == 0, (proc.stderr, out)
    calls = _calls(env)
    assert _flag(calls["issue-init"], "--evidence-universe") == "issue-marker"
    assert _flag(calls["issue-check"], "--evidence-universe") == "issue-marker"


@pytest.mark.parametrize(
    "workflow",
    [
        _workflow("trusted-config") + "      evidence-universe: issue-marker\n",
        _workflow("anything-else"),
    ],
    ids=["conflicting", "unknown"],
)
def test_unresolved_universe_fails_closed(tmp_path, workflow):
    """Conflicting or unknown evidence-universe values in the base workflow fail closed."""
    repo = _make_repo(tmp_path, workflow)
    certify = tmp_path / "fake-certify"
    certify.write_text(FAKE_CERTIFY)
    certify.chmod(0o755)
    env = {"repo": repo, "certify": certify, "tmp": tmp_path, "calls": tmp_path / "calls.log"}
    proc, out = run(env)
    assert proc.returncode == 2, out
    assert out["error_code"] == "CORE_UNIVERSE_UNRESOLVED"
    assert _calls(env) == {}
